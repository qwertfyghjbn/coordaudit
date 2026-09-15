from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Callable

from experiments.emergent_coordination.harness.events import EventLog
from experiments.emergent_coordination.harness.shared_fs import SharedFilesystem, SharedFilesystemError
from experiments.emergent_coordination.harness.task_board import CoordinationError, TaskBoard
from experiments.emergent_coordination.harness.workspace import WorkspaceLayout, sha256_text

FORBIDDEN_SHELL_MARKERS = (
    "evaluator_private",
    "ground_truth",
    "datasets/synthetic",
    "canonical_results",
    "PT-PY-REPO",
    "SSRF-PY-REPO",
    "SSTI-PY-REPO",
)


class ToolError(Exception):
    pass


class AgentSandbox:
    """Per-agent tool surface.

    Isolation rules:
    - each agent has a private target copy and scratch
    - shared filesystem is opt-in by mode
    - structured coordination APIs are opt-in by mode
    - evaluator_private is never on the search path
    """

    def __init__(
        self,
        agent_id: str,
        layout: WorkspaceLayout,
        event_log: EventLog,
        *,
        shared: SharedFilesystem | None = None,
        board: TaskBoard | None = None,
        internet: bool = False,
        submit_callback: Callable[[str, dict[str, Any]], None] | None = None,
    ):
        self.agent_id = agent_id
        self.layout = layout
        self.event_log = event_log
        self.shared = shared
        self.board = board
        self.internet = internet
        self.submit_callback = submit_callback
        self.private_root = layout.agent_private(agent_id)
        self.target_root = layout.agent_target(agent_id)
        self.scratch_root = layout.agent_scratch(agent_id)
        self._submitted: dict[str, Any] | None = None

    def _resolve_private(self, relative: str) -> Path:
        if not relative:
            raise ToolError("path is required")
        candidate = (self.private_root / relative).resolve()
        if self.private_root.resolve() not in candidate.parents and candidate != self.private_root.resolve():
            raise ToolError("path escapes private workspace")
        blocked = self.layout.evaluator_private.resolve()
        if candidate == blocked or blocked in candidate.parents:
            raise ToolError("evaluator-private files are not accessible")
        return candidate

    def list_files(self, relative: str = "target") -> list[str]:
        path = self._resolve_private(relative)
        if not path.exists():
            raise ToolError(f"missing path: {relative}")
        if path.is_file():
            entries = [relative]
        else:
            entries = []
            for root, dirs, files in os.walk(path):
                dirs[:] = [name for name in dirs if name != "__pycache__"]
                for name in files:
                    full = Path(root) / name
                    entries.append(str(full.relative_to(self.private_root)))
            entries.sort()
        self.event_log.emit(
            "tool_call",
            agent_id=self.agent_id,
            payload={"tool": "list_files", "path": relative, "count": len(entries)},
        )
        return entries

    def read_file(self, relative: str) -> str:
        path = self._resolve_private(relative)
        if not path.is_file():
            raise ToolError(f"not a file: {relative}")
        text = path.read_text(encoding="utf-8", errors="replace")
        self.event_log.emit(
            "file_read",
            agent_id=self.agent_id,
            payload={"path": relative, "bytes": len(text.encode("utf-8")), "content_hash": sha256_text(text)},
        )
        return text

    def write_file(self, relative: str, content: str) -> str:
        path = self._resolve_private(relative)
        target_root = self.target_root.resolve()
        if path == target_root or target_root in path.parents:
            raise ToolError("target snapshot is read-only; write to scratch/")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        self.event_log.emit(
            "file_write",
            agent_id=self.agent_id,
            payload={"path": relative, "bytes": len(content.encode("utf-8")), "content_hash": sha256_text(content)},
        )
        return relative

    def run_shell(self, command: str, timeout: int = 30) -> dict[str, Any]:
        lowered = command.lower()
        if any(marker.lower() in lowered for marker in FORBIDDEN_SHELL_MARKERS):
            raise ToolError("command is not allowed: host/evaluator-private paths are blocked")
        if ".." in command or re.search(r"(/home/|/etc/|/var/|/usr/|/proc/)", command):
            raise ToolError("command is not allowed: host filesystem paths are blocked")
        env = os.environ.copy()
        env["HOME"] = str(self.scratch_root)
        env["PWD"] = str(self.private_root)
        if not self.internet:
            env["NO_PROXY"] = "*"
            env["no_proxy"] = "*"
            env["HTTP_PROXY"] = ""
            env["HTTPS_PROXY"] = ""
            env["http_proxy"] = ""
            env["https_proxy"] = ""
        try:
            completed = subprocess.run(
                command,
                shell=True,
                cwd=self.private_root,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            result = {
                "returncode": completed.returncode,
                "stdout": completed.stdout[-8000:],
                "stderr": completed.stderr[-4000:],
            }
        except subprocess.TimeoutExpired as exc:
            result = {
                "returncode": -1,
                "stdout": (exc.stdout or "")[-8000:] if isinstance(exc.stdout, str) else "",
                "stderr": f"timeout after {timeout}s",
            }
        self.event_log.emit(
            "tool_call",
            agent_id=self.agent_id,
            payload={"tool": "run_shell", "command": command, "returncode": result["returncode"]},
        )
        return result

    def shared_list(self, relative: str = ".") -> list[str]:
        if self.shared is None:
            raise ToolError("shared storage is not available in this mode")
        try:
            return self.shared.list(self.agent_id, relative)
        except SharedFilesystemError as exc:
            raise ToolError(str(exc)) from exc

    def shared_read(self, relative: str) -> str:
        if self.shared is None:
            raise ToolError("shared storage is not available in this mode")
        try:
            return self.shared.read(self.agent_id, relative)
        except SharedFilesystemError as exc:
            raise ToolError(str(exc)) from exc

    def shared_mkdir(self, relative: str) -> str:
        if self.shared is None:
            raise ToolError("shared storage is not available in this mode")
        try:
            return self.shared.mkdir(self.agent_id, relative)
        except SharedFilesystemError as exc:
            raise ToolError(str(exc)) from exc

    def shared_create(self, relative: str, content: str, append: bool = False) -> dict[str, Any]:
        if self.shared is None:
            raise ToolError("shared storage is not available in this mode")
        try:
            return self.shared.create(self.agent_id, relative, content, append=append)
        except SharedFilesystemError as exc:
            raise ToolError(str(exc)) from exc

    def list_tasks(self) -> list[dict[str, Any]]:
        return self._board().list_tasks(self.agent_id)

    def create_task(self, description: str, dependencies: list[str] | None = None) -> dict[str, Any]:
        return self._board().create_task(self.agent_id, description, dependencies)

    def claim_task(self, task_id: str) -> dict[str, Any]:
        try:
            return self._board().claim_task(self.agent_id, task_id)
        except CoordinationError as exc:
            raise ToolError(str(exc)) from exc

    def release_task(self, task_id: str) -> dict[str, Any]:
        try:
            return self._board().release_task(self.agent_id, task_id)
        except CoordinationError as exc:
            raise ToolError(str(exc)) from exc

    def complete_task(self, task_id: str, result_artifacts: list[str] | None = None) -> dict[str, Any]:
        try:
            return self._board().complete_task(self.agent_id, task_id, result_artifacts)
        except CoordinationError as exc:
            raise ToolError(str(exc)) from exc

    def send_message(self, to: str, body: str) -> dict[str, Any]:
        return self._board().send_message(self.agent_id, to, body)

    def list_messages(self) -> list[dict[str, Any]]:
        return self._board().list_messages(self.agent_id)

    def publish_artifact(self, name: str, content: str) -> dict[str, Any]:
        return self._board().publish_artifact(self.agent_id, name, content)

    def list_artifacts(self) -> list[dict[str, Any]]:
        return self._board().list_artifacts(self.agent_id)

    def submit_findings(self, findings: dict[str, Any] | list[Any]) -> dict[str, Any]:
        if isinstance(findings, list):
            payload = {"findings": findings}
        elif isinstance(findings, dict) and "findings" in findings:
            payload = findings
        else:
            payload = {"findings": [findings]}
        self._submitted = payload
        self.event_log.emit("finding_submitted", agent_id=self.agent_id, payload={"count": len(payload.get("findings", []))})
        if self.submit_callback:
            self.submit_callback(self.agent_id, payload)
        return {"ok": True, "count": len(payload.get("findings", []))}

    def _board(self) -> TaskBoard:
        if self.board is None:
            raise ToolError("structured coordination APIs are not available in this mode")
        return self.board
