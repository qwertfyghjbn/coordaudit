"""Condition-neutral post-terminal finalizer for T-Pilot 2 (``team_synthesis_v1``).

This runner is deliberately independent from the frozen search-stage
``AgentRunner`` lifecycle: search agents are already terminal when it starts,
it never reopens their sessions, and its single session (``team_finalizer``)
sees exactly the frozen raw candidate set plus its own bounded read results.
The machine it implements is the frozen design:

    all search agents terminal -> C_raw freeze
    -> condition-neutral finalizer (retain / merge / correct / drop)
    -> explicit raw decisions + C_final
    -> (evaluation happens in the runner, blind layers come later)

Degradation is an explicit recorded outcome, never a run failure: if the
reserve, the synthesis window, or the run wall clock expires before a valid
``submit_team_findings``, C_final becomes the deterministic union of C_raw.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any

from experiments.emergent_coordination.harness.budget import BudgetExhausted, BudgetTracker
from experiments.emergent_coordination.harness.call_role import classify_call_role
from experiments.emergent_coordination.harness.events import EventLog, TranscriptLog, utc_now
from experiments.emergent_coordination.harness.llm.client import LLMClient
from experiments.emergent_coordination.harness.paths import normalize_target_relative_path
from experiments.emergent_coordination.harness.prompts import (
    T_PILOT_2_SYNTHESIS_INSTRUCTIONS,
    synthesis_snapshot_message,
)
from experiments.emergent_coordination.harness.repository_v1_findings import validate_evidence_refs
from experiments.emergent_coordination.harness.synthesis_findings import validate_synthesis_payload
from experiments.emergent_coordination.harness.tools.sandbox import AgentSandbox
from experiments.emergent_coordination.harness.tools.specs import synthesis_tools
from experiments.emergent_coordination.harness.workspace import WorkspaceLayout, prepare_finalizer_workspace

FINALIZER_ID = "team_finalizer"
SYNTHESIS_PHASE = "team_synthesis_v1"
_ALLOWED_TOOL_NAMES = frozenset({"read_file", "submit_team_findings"})
_CORRECTION_FIELDS = ("severity", "trust_boundary", "affected_object", "verification")


@dataclass
class SynthesisOutcome:
    status: str  # completed | degraded | skipped_empty_raw
    reason: str | None
    final_payload: dict[str, Any] | None
    raw_dispositions: list[dict[str, Any]]
    delta: dict[str, Any]
    provider_calls: int = 0
    provider_failures: int = 0
    read_file_calls: int = 0
    model_snapshot_sha256: str | None = None


class TeamSynthesisRunner:
    """Run the bounded post-terminal synthesis phase over a frozen C_raw."""

    def __init__(
        self,
        *,
        layout: WorkspaceLayout,
        event_log: EventLog,
        transcript_log: TranscriptLog,
        budget: BudgetTracker,
        llm: LLMClient,
        agent_results: list[dict[str, Any]],
        submissions: dict[str, dict[str, Any]],
        agent_ids: list[str],
        read_file_cap: int = 1,
    ):
        self.layout = layout
        self.event_log = event_log
        self.transcript_log = transcript_log
        self.budget = budget
        self.llm = llm
        self.agent_results = agent_results
        self.submissions = submissions
        self.agent_ids = list(agent_ids)
        self.read_file_cap = int(read_file_cap)
        self._messages: list[dict[str, Any]] = []
        self._last_event_id: str | None = None
        self._reads_used = 0
        self._provider_calls = 0
        self._provider_failures = 0
        self._last_provider_failed = False
        self._input_visible_emitted = False
        self._model_snapshot_sha256: str | None = None
        self._allowed_read_paths: set[str] = set()
        self._foreign_refs: set[str] = set()

    # ------------------------------------------------------------------ freeze

    def freeze_raw_set(self) -> tuple[list[dict[str, Any]], dict[str, Any] | None, str | None]:
        """Freeze C_raw: full records + model-visible snapshot, hashed."""
        events = self.event_log.read_all()
        file_read_paths = {
            event["event_id"]: str((event.get("payload") or {}).get("path") or "")
            for event in events
            if event.get("event_type") == "file_read"
        }
        submission_events = [
            event
            for event in events
            if event.get("event_type") == "finding_submitted"
        ]
        submission_order = {event["event_id"]: index for index, event in enumerate(submission_events)}
        stop_reasons = {str(item.get("agent_id")): item.get("stop_reason") for item in self.agent_results}

        records: list[dict[str, Any]] = []
        for event in sorted(submission_events, key=lambda item: item.get("sequence") or 0):
            agent_id = str(event.get("agent_id"))
            payload = self.submissions.get(agent_id) or {}
            for finding in payload.get("findings", []):
                raw_index = len(records)
                records.append(
                    {
                        "raw_id": f"raw_{raw_index:02d}",
                        "submitted_by": agent_id,
                        "submission_event_id": event["event_id"],
                        "submission_sequence": submission_order.get(event["event_id"], raw_index),
                        "submission_time": event.get("timestamp"),
                        "finding": finding,
                        "evidence_map": {
                            reference: file_read_paths.get(reference, "")
                            for reference in (finding.get("evidence_refs") or [])
                        },
                        "submitter_stop_reason": stop_reasons.get(agent_id),
                    }
                )
        contributor_tokens = {
            agent_id: f"contributor_{index}"
            for index, agent_id in enumerate(sorted(self.agent_ids))
        }
        model_snapshot = {
            "schema_version": "t-pilot-2-raw-candidates-model-v1",
            "raw_candidates": [
                {
                    "raw_id": record["raw_id"],
                    "contributor": contributor_tokens[record["submitted_by"]],
                    "finding": record["finding"],
                    "evidence_map": record["evidence_map"],
                    "submission_sequence": record["submission_sequence"],
                }
                for record in records
            ],
            "contributor_terminal_states": {
                contributor_tokens[agent_id]: stop_reasons.get(agent_id)
                for agent_id in sorted(self.agent_ids)
            },
        }
        model_snapshot_json = json.dumps(model_snapshot, ensure_ascii=False, sort_keys=True)
        model_snapshot_sha256 = hashlib.sha256(model_snapshot_json.encode("utf-8")).hexdigest()
        artifact = {
            "schema_version": "t-pilot-2-raw-candidates-v1",
            "frozen_at": utc_now(),
            "raw_count": len(records),
            "contributor_map": contributor_tokens,
            "model_snapshot": model_snapshot,
            "model_snapshot_sha256": model_snapshot_sha256,
            "records": records,
        }
        artifact_path = self.layout.artifacts / "raw_candidate_set.json"
        artifact_path.write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")
        artifact_sha256 = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
        self._last_event_id = self.event_log.emit(
            "raw_candidate_set_frozen",
            agent_id=FINALIZER_ID,
            payload={
                "raw_count": len(records),
                "model_snapshot_sha256": model_snapshot_sha256,
                "artifact_sha256": artifact_sha256,
                "contributor_terminal_states": model_snapshot["contributor_terminal_states"],
                "evidence_ref_count": sum(len(record["evidence_map"]) for record in records),
            },
            parent_event_ids=[self._last_event_id] if self._last_event_id else None,
        )["event_id"]
        return records, (model_snapshot if records else None), (model_snapshot_sha256 if records else None)

    # -------------------------------------------------------------------- run

    def run(self) -> SynthesisOutcome:
        records, model_snapshot, model_snapshot_sha256 = self.freeze_raw_set()
        if not records:
            final_payload = {"schema_version": "deterministic-union", "findings": []}
            delta = self._mechanical_delta(records, [], [])
            (self.layout.artifacts / "team_final_findings.json").write_text(
                json.dumps(final_payload, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            (self.layout.artifacts / "raw_disposition.json").write_text(
                json.dumps({"schema_version": "t-pilot-2-raw-disposition-v1", "source": "skipped_empty_raw", "dispositions": []}, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            (self.layout.artifacts / "synthesis_delta.json").write_text(
                json.dumps(delta, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            self.event_log.emit(
                "synthesis_skipped_empty_raw",
                agent_id=FINALIZER_ID,
                payload={"raw_count": 0, "final_finding_count": 0},
                parent_event_ids=[self._last_event_id] if self._last_event_id else None,
                outcome="skipped_empty_raw",
            )
            return SynthesisOutcome(
                status="skipped_empty_raw",
                reason="empty_raw_set",
                final_payload=final_payload,
                raw_dispositions=[],
                delta=delta,
            )
        self.budget.register_agent(FINALIZER_ID)
        self.budget.open_synthesis_phase()
        prepare_finalizer_workspace(self.layout)
        sandbox = AgentSandbox(
            FINALIZER_ID,
            self.layout,
            self.event_log,
            internet=False,
            finding_schema="repository_v1",
        )
        known_raw_ids = {record["raw_id"] for record in records}
        self._foreign_refs = {reference for record in records for reference in record["evidence_map"]}
        self._allowed_read_paths = {
            normalize_target_relative_path(path)
            for record in records
            for path in (
                *record["evidence_map"].values(),
                (record["finding"].get("source") or {}).get("file"),
                (record["finding"].get("sink") or {}).get("file"),
                ((record["finding"].get("guard") or {}).get("anchor") or {}).get("file"),
            )
            if path
        }
        self._model_snapshot_sha256 = model_snapshot_sha256
        self._messages = [
            {"role": "system", "content": T_PILOT_2_SYNTHESIS_INSTRUCTIONS},
            {"role": "user", "content": synthesis_snapshot_message(model_snapshot or {}, model_snapshot_sha256=model_snapshot_sha256 or "")},
        ]
        tools = synthesis_tools()
        reserve = self.budget.synthesis_reserve_permits
        # Each loop iteration performs exactly one provider call; the phase
        # is therefore bounded by the static reserve and the synthesis window.
        for _attempt in range(reserve + 1):
            try:
                self.budget.check_synthesis_window()
            except BudgetExhausted:
                return self._degrade(records, "deadline")
            if self.budget.synthesis_calls_used >= reserve:
                return self._degrade(records, "provider_failure" if self._last_provider_failed else "reserve_exhausted")
            response = self._complete_with_permit(tools, model_snapshot_sha256 or "")
            if response is None:
                # Provider failure: the attempt consumed a reserved permit and
                # there is no hidden retry; the phase continues only while
                # reserve and window remain (implementation-audit semantics).
                continue
            try:
                self.budget.check_synthesis_window()
            except BudgetExhausted:
                return self._degrade(records, "deadline")
            accepted, tool_results = self._handle_response(response, sandbox, known_raw_ids, records)
            if accepted is not None:
                self.budget.mark_agent_terminal(FINALIZER_ID)
                self.budget.close_synthesis_phase()
                return accepted
            for content in tool_results:
                self._messages.append(content[0])
                self._last_event_id = content[1]
        return self._degrade(records, "reserve_exhausted")

    # ----------------------------------------------------------- provider call

    def _complete_with_permit(self, tools: list[dict[str, Any]], model_snapshot_sha256: str):
        started = self.event_log.emit(
            "call_permit_requested",
            agent_id=FINALIZER_ID,
            payload={"step": self._provider_calls + 1, "retry_of": None},
            parent_event_ids=[self._last_event_id] if self._last_event_id else None,
        )
        try:
            permit = self.budget.acquire_call_permit(FINALIZER_ID, call_kind="team_synthesis")
        except BudgetExhausted as exc:
            self.event_log.emit(
                "call_permit_denied",
                agent_id=FINALIZER_ID,
                payload={"step": self._provider_calls + 1, "reason": exc.reason, "snapshot": exc.snapshot},
                parent_event_ids=[started["event_id"]],
            )
            return None
        granted = self.event_log.emit(
            "call_permit_granted",
            agent_id=FINALIZER_ID,
            payload={**permit.as_dict(), "step": self._provider_calls + 1, "budget": self.budget.snapshot()},
            parent_event_ids=[started["event_id"]],
            budget_progress=self.budget.snapshot(),
        )
        self._last_event_id = granted["event_id"]
        request_transcript = self.transcript_log.request(
            agent_id=FINALIZER_ID,
            step=self._provider_calls + 1,
            permit_id=permit.permit_id,
            messages=self._messages,
            tools=tools,
            parent_event_ids=[granted["event_id"]],
        )
        if not self._input_visible_emitted:
            self._input_visible_emitted = True
            self._last_event_id = self.event_log.emit(
                "synthesis_started",
                agent_id=FINALIZER_ID,
                payload={
                    "policy": SYNTHESIS_PHASE,
                    "reserve_permits": self.budget.synthesis_reserve_permits,
                    "window_seconds": self.budget.synthesis_window_seconds,
                    "read_file_cap": self.read_file_cap,
                    "model_snapshot_sha256": model_snapshot_sha256,
                },
                parent_event_ids=[granted["event_id"]],
            )["event_id"]
            self._last_event_id = self.event_log.emit(
                "synthesis_input_model_visible",
                agent_id=FINALIZER_ID,
                payload={
                    "model_snapshot_sha256": model_snapshot_sha256,
                    "request_transcript_id": request_transcript["transcript_id"],
                    "foreign_evidence_refs": sorted(self._foreign_refs),
                },
                parent_event_ids=[granted["event_id"]],
                artifact_refs=[request_transcript["transcript_id"]],
            )["event_id"]
        attempted = self.event_log.emit(
            "llm_call_attempted",
            agent_id=FINALIZER_ID,
            payload={**permit.as_dict(), "step": self._provider_calls + 1},
            parent_event_ids=[granted["event_id"]],
            artifact_refs=[request_transcript["transcript_id"]],
        )
        started_at = time.monotonic()
        self._provider_calls += 1
        try:
            response = self.llm.complete(self._messages, tools, agent_id=FINALIZER_ID)
        except Exception as exc:  # noqa: BLE001 - a bounded failure is an outcome
            self._provider_failures += 1
            self._last_provider_failed = True
            outcome = "timeout" if "timeout" in type(exc).__name__.lower() or isinstance(exc, TimeoutError) else "provider_error"
            self.budget.settle_call_permit(permit, outcome=outcome)
            self.event_log.emit(
                "llm_call",
                agent_id=FINALIZER_ID,
                payload={
                    **permit.as_dict(),
                    "step": self._provider_calls,
                    "call_kind": "team_synthesis",
                    "outcome": outcome,
                    "duration_seconds": time.monotonic() - started_at,
                    "error_type": type(exc).__name__,
                },
                parent_event_ids=[attempted["event_id"]],
                outcome=outcome,
                budget_progress=self.budget.snapshot(),
                artifact_refs=[request_transcript["transcript_id"]],
            )
            return None
        self.budget.settle_call_permit(permit, outcome="succeeded", usage=response.usage)
        self._last_provider_failed = False
        response_transcript = self.transcript_log.response(
            agent_id=FINALIZER_ID,
            step=self._provider_calls,
            permit_id=permit.permit_id,
            content=response.content,
            tool_calls=response.tool_calls,
            model_metadata=response.model_metadata,
            parent_refs=[request_transcript["transcript_id"]],
        )
        self._last_event_id = self.event_log.emit(
            "llm_call",
            agent_id=FINALIZER_ID,
            payload={
                **permit.as_dict(),
                "step": self._provider_calls,
                "call_kind": "team_synthesis",
                "outcome": "succeeded",
                "model": response.usage.model,
                "model_metadata": response.model_metadata,
                "tool_calls": len(response.tool_calls),
                "duration_seconds": time.monotonic() - started_at,
                "call_role": classify_call_role(
                    (call["name"] for call in response.tool_calls),
                    finalization_active=True,
                ),
                "output_tokens": response.usage.output_tokens,
                "max_output_tokens": getattr(self.llm, "max_tokens", None),
                "finish_reason": response.model_metadata.get("finish_reason"),
            },
            token_usage=response.usage.as_dict(),
            parent_event_ids=[attempted["event_id"]],
            outcome="succeeded",
            budget_progress=self.budget.snapshot(),
            artifact_refs=[request_transcript["transcript_id"], response_transcript["transcript_id"]],
        )["event_id"]
        return response

    # ---------------------------------------------------------------- dispatch

    def _handle_response(self, response, sandbox: AgentSandbox, known_raw_ids: set[str], records):
        """Returns (accepted_outcome_or_None, [(message, event_id), ...])."""
        results: list[tuple[dict[str, Any], str | None]] = []
        if response.tool_calls:
            self._messages.append(
                {
                    "role": "assistant",
                    "content": response.content or "",
                    "tool_calls": [
                        {"id": call["id"], "type": "function", "function": {"name": call["name"], "arguments": call["arguments"]}}
                        for call in response.tool_calls
                    ],
                }
            )
            for call in response.tool_calls:
                message, event_id, accepted = self._dispatch_tool(call, sandbox, known_raw_ids, records)
                results.append((message, event_id))
                if accepted is not None:
                    return accepted, results
            return None, results
        content = (response.content or "").strip()
        if content:
            maybe = _parse_synthesis_content(content)
            if maybe is not None:
                message, event_id, accepted = self._try_submit(maybe, call_id=None, known_raw_ids=known_raw_ids, records=records)
                if accepted is not None:
                    return accepted, [(message, event_id)]
                results.append((message, event_id))
                return None, results
            results.append(
                (
                    {"role": "user", "content": "Call submit_team_findings with the complete JSON payload (final findings plus one decision per raw candidate)."},
                    self._last_event_id,
                )
            )
            return None, results
        results.append(
            (
                {"role": "user", "content": "Call submit_team_findings with the complete JSON payload (final findings plus one decision per raw candidate)."},
                self._last_event_id,
            )
        )
        return None, results

    def _dispatch_tool(self, call: dict[str, Any], sandbox: AgentSandbox, known_raw_ids: set[str], records):
        name = call.get("name")
        raw_arguments = call.get("arguments") or "{}"
        if name not in _ALLOWED_TOOL_NAMES:
            event_id = self.event_log.emit(
                "prohibited_tool_attempt",
                agent_id=FINALIZER_ID,
                payload={
                    "requested_tool": name,
                    "call_id": call.get("id"),
                    "rejected_by": "synthesis_tool_gate",
                    "arguments_sha256": hashlib.sha256(raw_arguments.encode("utf-8")).hexdigest(),
                    "arguments_bytes": len(raw_arguments.encode("utf-8")),
                },
                parent_event_ids=[self._last_event_id] if self._last_event_id else None,
                outcome="rejected",
            )["event_id"]
            return (
                {"role": "tool", "tool_call_id": call.get("id"), "name": name, "content": json.dumps({"ok": False, "error": {"code": "prohibited_tool_during_synthesis", "message": "Only read_file and submit_team_findings may be dispatched in the synthesis phase."}})},
                event_id,
                None,
            )
        try:
            args = json.loads(raw_arguments) if raw_arguments else {}
        except json.JSONDecodeError:
            return (
                {"role": "tool", "tool_call_id": call.get("id"), "name": name, "content": json.dumps({"ok": False, "error": {"code": "invalid_json", "message": "Tool arguments must be valid JSON."}})},
                self._last_event_id,
                None,
            )
        if name == "read_file":
            return self._dispatch_read(call, args, sandbox)
        return self._try_submit(args, call_id=call.get("id"), known_raw_ids=known_raw_ids, records=records)

    def _dispatch_read(self, call: dict[str, Any], args: dict[str, Any], sandbox: AgentSandbox):
        requested_path = args.get("path") if isinstance(args, dict) else None
        if not isinstance(requested_path, str) or normalize_target_relative_path(requested_path) not in self._allowed_read_paths:
            event_id = self.event_log.emit(
                "prohibited_tool_attempt",
                agent_id=FINALIZER_ID,
                payload={"requested_tool": "read_file", "rejected_by": "synthesis_raw_anchor_scope", "call_id": call.get("id")},
                parent_event_ids=[self._last_event_id] if self._last_event_id else None,
                outcome="rejected",
            )["event_id"]
            return (
                {"role": "tool", "tool_call_id": call.get("id"), "name": "read_file", "content": json.dumps({"ok": False, "error": {"code": "outside_raw_candidate_scope"}})},
                event_id,
                None,
            )
        if self._reads_used >= self.read_file_cap:
            event_id = self.event_log.emit(
                "prohibited_tool_attempt",
                agent_id=FINALIZER_ID,
                payload={
                    "requested_tool": "read_file",
                    "call_id": call.get("id"),
                    "rejected_by": "synthesis_read_cap",
                    "reads_used": self._reads_used,
                    "read_file_cap": self.read_file_cap,
                },
                parent_event_ids=[self._last_event_id] if self._last_event_id else None,
                outcome="rejected",
            )["event_id"]
            return (
                {"role": "tool", "tool_call_id": call.get("id"), "name": "read_file", "content": json.dumps({"ok": False, "error": {"code": "read_allowance_exhausted", "message": "The bounded verification read allowance is exhausted."}})},
                event_id,
                None,
            )
        self._reads_used += 1
        dispatched = self.event_log.emit(
            "tool_call",
            agent_id=FINALIZER_ID,
            payload={"tool": "read_file", "arguments": args},
            parent_event_ids=[self._last_event_id] if self._last_event_id else None,
        )
        try:
            result = sandbox.read_file(args["path"])
            content = json.dumps({"evidence_ref": result["evidence_ref"], "path": result["path"], "content": result["content"][:11000]}, ensure_ascii=False)
        except Exception as exc:  # noqa: BLE001
            content = json.dumps({"error": str(exc)})
        return (
            {"role": "tool", "tool_call_id": call.get("id"), "name": "read_file", "content": content},
            dispatched["event_id"],
            None,
        )

    def _try_submit(self, args: Any, *, call_id, known_raw_ids: set[str], records):
        intake = validate_synthesis_payload(args, known_raw_ids, {record["raw_id"]: record["finding"] for record in records})
        errors = list(intake.errors)
        payload = intake.payload
        if payload is not None:
            available_paths = self._available_evidence_paths(records)
            errors.extend(validate_evidence_refs(payload, available_paths))
            for index, decision in enumerate(payload.get("raw_decisions", [])):
                for ref_index, reference in enumerate(decision.get("evidence_refs") or []):
                    if reference not in available_paths:
                        errors.append({"path": f"raw_decisions[{index}].evidence_refs[{ref_index}]", "message": "must reference snapshot-visible or finalizer file_read event"})
        if errors:
            rejected = self.event_log.emit(
                "team_findings_submission_rejected",
                agent_id=FINALIZER_ID,
                payload={"error_count": len(errors), "errors": errors[:64]},
                parent_event_ids=[self._last_event_id] if self._last_event_id else None,
                outcome="rejected",
            )
            self._last_event_id = rejected["event_id"]
            message = {"role": "tool" if call_id else "user", "tool_call_id": call_id, "name": "submit_team_findings", "content": "Your synthesis payload was rejected. Correct it and call submit_team_findings again: " + json.dumps(errors[:32], ensure_ascii=False)}
            if not call_id:
                message.pop("tool_call_id")
                message.pop("name")
            return (message, self._last_event_id, None)
        assert payload is not None
        payload_sha256 = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        final_artifact = self.layout.artifacts / "team_final_findings.json"
        final_artifact.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        dispositions = self._dispositions_from_decisions(records, payload)
        (self.layout.artifacts / "raw_disposition.json").write_text(
            json.dumps({"schema_version": "t-pilot-2-raw-disposition-v1", "source": "finalizer_explicit_decisions", "dispositions": dispositions}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        submitted = self.event_log.emit(
            "team_findings_submitted",
            agent_id=FINALIZER_ID,
            payload={
                "final_finding_count": len(payload.get("findings", [])),
                "raw_decision_counts": _decision_counts(payload.get("raw_decisions", [])),
                "payload_sha256": payload_sha256,
                "artifact_sha256": hashlib.sha256(final_artifact.read_bytes()).hexdigest(),
                "read_file_calls": self._reads_used,
                "provider_calls": self._provider_calls,
            },
            parent_event_ids=[self._last_event_id] if self._last_event_id else None,
            outcome="accepted",
        )
        self._last_event_id = submitted["event_id"]
        delta = self._mechanical_delta(records, payload.get("findings", []), payload.get("raw_decisions", []))
        (self.layout.artifacts / "synthesis_delta.json").write_text(
            json.dumps(delta, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        message = (
            {"role": "tool", "tool_call_id": call_id, "name": "submit_team_findings", "content": json.dumps({"ok": True, "final_finding_count": len(payload.get("findings", []))})}
            if call_id
            else {"role": "user", "content": json.dumps({"ok": True, "final_finding_count": len(payload.get("findings", []))})}
        )
        return (
            message,
            self._last_event_id,
            SynthesisOutcome(
                status="completed",
                reason=None,
                final_payload=payload,
                raw_dispositions=dispositions,
                delta=delta,
                provider_calls=self._provider_calls,
                provider_failures=self._provider_failures,
                read_file_calls=self._reads_used,
                model_snapshot_sha256=self._model_snapshot_sha256,
            ),
        )

    # ---------------------------------------------------------------- helpers

    def _available_evidence_paths(self, records: list[dict[str, Any]]) -> dict[str, str]:
        """Finalizer's own reads plus the snapshot-anchored foreign refs."""
        available: dict[str, str] = {}
        for event in self.event_log.read_all():
            if event.get("event_type") == "file_read" and event.get("agent_id") == FINALIZER_ID:
                available[event["event_id"]] = str((event.get("payload") or {}).get("path") or "")
        for record in records:
            for reference, path in record["evidence_map"].items():
                if reference and path:
                    available.setdefault(reference, path)
        return available

    def _dispositions_from_decisions(self, records: list[dict[str, Any]], payload: dict[str, Any]) -> list[dict[str, Any]]:
        decisions = {decision["raw_id"]: decision for decision in payload.get("raw_decisions", [])}
        dispositions: list[dict[str, Any]] = []
        for record in records:
            decision = decisions.get(record["raw_id"], {})
            dispositions.append(
                {
                    "raw_id": record["raw_id"],
                    "submitted_by": record["submitted_by"],
                    "action": decision.get("action"),
                    "target_final_id": decision.get("target_final_id"),
                    "merged_with": decision.get("merged_with"),
                    "evidence_refs": decision.get("evidence_refs", []),
                    "evidence_refs_empty": not decision.get("evidence_refs"),
                    "rationale": decision.get("rationale"),
                }
            )
        return dispositions

    def _degrade(self, records: list[dict[str, Any]], reason: str) -> SynthesisOutcome:
        self.event_log.emit(
            "synthesis_degraded",
            agent_id=FINALIZER_ID,
            payload={"reason": reason, "provider_calls": self._provider_calls, "provider_failures": self._provider_failures},
            parent_event_ids=[self._last_event_id] if self._last_event_id else None,
            outcome="degraded",
        )
        union = []
        for record in records:
            item = dict(record["finding"])
            item.setdefault("submitted_by", record["submitted_by"])
            union.append(item)
        payload = {"schema_version": "deterministic-union", "mode": "synthesis_degraded", "reason": reason, "findings": union}
        (self.layout.artifacts / "team_final_findings.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        dispositions = [
            {
                "raw_id": record["raw_id"],
                "submitted_by": record["submitted_by"],
                "action": "retain",
                "target_final_id": None,
                "merged_with": None,
                "evidence_refs": list((record["finding"].get("evidence_refs") or [])),
                "evidence_refs_empty": not (record["finding"].get("evidence_refs") or []),
                "rationale": "synthesis degraded to deterministic union; no finalizer decision",
            }
            for record in records
        ]
        (self.layout.artifacts / "raw_disposition.json").write_text(
            json.dumps({"schema_version": "t-pilot-2-raw-disposition-v1", "source": "degraded_union", "reason": reason, "dispositions": dispositions}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        self.budget.mark_agent_terminal(FINALIZER_ID)
        self.budget.close_synthesis_phase()
        delta = self._mechanical_delta(records, union, [])
        delta["degraded"] = True
        delta["degrade_reason"] = reason
        (self.layout.artifacts / "synthesis_delta.json").write_text(
            json.dumps(delta, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return SynthesisOutcome(
            status="degraded",
            reason=reason,
            final_payload=payload,
            raw_dispositions=dispositions,
            delta=delta,
            provider_calls=self._provider_calls,
            provider_failures=self._provider_failures,
            read_file_calls=self._reads_used,
            model_snapshot_sha256=self._model_snapshot_sha256,
        )

    def _mechanical_delta(
        self,
        records: list[dict[str, Any]],
        final_findings: list[dict[str, Any]],
        raw_decisions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        by_raw = {record["raw_id"]: record for record in records}
        final_by_id = {finding.get("final_id"): finding for finding in final_findings}
        corrections: list[dict[str, Any]] = []
        for decision in raw_decisions:
            action = decision.get("action")
            if action not in {"correct", "retain"}:
                continue
            record = by_raw.get(decision.get("raw_id"))
            target = final_by_id.get(decision.get("target_final_id"))
            if record is None or target is None:
                continue
            changed = []
            for field_name in _CORRECTION_FIELDS:
                if _normalizable(record["finding"].get(field_name)) != _normalizable(target.get(field_name)):
                    changed.append(field_name)
            if (record["finding"].get("guard") or {}).get("kind") != (target.get("guard") or {}).get("kind"):
                changed.append("guard.kind")
            if changed:
                corrections.append({"raw_id": decision["raw_id"], "action": action, "changed_fields": sorted(set(changed))})
        foreign_refs_used = sorted(
            {
                reference
                for finding in final_findings
                for reference in (finding.get("evidence_refs") or [])
                if reference in {ref for record in records for ref in record["evidence_map"]}
            }
        )
        return {
            "schema_version": "t-pilot-2-synthesis-delta-v1",
            "raw_finding_count": len(records),
            "final_finding_count": len(final_findings),
            "raw_decision_counts": _decision_counts(raw_decisions),
            "corrections_field_diffs": corrections,
            "dropped_raw_ids": sorted(
                decision["raw_id"] for decision in raw_decisions if decision.get("action") == "drop"
            ),
            "drop_decisions_with_empty_evidence_refs": sorted(
                decision["raw_id"]
                for decision in raw_decisions
                if decision.get("action") == "drop" and not decision.get("evidence_refs")
            ),
            "final_evidence_refs_citing_raw_evidence": foreign_refs_used,
            "derived_from_empty_rejections_possible": False,
        }


def _decision_counts(decisions: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"retain": 0, "merge": 0, "correct": 0, "drop": 0}
    for decision in decisions:
        action = decision.get("action")
        if action in counts:
            counts[action] += 1
    return counts


def _normalizable(value: Any) -> Any:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str) if isinstance(value, (dict, list)) else value


def _parse_synthesis_content(content: str) -> Any:
    text = content.strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            parsed = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    if isinstance(parsed, dict) and "findings" in parsed:
        return parsed
    return None
