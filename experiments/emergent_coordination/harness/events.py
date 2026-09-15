from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EVENT_TYPES = (
    "agent_started",
    "agent_finished",
    "llm_call",
    "tool_call",
    "file_read",
    "file_write",
    "shared_list",
    "shared_read",
    "shared_create",
    "shared_mkdir",
    "task_created",
    "task_claimed",
    "task_released",
    "task_completed",
    "message_sent",
    "message_read",
    "artifact_published",
    "finding_submitted",
    "budget_exhausted",
    "timeout",
    "error",
    "run_started",
    "run_finished",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class EventLog:
    def __init__(self, path: Path, run_id: str, target: str = "repo_pilot_v0"):
        self.path = path
        self.run_id = run_id
        self.target = target
        self._lock = threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=True)

    def emit(
        self,
        event_type: str,
        *,
        agent_id: str | None = None,
        payload: dict[str, Any] | None = None,
        token_usage: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        record = {
            "timestamp": utc_now(),
            "run_id": self.run_id,
            "agent_id": agent_id,
            "event_type": event_type,
            "payload": payload or {},
            "token_usage": token_usage or {},
            "target": self.target,
        }
        line = json.dumps(record, ensure_ascii=False, default=str)
        with self._lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        return record

    def read_all(self) -> list[dict[str, Any]]:
        records = []
        if not self.path.exists():
            return records
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return records
