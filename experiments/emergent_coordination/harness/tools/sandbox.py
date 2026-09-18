from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable

from experiments.emergent_coordination.harness.events import EventLog
from experiments.emergent_coordination.harness.findings import validate_evidence_refs as validate_v0_evidence_refs
from experiments.emergent_coordination.harness.findings import validate_payload as validate_v0_payload
from experiments.emergent_coordination.harness.repository_v1_findings import validate_evidence_refs as validate_v1_evidence_refs
from experiments.emergent_coordination.harness.repository_v1_findings import validate_payload as validate_v1_payload
from experiments.emergent_coordination.harness.shared_fs import SharedFilesystem, SharedFilesystemError
from experiments.emergent_coordination.harness.manager_board import ManagerBoard, ManagerCoordinationError
from experiments.emergent_coordination.harness.task_board import CoordinationError, TaskBoard
from experiments.emergent_coordination.harness.workspace import WorkspaceLayout, sha256_text

class ToolError(Exception):
    pass


class SandboxUnavailable(ToolError):
    pass


def assert_os_sandbox_ready() -> None:
    """Fail before a live run if bubblewrap cannot form the required namespace."""
    binary = shutil.which("bwrap")
    if binary is None:
        raise SandboxUnavailable("OS sandbox unavailable; shell execution is refused")
    command = _bwrap_base(binary) + ["--dir", "/work", "--chdir", "/work", "/bin/sh", "-lc", "exit 0"]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=10, env={})
    except (OSError, subprocess.SubprocessError) as exc:
        raise SandboxUnavailable("OS sandbox unavailable; shell execution is refused") from exc
    if completed.returncode != 0:
        raise SandboxUnavailable("OS sandbox unavailable; shell execution is refused")


