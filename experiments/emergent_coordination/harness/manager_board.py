"""Trusted, role-restricted state for the manager-worker coordination condition."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any

from experiments.emergent_coordination.harness.events import EventLog, utc_now


class ManagerCoordinationError(Exception):
    pass


@dataclass(frozen=True)
class ManagerTask:
    id: str
    description: str
    worker_id: str
    status: str


class ManagerBoard:
    """One-layer star state; it is reachable only through role-specific tools.

    The board deliberately has no worker-to-worker lookup, broadcast, claim,
    or delegation operation.  Reports retain their evidence references so the
    manager can later make an explicitly traceable submission.
    """

    def __init__(self, event_log: EventLog, manager_id: str, worker_ids: list[str]):
        self.event_log = event_log
        self.manager_id = manager_id
        self.worker_ids = frozenset(worker_ids)
        self._tasks: dict[str, dict[str, Any]] = {}
        self._next_task = 1
        self._lock = threading.RLock()
        self._manager_seen_reports: set[str] = set()

    def create_task(self, manager_id: str, worker_id: str, description: str) -> dict[str, Any]:
        self._require_manager(manager_id)
        self._require_worker(worker_id)
        if not description.strip():
            raise ManagerCoordinationError("task description is required")
        with self._lock:
            if any(task["worker_id"] == worker_id and task["status"] == "assigned" for task in self._tasks.values()):
                raise ManagerCoordinationError(f"worker already has an assigned task: {worker_id}")
            task_id = f"manager_task_{self._next_task:04d}"
            self._next_task += 1
            task = {
                "id": task_id,
                "description": description,
                "worker_id": worker_id,
                "status": "assigned",
                "created_at": utc_now(),
                "created_by": manager_id,
                "reports": [],
            }
            self._tasks[task_id] = task
        self.event_log.emit("manager_task_created", agent_id=manager_id, payload=_public_task(task))
        self.event_log.emit("manager_task_assigned", agent_id=manager_id, payload={"task_id": task_id, "worker_id": worker_id})
        return _public_task(task)

    def list_tasks(self, manager_id: str) -> list[dict[str, Any]]:
        self._require_manager(manager_id)
        with self._lock:
            tasks = [_manager_task_view(task) for task in self._tasks.values()]
            reports = [report for task in self._tasks.values() for report in task["reports"]]
        self.event_log.emit("manager_task_listed", agent_id=manager_id, payload={"count": len(tasks)})
        for report in reports:
            if report["id"] not in self._manager_seen_reports:
                self._manager_seen_reports.add(report["id"])
                self.event_log.emit(
                    "manager_report_observed",
                    agent_id=manager_id,
                    payload={
                        "report_id": report["id"],
                        "task_id": report["task_id"],
                        "worker_id": report["worker_id"],
                        "evidence_refs": list(report["evidence_refs"]),
                    },
                )
        return tasks

    def cancel_task(self, manager_id: str, task_id: str, reason: str) -> dict[str, Any]:
        self._require_manager(manager_id)
        with self._lock:
            task = self._task(task_id)
            if task["status"] != "assigned":
                raise ManagerCoordinationError("only an assigned task can be cancelled")
            task["status"] = "cancelled"
            task["cancelled_at"] = utc_now()
            task["cancel_reason"] = reason
        self.event_log.emit("manager_task_cancelled", agent_id=manager_id, payload={"task_id": task_id, "reason": reason})
        return _public_task(task)

    def reassign_task(self, manager_id: str, task_id: str, worker_id: str) -> dict[str, Any]:
        self._require_manager(manager_id)
        self._require_worker(worker_id)
        with self._lock:
            task = self._task(task_id)
            if task["status"] not in {"assigned", "cancelled"}:
                raise ManagerCoordinationError("only an assigned or cancelled task can be reassigned")
            if any(item["worker_id"] == worker_id and item["status"] == "assigned" for item in self._tasks.values() if item["id"] != task_id):
                raise ManagerCoordinationError(f"worker already has an assigned task: {worker_id}")
            previous_worker = task["worker_id"]
            task["worker_id"] = worker_id
            task["status"] = "assigned"
            task["reassigned_at"] = utc_now()
        self.event_log.emit(
            "manager_task_reassigned",
            agent_id=manager_id,
            payload={"task_id": task_id, "from_worker_id": previous_worker, "worker_id": worker_id},
        )
        return _public_task(task)

    def get_assignment(self, worker_id: str) -> dict[str, Any] | None:
        self._require_worker(worker_id)
        with self._lock:
            task = next((item for item in self._tasks.values() if item["worker_id"] == worker_id and item["status"] == "assigned"), None)
        self.event_log.emit(
            "manager_assignment_observed",
            agent_id=worker_id,
            payload={"task_id": task["id"] if task else None, "available": task is not None},
        )
        return _worker_task_view(task) if task else None

    def report_task(self, worker_id: str, task_id: str, result: str, evidence_refs: list[str] | None = None) -> dict[str, Any]:
        self._require_worker(worker_id)
        with self._lock:
            task = self._task(task_id)
            if task["worker_id"] != worker_id or task["status"] != "assigned":
                raise ManagerCoordinationError("worker may report only its currently assigned task")
            report = {
                "id": f"manager_report_{len(task['reports']) + 1:04d}_{task_id}",
                "task_id": task_id,
                "worker_id": worker_id,
                "result": result,
                "evidence_refs": list(evidence_refs or []),
                "reported_at": utc_now(),
                "transport_state": "produced",
                "model_visible": False,
                "adopted": False,
            }
            task["reports"].append(report)
            task["status"] = "reported"
        self.event_log.emit(
            "manager_worker_reported",
            agent_id=worker_id,
            payload={"report_id": report["id"], "task_id": task_id, "evidence_refs": report["evidence_refs"], "transport_state": "produced"},
        )
        return {"task_id": task_id, "report_id": report["id"], "accepted": True}

    def drain_reports(self) -> list[dict[str, Any]]:
        """Advance queued reports only; never imply model visibility/adoption."""
        delivered: list[dict[str, Any]] = []
        with self._lock:
            for task in self._tasks.values():
                for report in task["reports"]:
                    if report["transport_state"] == "produced":
                        report["transport_state"] = "queued"
                        self.event_log.emit(
                            "manager_report_queued",
                            agent_id=self.manager_id,
                            payload={"report_id": report["id"], "task_id": report["task_id"], "worker_id": report["worker_id"]},
                        )
                    if report["transport_state"] == "queued":
                        report["transport_state"] = "delivered"
                        delivered.append(dict(report))
        for report in delivered:
            self.event_log.emit(
                "manager_report_delivered",
                agent_id=self.manager_id,
                payload={"report_id": report["id"], "task_id": report["task_id"], "worker_id": report["worker_id"]},
            )
        return delivered

    def final_snapshot(self, *, completion_reason: str = "barrier") -> dict[str, Any]:
        """Return a deterministic, detached final snapshot of board state."""
        with self._lock:
            reports = [dict(report) for task in self._tasks.values() for report in task["reports"] if report["transport_state"] == "delivered"]
            tasks = [_manager_task_view(task) for task in self._tasks.values() if task["status"] in {"assigned", "cancelled"}]
        return {
            "reports": reports,
            "unresolved_tasks": [task["id"] for task in tasks],
            "completion_reason": completion_reason,
        }

    def mark_final_synthesis_visible(self, report_ids: list[str]) -> None:
        """Record visibility only when the frozen snapshot enters model input."""
        wanted = set(report_ids)
        visible_refs: dict[str, list[str]] = {}
        with self._lock:
            reports = [report for task in self._tasks.values() for report in task["reports"]]
            for report in reports:
                if report["id"] in wanted:
                    report["model_visible"] = True
                    visible_refs[report["id"]] = list(report["evidence_refs"])
        for report_id in sorted(wanted):
            self.event_log.emit(
                "manager_report_model_visible",
                agent_id=self.manager_id,
                payload={"report_id": report_id, "evidence_refs": visible_refs.get(report_id, [])},
            )

    def adopt_report(self, report_id: str) -> None:
        with self._lock:
            report = next(
                (item for task in self._tasks.values() for item in task["reports"] if item["id"] == report_id),
                None,
            )
            if report is None or not report["model_visible"]:
                raise ManagerCoordinationError("report adoption requires final synthesis visibility")
            report["adopted"] = True
        self.event_log.emit("manager_report_adopted", agent_id=self.manager_id, payload={"report_id": report_id})

    def request_more(self, worker_id: str) -> dict[str, Any]:
        self._require_worker(worker_id)
        self.event_log.emit("manager_worker_requested_more", agent_id=worker_id, payload={"worker_id": worker_id})
        return {"accepted": True, "worker_id": worker_id}

    def ready_workers(self) -> list[str]:
        with self._lock:
            return sorted(task["worker_id"] for task in self._tasks.values() if task["status"] == "assigned")

    def has_unobserved_reports(self) -> bool:
        with self._lock:
            return any(report["id"] not in self._manager_seen_reports for task in self._tasks.values() for report in task["reports"])

    def _task(self, task_id: str) -> dict[str, Any]:
        try:
            return self._tasks[task_id]
        except KeyError as exc:
            raise ManagerCoordinationError(f"unknown manager task: {task_id}") from exc

    def _require_manager(self, agent_id: str) -> None:
        if agent_id != self.manager_id:
            raise ManagerCoordinationError("manager-only operation")

    def _require_worker(self, agent_id: str) -> None:
        if agent_id not in self.worker_ids:
            raise ManagerCoordinationError("worker-only operation")


def _public_task(task: dict[str, Any]) -> dict[str, Any]:
    return {key: task[key] for key in ("id", "description", "worker_id", "status")}


def _worker_task_view(task: dict[str, Any]) -> dict[str, Any]:
    return {key: task[key] for key in ("id", "description", "status")}


def _manager_task_view(task: dict[str, Any]) -> dict[str, Any]:
    view = _public_task(task)
    view["reports"] = [dict(report) for report in task["reports"]]
    return view
