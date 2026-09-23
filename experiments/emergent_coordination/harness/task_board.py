from __future__ import annotations

import json
import os
import threading
import uuid
from pathlib import Path
from typing import Any

from experiments.emergent_coordination.harness.events import EventLog, utc_now


class CoordinationError(Exception):
    pass


class TaskBoard:
    """Filesystem-backed structured coordination state with atomic claim.

    ``initialization_lease_v1`` is an optional runtime primitive for a
    preregistered sequencing diagnostic. It serializes only the first
    list/create/claim decision for each agent in canonical agent-ID order. It
    never chooses a task scope or creates a task on behalf of an agent.
    """

    def __init__(
        self,
        root: Path,
        event_log: EventLog,
        *,
        initialization_policy: str | None = None,
        agent_ids: list[str] | tuple[str, ...] | None = None,
        result_sync_policy: str | None = None,
    ):
        self.root = root
        self.event_log = event_log
        self.tasks_dir = root / "tasks"
        self.messages_dir = root / "messages"
        self.artifacts_dir = root / "artifacts"
        self._lock = threading.RLock()
        self._initialization_condition = threading.Condition(self._lock)
        self._initialization_policy = initialization_policy
        self._initialization_order = tuple(sorted(agent_ids or ()))
        self._initialization_index = 0
        self._initialization_owner: str | None = None
        self._initialized_agents: set[str] = set()
        self._result_sync_policy = result_sync_policy
        self._participating_agents = tuple(sorted(agent_ids or ()))
        self._initial_claims: dict[str, str] = {}
        self._result_sync_trigger: dict[str, Any] | None = None
        self._result_sync_observed: set[str] = set()
        if initialization_policy not in {None, "initialization_lease_v1"}:
            raise CoordinationError(f"unsupported task-board initialization policy: {initialization_policy}")
        if initialization_policy == "initialization_lease_v1" and not self._initialization_order:
            raise CoordinationError("initialization_lease_v1 requires canonical agent IDs")
        if result_sync_policy not in {None, "result_sync_v1"}:
            raise CoordinationError(f"unsupported result-sync policy: {result_sync_policy}")
        if result_sync_policy == "result_sync_v1" and not self._participating_agents:
            raise CoordinationError("result_sync_v1 requires canonical participating agent IDs")
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self.messages_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

    def _task_path(self, task_id: str) -> Path:
        return self.tasks_dir / f"{task_id}.json"

    def _read_task(self, task_id: str) -> dict[str, Any]:
        path = self._task_path(task_id)
        if not path.exists():
            raise CoordinationError(f"unknown task: {task_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_task(self, task: dict[str, Any]) -> None:
        path = self._task_path(task["id"])
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(task, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)

    def list_tasks(self, agent_id: str) -> list[dict[str, Any]]:
        self._await_initialization_lease(agent_id, operation="list_tasks")
        with self._lock:
            tasks = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(self.tasks_dir.glob("*.json"))]
            sync_triggered = self._result_sync_trigger is not None
            sync_id = self._result_sync_trigger.get("sync_id") if self._result_sync_trigger else None
            result_observation_phase = "post_result_sync" if sync_triggered and agent_id in self._result_sync_observed else "pre_result_sync"
        self.event_log.emit(
            "tool_call",
            agent_id=agent_id,
            payload={"tool": "list_tasks", "count": len(tasks)},
        )
        for task in tasks:
            if task.get("status") == "completed":
                self.event_log.emit(
                    "task_result_observed",
                    agent_id=agent_id,
                    payload={
                        "task_id": task["id"],
                        "owner": task.get("owner"),
                        "foreign": task.get("owner") != agent_id,
                        "result_available": task.get("result") is not None,
                        "evidence_refs": task.get("evidence_refs") or [],
                        "sync_id": sync_id,
                        "observation_phase": result_observation_phase,
                    },
                )
        return tasks

    def create_task(
        self,
        agent_id: str,
        description: str,
        dependencies: list[str] | None = None,
    ) -> dict[str, Any]:
        self._await_initialization_lease(agent_id, operation="create_task")
        task = {
            "id": f"task_{uuid.uuid4().hex[:10]}",
            "description": description,
            "status": "open",
            "owner": None,
            "dependencies": list(dependencies or []),
            "creator": agent_id,
            "result": None,
            "evidence_refs": [],
            "created_at": utc_now(),
        }
        with self._lock:
            self._write_task(task)
        self.event_log.emit("task_created", agent_id=agent_id, payload=task)
        return task

    def claim_task(self, agent_id: str, task_id: str) -> dict[str, Any]:
        self._await_initialization_lease(agent_id, operation="claim_task")
        with self._lock:
            task = self._read_task(task_id)
            if task["status"] != "open" or task["owner"] is not None:
                self.event_log.emit(
                    "task_claim_conflict",
                    agent_id=agent_id,
                    payload={"task_id": task_id, "status": task.get("status"), "owner": task.get("owner")},
                    outcome="rejected",
                )
                raise CoordinationError(f"task already claimed: {task_id}")
            for dep in task.get("dependencies", []):
                dep_task = self._read_task(dep)
                if dep_task.get("status") != "completed":
                    raise CoordinationError(f"unmet dependency: {dep}")
            task["status"] = "claimed"
            task["owner"] = agent_id
            task["claimed_at"] = utc_now()
            self._write_task(task)
            if self._result_sync_policy == "result_sync_v1" and agent_id not in self._initial_claims:
                self._initial_claims[agent_id] = task_id
        self.event_log.emit("task_claimed", agent_id=agent_id, payload={"task_id": task_id})
        self.release_initialization_lease(agent_id, reason="task_claimed")
        return task

    def release_initialization_lease(self, agent_id: str, *, reason: str) -> None:
        """Release an uncompleted bootstrap lease when an agent terminates.

        A successful first claim releases the lease immediately. This terminal
        path covers a model that observes the board but submits without
        claiming, or an agent that fails after creating an open task.
        """
        if self._initialization_policy != "initialization_lease_v1":
            return
        with self._initialization_condition:
            if self._initialization_owner != agent_id:
                return
            self._release_initialization_lease_locked(agent_id, reason=reason)

    def _await_initialization_lease(self, agent_id: str, *, operation: str) -> None:
        if self._initialization_policy != "initialization_lease_v1":
            return
        if agent_id in self._initialized_agents:
            return
        waited = False
        with self._initialization_condition:
            while True:
                if agent_id in self._initialized_agents:
                    return
                if self._initialization_owner == agent_id:
                    return
                expected = (
                    self._initialization_order[self._initialization_index]
                    if self._initialization_index < len(self._initialization_order)
                    else None
                )
                if self._initialization_owner is None and expected == agent_id:
                    self._initialization_owner = agent_id
                    self.event_log.emit(
                        "task_initialization_lease_acquired",
                        agent_id=agent_id,
                        payload={
                            "policy": self._initialization_policy,
                            "operation": operation,
                            "turn_index": self._initialization_index,
                            "expected_agent": expected,
                        },
                    )
                    return
                if not waited:
                    waited = True
                    self.event_log.emit(
                        "task_initialization_lease_waited",
                        agent_id=agent_id,
                        payload={
                            "policy": self._initialization_policy,
                            "operation": operation,
                            "expected_agent": expected,
                            "owner": self._initialization_owner,
                            "turn_index": self._initialization_index,
                        },
                    )
                self._initialization_condition.wait()

    def _release_initialization_lease_locked(self, agent_id: str, *, reason: str) -> None:
        if self._initialization_owner != agent_id:
            return
        turn_index = self._initialization_index
        self._initialized_agents.add(agent_id)
        self._initialization_index += 1
        self._initialization_owner = None
        self.event_log.emit(
            "task_initialization_lease_released",
            agent_id=agent_id,
            payload={
                "policy": self._initialization_policy,
                "reason": reason,
                "turn_index": turn_index,
                "next_agent": (
                    self._initialization_order[self._initialization_index]
                    if self._initialization_index < len(self._initialization_order)
                    else None
                ),
            },
        )
        self._initialization_condition.notify_all()

    def release_task(self, agent_id: str, task_id: str) -> dict[str, Any]:
        with self._lock:
            task = self._read_task(task_id)
            if task.get("owner") != agent_id:
                raise CoordinationError("only the owner can release a task")
            if task["status"] == "completed":
                raise CoordinationError("completed task cannot be released")
            task["status"] = "open"
            task["owner"] = None
            task["released_at"] = utc_now()
            self._write_task(task)
        self.event_log.emit("task_released", agent_id=agent_id, payload={"task_id": task_id})
        return task

    def complete_task(
        self,
        agent_id: str,
        task_id: str,
        result: str | None = None,
        evidence_refs: list[str] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            task = self._read_task(task_id)
            if task.get("owner") != agent_id:
                raise CoordinationError("only the owner can complete a task")
            if task.get("status") == "completed":
                raise CoordinationError("task already completed")
            if result is not None and not isinstance(result, str):
                raise CoordinationError("task result must be a string")
            if evidence_refs is not None and (
                not isinstance(evidence_refs, list)
                or any(not isinstance(reference, str) or not reference for reference in evidence_refs)
            ):
                raise CoordinationError("evidence_refs must be a list of non-empty strings")
            task["status"] = "completed"
            task["completed_at"] = utc_now()
            task["result"] = result
            task["evidence_refs"] = list(evidence_refs or [])
            self._write_task(task)
            self.event_log.emit(
                "task_completed",
                agent_id=agent_id,
                payload={"task_id": task_id, "result": result, "evidence_refs": evidence_refs or []},
            )
            trigger = self._maybe_trigger_result_sync_locked()
            if trigger is not None:
                self.event_log.emit("result_sync_triggered", payload=trigger)
                self._initialization_condition.notify_all()
        return task

    def result_sync_status(self, agent_id: str) -> dict[str, Any]:
        """Return runtime-only synchronization state for submission gating."""
        if self._result_sync_policy != "result_sync_v1":
            return {"enabled": False, "triggered": False, "observed": False}
        with self._lock:
            initial_task_id = self._initial_claims.get(agent_id)
            initial_task = self._read_task(initial_task_id) if initial_task_id else None
            initial_claims_complete = set(self._initial_claims) == set(self._participating_agents)
            all_initial_tasks_completed = bool(initial_claims_complete) and all(
                self._read_task(task_id).get("status") == "completed"
                for task_id in self._initial_claims.values()
            )
            return {
                "enabled": True,
                "participating_agents": list(self._participating_agents),
                "initial_claims": dict(self._initial_claims),
                "initial_task_id": initial_task_id,
                "initial_task_completed": bool(initial_task and initial_task.get("status") == "completed"),
                "initial_claims_complete": initial_claims_complete,
                "all_initial_tasks_completed": all_initial_tasks_completed,
                "triggered": self._result_sync_trigger is not None,
                "sync_id": self._result_sync_trigger.get("sync_id") if self._result_sync_trigger else None,
                "observed": agent_id in self._result_sync_observed,
            }

    def observe_result_sync(self, agent_id: str, *, parent_event_id: str | None = None) -> dict[str, Any] | None:
        """Expose the raw completed-task snapshot to one agent exactly once."""
        if self._result_sync_policy != "result_sync_v1":
            return None
        with self._lock:
            if self._result_sync_trigger is None:
                return None
            snapshot = self._result_sync_snapshot_locked(agent_id)
            if agent_id not in self._result_sync_observed:
                self._result_sync_observed.add(agent_id)
                self.event_log.emit(
                    "result_sync_observed",
                    agent_id=agent_id,
                    payload={
                        "sync_id": snapshot["sync_id"],
                        "visible_completed_task_ids": snapshot["visible_completed_task_ids"],
                        "own_completed_task_ids": snapshot["own_completed_task_ids"],
                        "foreign_completed_task_ids": snapshot["foreign_completed_task_ids"],
                        "foreign_evidence_refs": snapshot["foreign_evidence_refs"],
                        "completed_tasks": snapshot["completed_tasks"],
                        "visibility": "model_visible_context",
                    },
                    parent_event_ids=[parent_event_id] if parent_event_id else None,
                )
            return snapshot

    def wait_for_result_sync(self, *, timeout_seconds: float) -> bool:
        """Wait only for the RESULT_SYNC transition, never for model behavior."""
        with self._initialization_condition:
            if self._result_sync_trigger is not None:
                return True
            self._initialization_condition.wait(timeout_seconds)
            return self._result_sync_trigger is not None

    def _maybe_trigger_result_sync_locked(self) -> dict[str, Any] | None:
        if self._result_sync_policy != "result_sync_v1" or self._result_sync_trigger is not None:
            return None
        if set(self._initial_claims) != set(self._participating_agents):
            return None
        if any(self._read_task(task_id).get("status") != "completed" for task_id in self._initial_claims.values()):
            return None
        task_ids = list(self._initial_claims.values())
        self._result_sync_trigger = {
            "policy": "result_sync_v1",
            "sync_id": "result_sync_v1_0001",
            "participating_agents": list(self._participating_agents),
            "initial_claims": dict(self._initial_claims),
            "completed_initial_task_ids": task_ids,
        }
        return dict(self._result_sync_trigger)

    def _result_sync_snapshot_locked(self, agent_id: str) -> dict[str, Any]:
        completed_tasks: list[dict[str, Any]] = []
        for path in sorted(self.tasks_dir.glob("*.json")):
            task = json.loads(path.read_text(encoding="utf-8"))
            if task.get("status") == "completed":
                completed_tasks.append(task)
        own = [task["id"] for task in completed_tasks if task.get("owner") == agent_id]
        foreign = [task["id"] for task in completed_tasks if task.get("owner") != agent_id]
        foreign_refs = sorted({
            reference
            for task in completed_tasks
            if task.get("owner") != agent_id
            for reference in task.get("evidence_refs") or []
        })
        return {
            "policy": "result_sync_v1",
            "sync_id": self._result_sync_trigger["sync_id"],
            "visible_completed_task_ids": [task["id"] for task in completed_tasks],
            "own_completed_task_ids": own,
            "foreign_completed_task_ids": foreign,
            "foreign_evidence_refs": foreign_refs,
            "completed_tasks": completed_tasks,
        }

    def claimed_tasks_for(self, agent_id: str) -> list[dict[str, Any]]:
        """Return the caller's still-open ownership obligations.

        This is a runtime-only read used by the versioned task-closure gate;
        it is intentionally not a model-visible tool and emits no synthetic
        coordination action.
        """
        with self._lock:
            claimed: list[dict[str, Any]] = []
            for path in sorted(self.tasks_dir.glob("*.json")):
                task = json.loads(path.read_text(encoding="utf-8"))
                if task.get("owner") == agent_id and task.get("status") == "claimed":
                    claimed.append(task)
            return claimed

    def send_message(self, agent_id: str, to: str, body: str) -> dict[str, Any]:
        message = {
            "id": f"msg_{uuid.uuid4().hex[:10]}",
            "from": agent_id,
            "to": to,
            "body": body,
            "created_at": utc_now(),
        }
        path = self.messages_dir / f"{message['id']}.json"
        path.write_text(json.dumps(message, indent=2, ensure_ascii=False), encoding="utf-8")
        self.event_log.emit("message_sent", agent_id=agent_id, payload=message)
        return message

    def list_messages(self, agent_id: str, unread_only: bool = False) -> list[dict[str, Any]]:
        messages = []
        for path in sorted(self.messages_dir.glob("*.json")):
            message = json.loads(path.read_text(encoding="utf-8"))
            if message.get("to") in {agent_id, "*", "broadcast"} or message.get("from") == agent_id:
                if unread_only and message.get("read_by", {}).get(agent_id):
                    continue
                messages.append(message)
        self.event_log.emit(
            "message_read",
            agent_id=agent_id,
            payload={"count": len(messages)},
        )
        return messages

    def publish_artifact(self, agent_id: str, name: str, content: str) -> dict[str, Any]:
        safe_name = Path(name).name
        artifact_id = f"{agent_id}_{uuid.uuid4().hex[:8]}_{safe_name}"
        path = self.artifacts_dir / artifact_id
        path.write_text(content, encoding="utf-8")
        record = {
            "id": artifact_id,
            "name": safe_name,
            "path": str(path),
            "created_by": agent_id,
            "created_at": utc_now(),
            "bytes": len(content.encode("utf-8")),
        }
        meta = path.with_suffix(path.suffix + ".meta.json")
        meta.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
        self.event_log.emit("artifact_published", agent_id=agent_id, payload=record)
        return record

    def list_artifacts(self, agent_id: str) -> list[dict[str, Any]]:
        artifacts = []
        for path in sorted(self.artifacts_dir.glob("*.meta.json")):
            artifacts.append(json.loads(path.read_text(encoding="utf-8")))
        self.event_log.emit(
            "tool_call",
            agent_id=agent_id,
            payload={"tool": "list_artifacts", "count": len(artifacts)},
        )
        return artifacts
