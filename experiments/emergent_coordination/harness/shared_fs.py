from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from experiments.emergent_coordination.harness.events import EventLog
from experiments.emergent_coordination.harness.workspace import sha256_bytes


class SharedFilesystemError(Exception):
    pass


class SharedFilesystem:
    """Create-only / append-friendly raw shared storage.

    Allowed operations: list, read, create, mkdir.
    Overwrite of an existing file is rejected so later analysis can recover
    who created which path and with what content.
    """

    MAX_INLINE_BYTES = 8192

    def __init__(self, root: Path, event_log: EventLog, snapshot_dir: Path):
        self.root = root
        self.event_log = event_log
        self.snapshot_dir = snapshot_dir
        self._lock = threading.Lock()
        self.root.mkdir(parents=True, exist_ok=True)
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)

    def _resolve(self, relative: str) -> Path:
        if not relative or relative.startswith("/"):
            raise SharedFilesystemError("shared paths must be relative")
        candidate = (self.root / relative).resolve()
        root = self.root.resolve()
        if candidate != root and root not in candidate.parents:
            raise SharedFilesystemError("path escapes shared root")
        return candidate

    def list(self, agent_id: str, relative: str = ".") -> list[str]:
        path = self._resolve(relative)
        if not path.exists():
            raise SharedFilesystemError(f"missing path: {relative}")
        if path.is_file():
            entries = [relative]
        else:
            entries = sorted(
                str(item.relative_to(self.root))
                for item in path.iterdir()
            )
        self.event_log.emit(
            "shared_list",
            agent_id=agent_id,
            payload={"path": relative, "entries": entries},
        )
        return entries

    def read(self, agent_id: str, relative: str) -> str:
        path = self._resolve(relative)
        if not path.is_file():
            raise SharedFilesystemError(f"not a file: {relative}")
        data = path.read_bytes()
        text = data.decode("utf-8", errors="replace")
        payload = self._content_payload(relative, data, text)
        self.event_log.emit("shared_read", agent_id=agent_id, payload=payload)
        return text

    def mkdir(self, agent_id: str, relative: str) -> str:
        path = self._resolve(relative)
        with self._lock:
            path.mkdir(parents=True, exist_ok=True)
        self.event_log.emit(
            "shared_mkdir",
            agent_id=agent_id,
            payload={"path": relative},
        )
        return relative

    def create(self, agent_id: str, relative: str, content: str, *, append: bool = False) -> dict[str, Any]:
        path = self._resolve(relative)
        data = content.encode("utf-8")
        with self._lock:
            if path.exists() and not append:
                raise SharedFilesystemError(f"create-only: {relative} already exists")
            path.parent.mkdir(parents=True, exist_ok=True)
            mode = "ab" if append and path.exists() else "wb"
            with path.open(mode) as handle:
                handle.write(data)
        payload = self._content_payload(relative, data, content)
        payload["append"] = append
        self.event_log.emit("shared_create", agent_id=agent_id, payload=payload)
        self._snapshot(agent_id, relative, data)
        return payload

    def _content_payload(self, relative: str, data: bytes, text: str) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "path": relative,
            "filename": Path(relative).name,
            "content_hash": sha256_bytes(data),
            "bytes": len(data),
        }
        if len(data) <= self.MAX_INLINE_BYTES:
            payload["content"] = text
        else:
            payload["content"] = None
            payload["content_omitted"] = True
        return payload

    def _snapshot(self, agent_id: str, relative: str, data: bytes) -> None:
        digest = sha256_bytes(data)
        snap = self.snapshot_dir / f"{agent_id}_{digest[:16]}_{Path(relative).name}"
        if not snap.exists():
            snap.write_bytes(data)
