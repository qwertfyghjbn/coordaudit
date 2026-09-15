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
    """Filesystem-backed structured coordination state with atomic claim."""

    def __init__(self, root: Path, event_log: EventLog):
        self.root = root
        self.event_log = event_log
        self.tasks_dir = root / "tasks"
        self.messages_dir = root / "messages"
        self.artifacts_dir = root / "artifacts"
        self._lock = threading.Lock()
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
        tasks = []
        for path in sorted(self.tasks_dir.glob("*.json")):
            tasks.append(json.loads(path.read_text(encoding="utf-8")))
        self.event_log.emit(
            "tool_call",
            agent_id=agent_id,
            payload={"tool": "list_tasks", "count": len(tasks)},
        )
        return tasks

    def create_task(
        self,
        agent_id: str,
        description: str,
        dependencies: list[str] | None = None,
    ) -> dict[str, Any]:
        task = {
            "id": f"task_{uuid.uuid4().hex[:10]}",
            "description": description,
            "status": "open",
            "owner": None,
            "dependencies": list(dependencies or []),
            "created_by": agent_id,
            "result_artifacts": [],
            "created_at": utc_now(),
        }
        with self._lock:
            self._write_task(task)
        self.event_log.emit("task_created", agent_id=agent_id, payload=task)
        return task

    def claim_task(self, agent_id: str, task_id: str) -> dict[str, Any]:
        with self._lock:
            task = self._read_task(task_id)
            if task["status"] != "open" or task["owner"] is not None:
                raise CoordinationError(f"task already claimed: {task_id}")
            for dep in task.get("dependencies", []):
                dep_task = self._read_task(dep)
                if dep_task.get("status") != "completed":
                    raise CoordinationError(f"unmet dependency: {dep}")
            task["status"] = "claimed"
            task["owner"] = agent_id
            task["claimed_at"] = utc_now()
            self._write_task(task)
        self.event_log.emit("task_claimed", agent_id=agent_id, payload={"task_id": task_id})
        return task

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
        result_artifacts: list[str] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            task = self._read_task(task_id)
            if task.get("owner") != agent_id:
                raise CoordinationError("only the owner can complete a task")
            task["status"] = "completed"
            task["completed_at"] = utc_now()
            if result_artifacts:
                task["result_artifacts"] = list(result_artifacts)
            self._write_task(task)
        self.event_log.emit(
            "task_completed",
            agent_id=agent_id,
            payload={"task_id": task_id, "result_artifacts": result_artifacts or []},
        )
        return task

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