def _bwrap_base(binary: str) -> list[str]:
    """Minimal immutable runtime mount set; agent state is added separately."""
    command = [
        binary,
        "--die-with-parent",
        "--new-session",
        "--unshare-net",
        "--unshare-pid",
        "--unshare-ipc",
        "--unshare-uts",
        "--clearenv",
        "--setenv",
        "PATH",
        "/usr/bin:/bin",
        "--setenv",
        "HOME",
        "/work/scratch",
        "--setenv",
        "TMPDIR",
        "/tmp",
        "--setenv",
        "PWD",
        "/work",
        "--ro-bind",
        "/usr",
        "/usr",
        "--symlink",
        "usr/bin",
        "/bin",
        "--symlink",
        "usr/sbin",
        "/sbin",
        "--ro-bind",
        "/lib",
        "/lib",
        "--ro-bind",
        "/lib64",
        "/lib64",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--tmpfs",
        "/tmp",
    ]
    return command


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
        manager_board: ManagerBoard | None = None,
        internet: bool = False,
        require_os_sandbox: bool = False,
        finding_schema: str = "repository_pilot_v0",
        submit_callback: Callable[[str, dict[str, Any]], None] | None = None,
    ):
        self.agent_id = agent_id
        self.layout = layout
        self.event_log = event_log
        self.shared = shared
        self.board = board
        self.manager_board = manager_board
        self.internet = internet
        self.require_os_sandbox = require_os_sandbox
        self.finding_schema = finding_schema
        self.submit_callback = submit_callback
        self.private_root = layout.agent_private(agent_id)
        self.target_root = layout.agent_target(agent_id)
        self.scratch_root = layout.agent_scratch(agent_id)
        self._submitted: dict[str, Any] | None = None
        self.submission_attempts = 0
        self.invalid_submission_attempts = 0
        if self.require_os_sandbox:
            assert_os_sandbox_ready()

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

    def read_file(self, relative: str) -> dict[str, str]:
        path = self._resolve_private(relative)
        if not path.is_file():
            raise ToolError(f"not a file: {relative}")
        text = path.read_text(encoding="utf-8", errors="replace")
        event = self.event_log.emit(
            "file_read",
            agent_id=self.agent_id,
            payload={"path": relative, "bytes": len(text.encode("utf-8")), "content_hash": sha256_text(text)},
        )
        # The opaque event ID is the only accepted finding evidence reference.
        # It lets the evaluator prove the submitting agent actually saw this file.
        return {"evidence_ref": event["event_id"], "path": relative, "content": text}

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
        if timeout <= 0:
            raise ToolError("timeout must be positive")
        binary = shutil.which("bwrap")
        if binary is None:
            raise SandboxUnavailable("OS sandbox unavailable; shell execution is refused")
        shell_command = _bwrap_base(binary) + [
            "--dir",
            "/work",
            "--ro-bind",
            str(self.target_root.resolve()),
            "/work/target",
            "--bind",
            str(self.scratch_root.resolve()),
            "/work/scratch",
            "--chdir",
            "/work",
            "/bin/sh",
            "-lc",
            command,
        ]
        try:
            completed = subprocess.run(
                shell_command,
                cwd=self.scratch_root,
                env={},
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
        except OSError as exc:
            raise SandboxUnavailable("OS sandbox unavailable; shell execution is refused") from exc
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

    def complete_task(
        self,
        task_id: str,
        result: str | None = None,
        evidence_refs: list[str] | None = None,
    ) -> dict[str, Any]:
        try:
            return self._board().complete_task(self.agent_id, task_id, result, evidence_refs)
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

    def manager_create_task(self, worker_id: str, description: str) -> dict[str, Any]:
        try:
            return self._manager_board().create_task(self.agent_id, worker_id, description)
        except ManagerCoordinationError as exc:
            raise ToolError(str(exc)) from exc

    def manager_list_tasks(self) -> list[dict[str, Any]]:
        try:
            return self._manager_board().list_tasks(self.agent_id)
        except ManagerCoordinationError as exc:
            raise ToolError(str(exc)) from exc

    def manager_cancel_task(self, task_id: str, reason: str) -> dict[str, Any]:
        try:
            return self._manager_board().cancel_task(self.agent_id, task_id, reason)
        except ManagerCoordinationError as exc:
            raise ToolError(str(exc)) from exc

    def manager_reassign_task(self, task_id: str, worker_id: str) -> dict[str, Any]:
        try:
            return self._manager_board().reassign_task(self.agent_id, task_id, worker_id)
        except ManagerCoordinationError as exc:
            raise ToolError(str(exc)) from exc

    def worker_get_assignment(self) -> dict[str, Any] | None:
        try:
            return self._manager_board().get_assignment(self.agent_id)
        except ManagerCoordinationError as exc:
            raise ToolError(str(exc)) from exc

    def worker_report_task(self, task_id: str, result: str, evidence_refs: list[str]) -> dict[str, Any]:
        try:
            return self._manager_board().report_task(self.agent_id, task_id, result, evidence_refs)
        except ManagerCoordinationError as exc:
            raise ToolError(str(exc)) from exc

    def worker_request_more(self) -> dict[str, Any]:
        try:
            return self._manager_board().request_more(self.agent_id)
        except ManagerCoordinationError as exc:
            raise ToolError(str(exc)) from exc

    def submit_findings(self, findings: dict[str, Any] | list[Any]) -> dict[str, Any]:
        self.submission_attempts += 1
        if isinstance(findings, list):
            payload = {"findings": findings}
        elif isinstance(findings, dict) and "findings" in findings:
            payload = findings
        else:
            payload = {"findings": [findings]}
        if self.finding_schema == "repository_pilot_v0":
            intake = validate_v0_payload(payload)
            validate_evidence_refs = validate_v0_evidence_refs
        elif self.finding_schema == "repository_v1":
            intake = validate_v1_payload(payload)
            validate_evidence_refs = validate_v1_evidence_refs
        else:
            raise ToolError("unsupported finding schema")
        errors = list(intake.errors)
        if intake.accepted:
            all_events = self.event_log.read_all()
            file_reads = {
                event["event_id"]: str((event.get("payload") or {}).get("path") or "")
                for event in all_events
                if event.get("event_type") == "file_read"
            }
            directly_read = {
                event["event_id"]
                for event in all_events
                if event.get("agent_id") == self.agent_id and event.get("event_type") == "file_read"
            }
            task_observed = {
                reference
                for event in all_events
                if event.get("agent_id") == self.agent_id and event.get("event_type") == "task_result_observed"
                for reference in ((event.get("payload") or {}).get("evidence_refs") or [])
            }
            manager_report_observed = {
                reference
                for event in all_events
                if event.get("agent_id") == self.agent_id and event.get("event_type") == "manager_report_observed"
                for reference in ((event.get("payload") or {}).get("evidence_refs") or [])
            }
            evidence_events = {
                reference: file_reads[reference]
                for reference in directly_read | task_observed | manager_report_observed
                if reference in file_reads
            }
            errors.extend(validate_evidence_refs(intake.payload or {}, evidence_events))
        if errors:
            self.invalid_submission_attempts += 1
            self.event_log.emit(
                "finding_submission_rejected",
                agent_id=self.agent_id,
                payload={"error_count": len(errors), "errors": errors},
                outcome="rejected",
            )
            return {"ok": False, "errors": errors, "retry_allowed": True}
        self._submitted = intake.payload
        self.event_log.emit(
            "finding_submitted",
            agent_id=self.agent_id,
            payload={"count": len(payload.get("findings", []))},
            outcome="accepted",
        )
        if self.submit_callback:
            self.submit_callback(self.agent_id, intake.payload or {"findings": []})
        return {"ok": True, "count": len(payload.get("findings", []))}

    def _board(self) -> TaskBoard:
        if self.board is None:
            raise ToolError("structured coordination APIs are not available in this mode")
        return self.board

    def _manager_board(self) -> ManagerBoard:
        if self.manager_board is None:
            raise ToolError("manager-worker coordination is not available in this mode")
        return self.manager_board
