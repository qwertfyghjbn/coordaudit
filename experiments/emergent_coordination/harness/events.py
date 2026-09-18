from __future__ import annotations

import hashlib
import json
import re
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EVENT_SCHEMA_VERSION = 2
TRANSCRIPT_SCHEMA_VERSION = 1

EVENT_TYPES = (
    "agent_started", "agent_finished", "llm_call", "llm_call_attempted",
    "call_permit_requested", "call_permit_granted", "call_permit_denied",
    "llm_retry_scheduled", "tool_call", "file_read", "file_write",
    "shared_list", "shared_read", "shared_create", "shared_mkdir",
    "task_created", "task_claimed", "task_claim_conflict", "task_released", "task_completed", "task_result_observed",
    "manager_task_created", "manager_task_assigned", "manager_task_listed", "manager_task_cancelled",
    "manager_task_reassigned", "manager_assignment_observed", "manager_worker_reported",
    "manager_report_observed", "manager_worker_requested_more",
    "message_sent", "message_read", "artifact_published", "finding_submitted", "finding_submission_rejected",
    "budget_exhausted", "timeout", "error", "run_started", "run_finished",
)

_CONTENT_FIELDS = frozenset({
    "arguments", "body", "command", "content", "description", "error",
    "result", "stdout", "stderr",
})
_SECRET_KEYS = frozenset({
    "api_key", "apikey", "authorization", "password", "secret", "token",
    "access_token", "refresh_token", "client_secret", "x_api_key",
})
_HIDDEN_MARKERS = ("evaluator_private", "ground_truth.json", "provenance.json")
_HOST_PATH = re.compile(r"(?<![\w<])/(?:home|users|private|var|tmp)/[^\s\"'\\]+", re.IGNORECASE)
_HEADER_SECRET = re.compile(
    r"(?i)\b(authorization|proxy-authorization|x-api-key|api[_-]?key|access[_-]?token|"
    r"refresh[_-]?token|client[_-]?secret|password)\b(\s*[:=]\s*)(?:bearer\s+)?[^\s,;\"'}]+"
)
_OPENAI_SECRET = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Sanitized:
    value: Any
    violations: tuple[str, ...] = ()


def sanitize_for_persistence(value: Any) -> Sanitized:
    """Deterministically remove credentials, host paths, and hidden assets."""
    violations: set[str] = set()

    def visit(item: Any, key: str | None = None) -> Any:
        if key and key.lower() in _SECRET_KEYS:
            return "[REDACTED]"
        if isinstance(item, dict):
            return {str(name): visit(child, str(name)) for name, child in item.items()}
        if isinstance(item, list):
            return [visit(child) for child in item]
        if isinstance(item, tuple):
            return [visit(child) for child in item]
        if not isinstance(item, str):
            return item
        lowered = item.lower()
        if any(marker in lowered for marker in _HIDDEN_MARKERS):
            violations.add("hidden_evaluator_or_private_content")
            return "[HIDDEN_CONTENT_REDACTED]"
        redacted = _HEADER_SECRET.sub(r"\1\2[REDACTED]", item)
        redacted = _OPENAI_SECRET.sub("[REDACTED]", redacted)
        return _HOST_PATH.sub("<HOST_PATH>", redacted)

    return Sanitized(value=visit(value), violations=tuple(sorted(violations)))


