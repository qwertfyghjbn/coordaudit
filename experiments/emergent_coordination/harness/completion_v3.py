"""Explicit team-finalization contract for ``completion_v3``.

This module is deliberately independent from the frozen per-agent
``completion_v2`` gate.  It provides the small, auditable state machine used
by a team runtime: a team-owned reserved permit, a deterministic barrier,
transport-only drain, and an immutable final snapshot.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
import time
from typing import Any, Callable, Iterable, Mapping

COMPLETION_V3 = "completion_v3"
TEAM_COMPLETION_V3 = "team_completion_v3"
RESERVED_FINAL_SYNTHESIS_PERMITS = 1
TERMINAL_WORKER_STATES = frozenset({"done", "failed", "timed_out", "cancelled"})


class FinalizationState(str, Enum):
    NORMAL_WORK = "NORMAL_WORK"
    TEAM_FINALIZING = "TEAM_FINALIZING"
    FINAL_SNAPSHOT_READY = "FINAL_SNAPSHOT_READY"
    MANAGER_FINAL_SYNTHESIS = "MANAGER_FINAL_SYNTHESIS"
    TEAM_TERMINAL = "TEAM_TERMINAL"
    FORCED_UNFINISHED = "FORCED_UNFINISHED"


@dataclass(frozen=True)
class ReportRecord:
    report_id: str
    worker_id: str
    result: str
    evidence_refs: tuple[str, ...]
    transport_state: str = "produced"
    model_visible: bool = False
    adopted: bool = False
    late: bool = False


@dataclass(frozen=True)
class FinalTeamSnapshot:
    worker_terminal_states: Mapping[str, str]
    reports: tuple[ReportRecord, ...]
    failed_workers: tuple[str, ...]
    timed_out_workers: tuple[str, ...]
    cancelled_workers: tuple[str, ...]
    unresolved_tasks: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    completion_reason: str
    snapshot_sequence: int

    def as_payload(self) -> dict[str, Any]:
        return {
            "worker_terminal_states": dict(self.worker_terminal_states),
            "reports": [
                {
                    "report_id": report.report_id,
                    "worker_id": report.worker_id,
                    "result": report.result,
                    "evidence_refs": list(report.evidence_refs),
                    "transport_state": report.transport_state,
                    "model_visible": report.model_visible,
                    "adopted": report.adopted,
                    "late": report.late,
                }
                for report in self.reports
            ],
            "failed_workers": list(self.failed_workers),
            "timed_out_workers": list(self.timed_out_workers),
            "cancelled_workers": list(self.cancelled_workers),
            "unresolved_tasks": list(self.unresolved_tasks),
            "evidence_refs": list(self.evidence_refs),
            "completion_reason": self.completion_reason,
            "snapshot_sequence": self.snapshot_sequence,
        }


class ReportTransport:
    """Monotonic report transport with no semantic side effects."""

    def __init__(self) -> None:
        self._reports: dict[str, ReportRecord] = {}
        self._frozen = False
        self.late_report_ids: list[str] = []

    @property
    def reports(self) -> tuple[ReportRecord, ...]:
        return tuple(self._reports[key] for key in sorted(self._reports))

    def produce(self, report_id: str, worker_id: str, result: str, evidence_refs: Iterable[str] = ()) -> ReportRecord:
        if report_id in self._reports:
            raise ValueError(f"duplicate report: {report_id}")
        record = ReportRecord(report_id, worker_id, result, tuple(evidence_refs))
        self._reports[report_id] = record
        if self._frozen:
            self.late_report_ids.append(report_id)
            self._reports[report_id] = ReportRecord(**{**record.__dict__, "late": True})
        return self._reports[report_id]

    def queue(self, report_id: str) -> ReportRecord:
        return self._transition(report_id, "produced", "queued")

    def drain(self) -> tuple[str, ...]:
        delivered: list[str] = []
        for report_id, record in list(self._reports.items()):
            if record.transport_state == "queued":
                self._reports[report_id] = ReportRecord(**{**record.__dict__, "transport_state": "delivered"})
                delivered.append(report_id)
        return tuple(sorted(delivered))

    def freeze(self) -> None:
        self._frozen = True

    def mark_model_visible(self, report_ids: Iterable[str]) -> tuple[str, ...]:
        visible: list[str] = []
        for report_id in report_ids:
            record = self._reports[report_id]
            if record.transport_state not in {"delivered", "produced", "queued"}:
                raise ValueError(f"report is not eligible for model visibility: {report_id}")
            self._reports[report_id] = ReportRecord(**{**record.__dict__, "model_visible": True})
            visible.append(report_id)
        return tuple(sorted(visible))

    def adopt(self, report_id: str) -> None:
        record = self._reports[report_id]
        if not record.model_visible:
            raise ValueError("adoption requires actual model visibility")
        self._reports[report_id] = ReportRecord(**{**record.__dict__, "adopted": True})

    def _transition(self, report_id: str, expected: str, target: str) -> ReportRecord:
        record = self._reports[report_id]
        if record.transport_state != expected:
            raise ValueError(f"invalid report transition {record.transport_state}->{target}")
        self._reports[report_id] = ReportRecord(**{**record.__dict__, "transport_state": target})
        return self._reports[report_id]


class TeamFinalizationCoordinator:
    """Generic completion_v3 barrier; no architecture-specific policy branch."""

    def __init__(
        self,
        *,
        worker_ids: Iterable[str],
        reserved_permits: int = 1,
        finalization_deadline_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.worker_ids = tuple(worker_ids)
        if not self.worker_ids or len(set(self.worker_ids)) != len(self.worker_ids):
            raise ValueError("worker ids must be unique and non-empty")
        if reserved_permits != 1:
            raise ValueError("completion_v3 reserves exactly one final synthesis permit")
        if finalization_deadline_seconds <= 0:
            raise ValueError("finalization deadline must be positive")
        self.state = FinalizationState.NORMAL_WORK
        self.worker_states = {worker_id: "running" for worker_id in self.worker_ids}
        self.transport = ReportTransport()
        self.snapshot: FinalTeamSnapshot | None = None
        self._sequence = 0
        self._final_synthesis_started = False
        self.outcome: str | None = None
        self.finalization_deadline_seconds = float(finalization_deadline_seconds)
        self._clock = clock
        self._barrier_started_at: float | None = None

    def enter_barrier(self, worker_states: Mapping[str, str] | None = None) -> dict[str, str]:
        if self.state is not FinalizationState.NORMAL_WORK:
            raise RuntimeError(f"cannot enter barrier from {self.state}")
        if worker_states is not None:
            unknown = set(worker_states) - set(self.worker_ids)
            if unknown:
                raise ValueError(f"unknown workers: {sorted(unknown)}")
            self.worker_states.update(worker_states)
        self.state = FinalizationState.TEAM_FINALIZING
        self._barrier_started_at = self._clock()
        # Waiting workers have no remaining model work.  Running workers are
        # deterministically cancelled at the finite barrier boundary.
        for worker_id, status in self.worker_states.items():
            if status == "waiting_for_assignment":
                self.worker_states[worker_id] = "cancelled"
            elif status not in TERMINAL_WORKER_STATES:
                self.worker_states[worker_id] = "cancelled"
        return dict(self.worker_states)

    def drain_and_freeze(self, *, unresolved_tasks: Iterable[str] = (), reason: str = "barrier") -> FinalTeamSnapshot:
        if self.state is not FinalizationState.TEAM_FINALIZING:
            raise RuntimeError("team barrier is not active")
        self.transport.drain()
        self.transport.freeze()
        self._sequence += 1
        reports = self.transport.reports
        states = dict(sorted(self.worker_states.items()))
        self.snapshot = FinalTeamSnapshot(
            worker_terminal_states=MappingProxyType(states),
            reports=reports,
            failed_workers=tuple(sorted(worker for worker, state in states.items() if state == "failed")),
            timed_out_workers=tuple(sorted(worker for worker, state in states.items() if state == "timed_out")),
            cancelled_workers=tuple(sorted(worker for worker, state in states.items() if state == "cancelled")),
            unresolved_tasks=tuple(sorted(unresolved_tasks)),
            evidence_refs=tuple(sorted({ref for report in reports for ref in report.evidence_refs})),
            completion_reason=reason,
            snapshot_sequence=self._sequence,
        )
        self.state = FinalizationState.FINAL_SNAPSHOT_READY
        return self.snapshot

    def deadline_exceeded(self) -> bool:
        """Whether the bounded team-finalization window has elapsed."""
        if self._barrier_started_at is None:
            return False
        return self._clock() - self._barrier_started_at > self.finalization_deadline_seconds

    def finish_deadline(self) -> str:
        """Close without a model call when the v3 finalization window expires."""
        if self.state not in {FinalizationState.TEAM_FINALIZING, FinalizationState.FINAL_SNAPSHOT_READY}:
            raise RuntimeError("deadline can only close an active finalization")
        self.outcome = "forced_unfinished"
        self.state = FinalizationState.FORCED_UNFINISHED
        return self.outcome

    def begin_final_synthesis(self) -> FinalTeamSnapshot:
        if self.state is not FinalizationState.FINAL_SNAPSHOT_READY or self.snapshot is None:
            raise RuntimeError("final snapshot is not ready")
        if self._final_synthesis_started:
            raise RuntimeError("final synthesis is exactly-once")
        self._final_synthesis_started = True
        self.state = FinalizationState.MANAGER_FINAL_SYNTHESIS
        return self.snapshot

    def record_final_synthesis_request(self) -> tuple[str, ...]:
        """Mark reports visible at the exact point the request input is emitted."""
        if self.state is not FinalizationState.MANAGER_FINAL_SYNTHESIS or self.snapshot is None:
            raise RuntimeError("final synthesis request is not authorized")
        return self.transport.mark_model_visible(report.report_id for report in self.snapshot.reports)

    def finish(self, *, submitted: bool, worker_failure: bool = False) -> str:
        if self.state is not FinalizationState.MANAGER_FINAL_SYNTHESIS:
            raise RuntimeError("final synthesis has not started")
        self.outcome = "completed_with_worker_failure" if submitted and worker_failure else ("completed" if submitted else "forced_unfinished")
        self.state = FinalizationState.TEAM_TERMINAL if submitted else FinalizationState.FORCED_UNFINISHED
        return self.outcome