class EventLog:
    """Stable event index; model/tool content lives in append-only side records."""

    def __init__(self, path: Path, run_id: str, target: str = "repo_pilot_v0"):
        self.path = path
        self.run_id = run_id
        self.target = target
        self.artifact_dir = path.parent / "artifacts"
        self._lock = threading.Lock()
        self._local = threading.local()
        self._sequence = 0
        self._artifact_sequence = 0
        self._integrity_violations: set[str] = set()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=True)

    @property
    def integrity_violations(self) -> list[str]:
        with self._lock:
            return sorted(self._integrity_violations)

    @contextmanager
    def parent_context(self, parent_event_id: str):
        """Attach a dispatch event to tool/store events emitted on this thread."""
        previous = getattr(self._local, "parent_event_id", None)
        self._local.parent_event_id = parent_event_id
        try:
            yield
        finally:
            self._local.parent_event_id = previous

    def emit(
        self,
        event_type: str,
        *,
        agent_id: str | None = None,
        payload: dict[str, Any] | None = None,
        token_usage: dict[str, Any] | None = None,
        parent_event_ids: list[str] | tuple[str, ...] | None = None,
        outcome: str | None = None,
        budget_progress: dict[str, Any] | None = None,
        artifact_refs: list[str] | tuple[str, ...] | None = None,
    ) -> dict[str, Any]:
        if event_type not in EVENT_TYPES:
            raise ValueError(f"unknown event type: {event_type}")
        with self._lock:
            self._sequence += 1
            event_id = f"evt_{self._sequence:08d}"
            projected, hashes, generated_refs = self._project_payload(
                payload or {}, event_id=event_id, agent_id=agent_id
            )
            inherited_parent = getattr(self._local, "parent_event_id", None)
            effective_parents = (
                list(parent_event_ids)
                if parent_event_ids is not None
                else ([inherited_parent] if inherited_parent else [])
            )
            record = {
                "schema_version": EVENT_SCHEMA_VERSION,
                "event_id": event_id,
                "sequence": self._sequence,
                "timestamp": utc_now(),
                "run_id": self.run_id,
                "agent_id": agent_id,
                "event_type": event_type,
                "parent_event_ids": effective_parents,
                "outcome": outcome or _outcome_from_payload(projected),
                "budget_progress": budget_progress or {},
                "payload": projected,
                "content_hashes": hashes,
                "artifact_refs": list(artifact_refs or []) + generated_refs,
                "token_usage": sanitize_for_persistence(token_usage or {}).value,
                "target": self.target,
            }
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
            return record

    def _project_payload(self, payload: dict[str, Any], *, event_id: str, agent_id: str | None) -> tuple[dict[str, Any], list[dict[str, str]], list[str]]:
        hashes: list[dict[str, str]] = []
        refs: list[str] = []

        def project(item: Any, path: str, key: str | None = None) -> Any:
            if key in _CONTENT_FIELDS:
                artifact = self._append_artifact(event_id, agent_id, path, item)
                hashes.append({"field": path, "sha256": artifact["content_hash"]})
                refs.append(artifact["artifact_id"])
                return {"content_hash": artifact["content_hash"], "bytes": artifact["bytes"]}
            if isinstance(item, dict):
                return {str(name): project(child, f"{path}.{name}", str(name)) for name, child in item.items()}
            if isinstance(item, list):
                return [project(child, f"{path}[{index}]") for index, child in enumerate(item)]
            sanitized = sanitize_for_persistence(item)
            self._integrity_violations.update(sanitized.violations)
            return sanitized.value

        return project(payload, "payload"), hashes, refs

    def _append_artifact(self, event_id: str, agent_id: str | None, field: str, value: Any) -> dict[str, Any]:
        sanitized = sanitize_for_persistence(value)
        self._integrity_violations.update(sanitized.violations)
        self._artifact_sequence += 1
        artifact_id = f"art_{self._artifact_sequence:08d}"
        encoded = canonical_json(sanitized.value)
        record = {
            "schema_version": 1,
            "artifact_id": artifact_id,
            "event_id": event_id,
            "agent_id": agent_id,
            "field": field,
            "content": sanitized.value,
            "content_hash": hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
            "bytes": len(encoded.encode("utf-8")),
        }
        owner = agent_id or "control_plane"
        with (self.artifact_dir / f"{owner}.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        return record

    def read_all(self) -> list[dict[str, Any]]:
        return _read_jsonl(self.path)

    def read_artifacts(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for path in sorted(self.artifact_dir.glob("*.jsonl")):
            records.extend(_read_jsonl(path))
        return records


class TranscriptLog:
    """Per-agent append-only records of the redacted, actually-visible context."""

    def __init__(self, root: Path, run_id: str, event_log: EventLog):
        self.root = root
        self.run_id = run_id
        self.event_log = event_log
        self._lock = threading.Lock()
        self._sequences: dict[str, int] = {}
        root.mkdir(parents=True, exist_ok=True)

    def request(self, *, agent_id: str, step: int, permit_id: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]], parent_event_ids: list[str]) -> dict[str, Any]:
        return self._append(agent_id=agent_id, kind="model_request", payload={"step": step, "permit_id": permit_id, "messages": messages, "tools": tools}, parent_refs=parent_event_ids)

    def response(
        self,
        *,
        agent_id: str,
        step: int,
        permit_id: str,
        content: str | None,
        tool_calls: list[dict[str, Any]],
        model_metadata: dict[str, Any],
        parent_refs: list[str],
    ) -> dict[str, Any]:
        return self._append(
            agent_id=agent_id,
            kind="model_response",
            payload={
                "step": step,
                "permit_id": permit_id,
                "content": content or "",
                "tool_calls": tool_calls,
                "model_metadata": model_metadata,
            },
            parent_refs=parent_refs,
        )

    def tool_result(self, *, agent_id: str, tool_call_id: str, name: str, content: str, parent_refs: list[str]) -> dict[str, Any]:
        return self._append(agent_id=agent_id, kind="tool_result", payload={"tool_call_id": tool_call_id, "name": name, "content": content}, parent_refs=parent_refs)

    def _append(self, *, agent_id: str, kind: str, payload: dict[str, Any], parent_refs: list[str]) -> dict[str, Any]:
        sanitized = sanitize_for_persistence(payload)
        if sanitized.violations:
            with self.event_log._lock:
                self.event_log._integrity_violations.update(sanitized.violations)
        with self._lock:
            sequence = self._sequences.get(agent_id, 0) + 1
            self._sequences[agent_id] = sequence
            record = {
                "schema_version": TRANSCRIPT_SCHEMA_VERSION,
                "transcript_id": f"trn_{agent_id}_{sequence:08d}",
                "sequence": sequence,
                "timestamp": utc_now(),
                "run_id": self.run_id,
                "agent_id": agent_id,
                "kind": kind,
                "parent_refs": list(parent_refs),
                "content": sanitized.value,
                "content_hash": content_hash(sanitized.value),
            }
            with (self.root / f"{agent_id}.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
            return record

    def read_all(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for path in sorted(self.root.glob("*.jsonl")):
            records.extend(_read_jsonl(path))
        return records


def reconcile_run(event_log: EventLog, transcript_log: TranscriptLog, budget_snapshot: dict[str, Any]) -> dict[str, Any]:
    """Verify index, append-only contents, and permit ledger agree at run end."""
    reasons: list[str] = list(event_log.integrity_violations)
    events = event_log.read_all()
    artifacts = {item.get("artifact_id"): item for item in event_log.read_artifacts()}
    transcripts = transcript_log.read_all()
    seen_events: set[str] = set()
    expected_sequence = 1
    calls: dict[str, dict[str, Any]] = {}
    for event in events:
        if event.get("schema_version") != EVENT_SCHEMA_VERSION or event.get("sequence") != expected_sequence:
            reasons.append("event_index_sequence_or_schema_mismatch")
        expected_sequence += 1
        event_id = event.get("event_id")
        if not isinstance(event_id, str) or event_id in seen_events:
            reasons.append("event_id_missing_or_duplicate")
        if any(parent not in seen_events for parent in event.get("parent_event_ids") or []):
            reasons.append("event_parent_reference_missing_or_forward")
        seen_events.add(event_id)
        for ref in event.get("artifact_refs") or []:
            artifact = artifacts.get(ref)
            if artifact is None and not str(ref).startswith("trn_"):
                reasons.append("event_artifact_reference_missing")
            elif artifact is not None and content_hash(artifact.get("content")) != artifact.get("content_hash"):
                reasons.append("artifact_content_hash_mismatch")
        if event.get("event_type") == "llm_call":
            permit_id = (event.get("payload") or {}).get("permit_id")
            if permit_id:
                calls[str(permit_id)] = event

    by_agent: dict[str, int] = {}
    transcript_ids: set[str] = set()
    for record in transcripts:
        agent_id = str(record.get("agent_id"))
        next_sequence = by_agent.get(agent_id, 0) + 1
        if record.get("schema_version") != TRANSCRIPT_SCHEMA_VERSION or record.get("sequence") != next_sequence:
            reasons.append("transcript_sequence_or_schema_mismatch")
        by_agent[agent_id] = next_sequence
        transcript_id = record.get("transcript_id")
        if not isinstance(transcript_id, str) or transcript_id in transcript_ids:
            reasons.append("transcript_id_missing_or_duplicate")
        transcript_ids.add(transcript_id)
        if content_hash(record.get("content")) != record.get("content_hash"):
            reasons.append("transcript_content_hash_mismatch")
        if sanitize_for_persistence(record.get("content")).violations:
            reasons.append("hidden_evaluator_or_private_content")

    ledger = {entry.get("permit_id"): entry for entry in budget_snapshot.get("permit_ledger") or []}
    if set(calls) != set(ledger):
        reasons.append("permit_ledger_call_set_mismatch")
    for permit_id, entry in ledger.items():
        event = calls.get(permit_id)
        if event is None:
            continue
        if (event.get("outcome") or (event.get("payload") or {}).get("outcome")) != entry.get("outcome"):
            reasons.append("permit_ledger_outcome_mismatch")
        refs = set(event.get("artifact_refs") or [])
        if not any(ref in transcript_ids for ref in refs):
            reasons.append("llm_call_missing_request_transcript")
        if entry.get("outcome") == "succeeded" and len(refs & transcript_ids) < 2:
            reasons.append("successful_llm_call_missing_response_transcript")

    unique_reasons = sorted(set(reasons))
    return {"status": "valid" if not unique_reasons else "infrastructure_invalid", "reasons": unique_reasons, "event_count": len(events), "transcript_count": len(transcripts), "artifact_count": len(artifacts), "permit_count": len(ledger)}


def _outcome_from_payload(payload: dict[str, Any]) -> str | None:
    value = payload.get("outcome")
    return value if isinstance(value, str) else None


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]
