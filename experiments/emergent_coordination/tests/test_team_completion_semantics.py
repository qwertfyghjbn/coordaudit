"""Pure mock validation for the Candidate E team-completion draft.

This file deliberately does not import a provider client or the live experiment
runner.  It tests the proposed state-machine and lineage invariants with a
small deterministic fixture so that semantic regressions are caught before any
S/P/B/T/M calibration is authorized.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest


class GateDenied(RuntimeError):
    pass


class MockPermitLedger:
    def __init__(self, granted: int, reserve: int):
        self.granted = granted
        self.consumed = 0
        self.reserve = reserve

    @property
    def remaining(self) -> int:
        return self.granted - self.consumed

    def consume(self) -> None:
        if self.remaining <= 0:
            raise RuntimeError("no team permit")
        self.consumed += 1

    def at_safety_boundary(self) -> bool:
        return self.remaining <= self.reserve


@dataclass
class MockLineage:
    stages: dict[str, str] = field(default_factory=dict)
    history: list[tuple[str, str]] = field(default_factory=list)
    labels: dict[str, set[str]] = field(default_factory=dict)
    producers: dict[str, set[str]] = field(default_factory=dict)

    def set(self, ref: str, stage: str) -> None:
        self.stages[ref] = stage
        self.history.append((ref, stage))

    def require(self, ref: str, stage: str) -> None:
        assert self.stages.get(ref) == stage

    def label(self, ref: str, value: str) -> None:
        self.labels.setdefault(ref, set()).add(value)


class MockProvider:
    """A provider-shaped recorder; it has no network or API implementation."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def call(self, agent: str, action: str, ledger: MockPermitLedger) -> None:
        ledger.consume()
        self.calls.append((agent, action))


@dataclass
class MockTeam:
    agents: tuple[str, ...] = ("a", "b", "c", "d")
    permits: int = 12
    reserve: int = 2
    drain_max_ticks: int = 8
    statuses: dict[str, str] = field(init=False)
    local_submission: dict[str, str] = field(init=False)
    phase: str = field(default="normal", init=False)
    event_seq: int = field(default=0, init=False)
    cutoff: int | None = field(default=None, init=False)
    queue: list[tuple[int, str, str | None]] = field(default_factory=list, init=False)
    late_events: list[tuple[int, str, str | None]] = field(default_factory=list, init=False)
    provider: MockProvider = field(default_factory=MockProvider, init=False)
    lineage: MockLineage = field(default_factory=MockLineage, init=False)
    ledger: MockPermitLedger = field(init=False)
    prohibited: list[tuple[str, str]] = field(default_factory=list, init=False)
    convergence: dict[str, bool] = field(default_factory=dict, init=False)
    exploration_after_convergence: dict[str, int] = field(default_factory=dict, init=False)
    obligations: set[str] = field(default_factory=set, init=False)
    validator_accepts: bool = field(default=True, init=False)
    adopted: set[str] = field(default_factory=set, init=False)

    def __post_init__(self) -> None:
        self.statuses = {agent: "active" for agent in self.agents}
        self.local_submission = {agent: "none" for agent in self.agents}
        self.ledger = MockPermitLedger(self.permits, self.reserve)

    def model_call(self, agent: str, action: str) -> None:
        if self.phase == "hard_finalization" and action != "submit_findings":
            self.prohibited.append((agent, action))
            raise GateDenied(action)
        self.provider.call(agent, action, self.ledger)

    def local_report(self, agent: str) -> None:
        self.local_submission[agent] = "reported"

    def local_submit(self, agent: str) -> bool:
        if self.phase == "hard_finalization":
            self.model_call(agent, "submit_findings")
        accepted = self.validator_accepts
        self.local_submission[agent] = "accepted" if accepted else "rejected"
        return accepted

    def set_waiting(self, agent: str) -> None:
        assert self.statuses[agent] != "hard_finalizing"
        self.statuses[agent] = "waiting"

    def resume(self, agent: str) -> None:
        if self.statuses[agent] == "hard_finalizing":
            raise GateDenied("resume")
        assert self.statuses[agent] == "waiting"
        self.statuses[agent] = "active"

    def mark_done(self, agent: str) -> None:
        self.statuses[agent] = "done"

    def produce(self, ref: str, producer: str | None = None) -> None:
        self.lineage.set(ref, "produced")
        if producer is not None:
            self.lineage.producers.setdefault(ref, set()).add(producer)

    def queue_info(self, ref: str) -> None:
        self.lineage.require(ref, "produced")
        self.lineage.set(ref, "queued")

    def emit(self, kind: str, ref: str | None = None) -> int:
        self.event_seq += 1
        self.queue.append((self.event_seq, kind, ref))
        return self.event_seq

    def freeze_if_boundary(self) -> bool:
        if self.phase == "normal" and self.ledger.at_safety_boundary():
            self.phase = "freeze"
            self.cutoff = self.event_seq
            return True
        return False

    def freeze(self) -> None:
        self.phase = "freeze"
        self.cutoff = self.event_seq

    def drain(self) -> None:
        assert self.phase == "freeze"
        self.phase = "drain"
        ticks = 0
        remaining: list[tuple[int, str, str | None]] = []
        for event in self.queue:
            seq, kind, ref = event
            if self.cutoff is None or seq > self.cutoff:
                self.late_events.append(event)
                continue
            if ticks >= self.drain_max_ticks:
                remaining.append(event)
                continue
            ticks += 1
            if kind in {"report", "message", "artifact_visibility"} and ref:
                if self.lineage.stages.get(ref) == "queued":
                    self.lineage.set(ref, "delivered")
            elif kind == "task_close":
                self.obligations.discard(ref or "")
            elif kind == "semantic_adopt":
                raise AssertionError("drain must never perform semantic adoption")
        self.queue = remaining

    def hard_finalize(self, agents: tuple[str, ...] | None = None) -> None:
        assert self.phase == "drain"
        self.phase = "hard_finalization"
        for agent in agents or self.agents:
            if self.statuses[agent] != "done":
                self.statuses[agent] = "hard_finalizing"

    def adopt(self, ref: str) -> None:
        self.lineage.require(ref, "model_visible")
        self.lineage.set(ref, "adopted")
        self.adopted.add(ref)

    def make_model_visible(self, ref: str) -> None:
        assert self.lineage.stages.get(ref) == "delivered"
        self.lineage.set(ref, "model_visible")

    def outcome(self) -> tuple[str, str]:
        forced = self.phase == "hard_finalization" or bool(self.obligations)
        return ("forced_complete" if forced else "clean_complete", "valid")


def _boundary_team() -> MockTeam:
    team = MockTeam(permits=4, reserve=2)
    team.model_call("a", "exploration")
    team.model_call("b", "exploration")
    assert team.freeze_if_boundary()
    return team


def test_GEN01_all_agents_naturally_complete() -> None:
    team = MockTeam(agents=("a", "b"))
    for agent in team.agents:
        assert team.local_submit(agent)
        team.mark_done(agent)
    assert team.phase == "normal"
    assert team.provider.calls == []
    assert team.outcome() == ("clean_complete", "valid")


def test_GEN02_one_agent_keeps_exploring() -> None:
    team = _boundary_team()
    team.drain()
    team.hard_finalize(("a",))
    team.mark_done("b")
    assert team.statuses == {"a": "hard_finalizing", "b": "done", "c": "active", "d": "active"}
    assert team.outcome() == ("forced_complete", "valid")
    assert len(team.provider.calls) == 2


def test_GEN03_convergence_without_behavioral_stopping() -> None:
    team = MockTeam(agents=("a",))
    team.convergence["a"] = True
    team.exploration_after_convergence["a"] = 3
    assert team.convergence["a"] is True
    assert team.exploration_after_convergence["a"] == 3
    assert team.statuses["a"] == "active"


def test_GEN04_validator_rejection_does_not_reopen_exploration() -> None:
    team = MockTeam(agents=("a",), permits=0, reserve=0)
    team.validator_accepts = False
    assert not team.local_submit("a")
    assert team.local_submission["a"] == "rejected"
    assert team.provider.calls == []
    with pytest.raises(RuntimeError):
        team.model_call("a", "submission_repair")


def test_GEN05_hard_gate_rejects_non_submit_dispatch() -> None:
    team = _boundary_team()
    team.drain()
    team.hard_finalize(("a",))
    with pytest.raises(GateDenied):
        team.model_call("a", "read_file")
    assert team.prohibited == [("a", "read_file")]
    team.local_submit("a")


def test_GEN06_drain_reconciles_without_model_call_or_adoption() -> None:
    team = _boundary_team()
    team.produce("r1")
    team.queue_info("r1")
    team.emit("report", "r1")
    team.freeze()
    calls = list(team.provider.calls)
    team.drain()
    assert team.lineage.stages["r1"] == "delivered"
    assert team.provider.calls == calls
    assert "r1" not in team.adopted


def test_GEN07_drain_does_not_expand_for_late_event() -> None:
    team = _boundary_team()
    team.freeze()
    team.emit("report", "late")
    team.drain()
    assert len(team.late_events) == 1
    assert team.queue == []


def test_GEN08_hard_finalization_rejects_resume() -> None:
    team = _boundary_team()
    team.set_waiting("a")
    team.drain()
    team.hard_finalize(("a",))
    with pytest.raises(GateDenied):
        team.resume("a")


def test_GEN09_simultaneous_submit_order_is_explicit() -> None:
    team = MockTeam(agents=("a", "b"))
    assert team.local_submit("a")
    assert team.local_submit("b")
    assert team.local_submission == {"a": "accepted", "b": "accepted"}


def test_P01_three_done_one_active_is_not_implicit_team_completion() -> None:
    team = MockTeam()
    for agent in ("a", "b", "c"):
        team.local_submit(agent)
        team.mark_done(agent)
    assert team.statuses["d"] == "active"
    assert team.outcome() == ("clean_complete", "valid")
    assert team.statuses["d"] != "done"


def test_P02_early_submit_does_not_end_team() -> None:
    team = MockTeam(agents=("a", "b"))
    team.local_submit("a")
    team.mark_done("a")
    team.produce("strong-b")
    assert team.statuses["b"] == "active"
    assert team.lineage.stages["strong-b"] == "produced"


def test_P03_simultaneous_submission_has_no_implicit_merge() -> None:
    team = MockTeam(agents=("a", "b"))
    team.local_submit("b")
    team.local_submit("a")
    assert team.local_submission == {"a": "accepted", "b": "accepted"}
    assert not hasattr(team, "merged_findings")


def test_B01_written_evidence_remains_available_after_writer_local_report() -> None:
    team = MockTeam(agents=("a", "b"))
    team.produce("shared-1")
    team.queue_info("shared-1")
    team.local_report("a")
    assert team.lineage.stages["shared-1"] == "queued"
    assert team.local_submission["a"] == "reported"


def test_B02_unread_artifact_is_not_alone_a_blocking_obligation() -> None:
    team = MockTeam(agents=("a", "b"))
    team.produce("unused")
    team.queue_info("unused")
    team.mark_done("a")
    team.mark_done("b")
    assert team.obligations == set()
    assert team.outcome() == ("clean_complete", "valid")


def test_B03_post_finalization_shared_read_is_rejected() -> None:
    team = _boundary_team()
    team.drain()
    team.hard_finalize(("a",))
    with pytest.raises(GateDenied):
        team.model_call("a", "shared_read")


def test_B04_write_visibility_can_reconcile_without_call() -> None:
    team = _boundary_team()
    team.produce("artifact")
    team.queue_info("artifact")
    team.emit("artifact_visibility", "artifact")
    team.freeze()
    before = len(team.provider.calls)
    team.drain()
    assert team.lineage.stages["artifact"] == "delivered"
    assert len(team.provider.calls) == before


def test_T01_terminal_tasks_can_close_without_scheduler_created_work() -> None:
    team = MockTeam(agents=("a",))
    team.obligations.clear()
    team.mark_done("a")
    assert team.outcome() == ("clean_complete", "valid")


def test_T02_active_task_owner_waiting_is_not_clean_completion() -> None:
    team = MockTeam(agents=("a",))
    team.obligations.add("task-1")
    team.set_waiting("a")
    assert team.outcome() == ("forced_complete", "valid")


def test_T03_terminal_task_report_can_be_transport_reconciled() -> None:
    team = _boundary_team()
    team.produce("task-report")
    team.queue_info("task-report")
    team.emit("report", "task-report")
    team.freeze()
    team.drain()
    assert team.lineage.stages["task-report"] == "delivered"


def test_T04_claim_before_freeze_is_not_a_drain_side_effect() -> None:
    team = MockTeam(agents=("a",), permits=3, reserve=1)
    team.model_call("a", "claim_task")
    assert team.provider.calls == [("a", "claim_task")]
    team.freeze_if_boundary()
    assert team.phase == "normal"


def test_T05_unclaimed_backlog_does_not_get_runtime_assigned() -> None:
    team = _boundary_team()
    team.obligations.add("unclaimed-1")
    team.drain()
    team.hard_finalize(("a",))
    assert team.obligations == {"unclaimed-1"}
    assert team.outcome() == ("forced_complete", "valid")


def test_M01_manager_can_submit_after_all_reports_are_received() -> None:
    team = MockTeam(agents=("manager", "worker"))
    team.local_report("worker")
    team.local_submit("manager")
    team.mark_done("manager")
    team.mark_done("worker")
    assert team.outcome() == ("clean_complete", "valid")


def test_M02_pending_worker_report_prevents_clean_completion() -> None:
    team = MockTeam(agents=("manager", "worker"))
    team.obligations.add("pending-report")
    team.local_submit("manager")
    assert team.outcome() == ("forced_complete", "valid")


def test_M03_waiting_worker_without_assignment_is_not_done() -> None:
    team = MockTeam(agents=("manager", "worker"))
    team.set_waiting("worker")
    assert team.statuses["worker"] == "waiting"
    assert team.statuses["worker"] != "done"
    assert team.provider.calls == []


def test_M04_reassignment_after_freeze_is_rejected() -> None:
    team = _boundary_team()
    team.drain()
    team.hard_finalize(("a",))
    with pytest.raises(GateDenied):
        team.model_call("a", "manager_reassign")


def test_M05_manager_convergence_does_not_end_running_worker() -> None:
    team = MockTeam(agents=("manager", "worker"))
    team.convergence["manager"] = True
    assert team.statuses["worker"] == "active"
    assert team.statuses["manager"] == "active"


def test_M06_worker_evidence_delivery_does_not_summarize_for_manager() -> None:
    team = _boundary_team()
    team.produce("worker-evidence")
    team.queue_info("worker-evidence")
    team.emit("report", "worker-evidence")
    team.freeze()
    team.drain()
    assert team.lineage.stages["worker-evidence"] == "delivered"
    assert "worker-evidence" not in team.adopted


def test_M07_late_report_is_recorded_without_mutating_accepted_state() -> None:
    team = MockTeam(agents=("manager", "worker"))
    team.local_submit("manager")
    accepted_before = team.local_submission["manager"]
    team.freeze()
    team.produce("late")
    team.queue_info("late")
    team.emit("report", "late")
    team.drain()
    assert team.local_submission["manager"] == accepted_before
    assert team.late_events


def test_BUD01_zero_permits_still_allows_bounded_transport_only() -> None:
    team = MockTeam(agents=("a",), permits=0, reserve=0)
    team.produce("pending")
    team.queue_info("pending")
    team.emit("report", "pending")
    team.freeze()
    team.drain()
    assert team.lineage.stages["pending"] == "delivered"
    assert team.provider.calls == []


def test_BUD02_zero_permits_cannot_buy_manager_report_processing_call() -> None:
    team = MockTeam(agents=("manager",), permits=0, reserve=0)
    with pytest.raises(RuntimeError):
        team.model_call("manager", "process_report")
    assert team.provider.calls == []


def test_BUD03_last_permit_timeout_is_accounted_without_overdraft() -> None:
    team = MockTeam(agents=("worker",), permits=1, reserve=0)
    team.model_call("worker", "timeout")
    assert team.ledger.remaining == 0
    with pytest.raises(RuntimeError):
        team.model_call("worker", "retry")


def test_BUD04_zero_permit_submission_repair_is_denied() -> None:
    team = MockTeam(agents=("a",), permits=0, reserve=0)
    team.validator_accepts = False
    assert not team.local_submit("a")
    with pytest.raises(RuntimeError):
        team.model_call("a", "submission_repair")


def test_BUD05_last_permit_is_atomic_and_not_topology_prioritized() -> None:
    team = MockTeam(agents=("a", "b"), permits=1, reserve=0)
    team.model_call("a", "exploration")
    with pytest.raises(RuntimeError):
        team.model_call("b", "exploration")
    assert team.provider.calls == [("a", "exploration")]


def test_EVD01_delivered_unadopted_at_close() -> None:
    team = _boundary_team()
    team.produce("r1")
    team.queue_info("r1")
    team.emit("report", "r1")
    team.freeze()
    team.drain()
    team.lineage.label("r1", "delivered_unadopted_at_close")
    assert team.lineage.stages["r1"] == "delivered"
    assert "r1" not in team.adopted
    assert "delivered_unadopted_at_close" in team.lineage.labels["r1"]
    assert team.lineage.history[-1] == ("r1", "delivered")


def test_EVD02_model_visible_does_not_imply_adoption() -> None:
    team = MockTeam(agents=("manager",))
    team.produce("r2")
    team.queue_info("r2")
    team.emit("report", "r2")
    team.freeze()
    team.drain()
    team.make_model_visible("r2")
    assert team.lineage.stages["r2"] == "model_visible"
    assert "r2" not in team.adopted


def test_EVD03_explicit_adoption_before_freeze_is_preserved() -> None:
    team = MockTeam(agents=("manager",))
    team.produce("r3")
    team.queue_info("r3")
    team.emit("report", "r3")
    # The manager explicitly sees and adopts the report before the team freeze.
    team.lineage.set("r3", "delivered")
    team.make_model_visible("r3")
    team.adopt("r3")
    team.freeze()
    team.drain()
    assert team.lineage.stages["r3"] == "adopted"
    assert "r3" in team.adopted


def test_EVD04_store_visibility_does_not_mean_agent_read() -> None:
    team = _boundary_team()
    team.produce("artifact")
    team.queue_info("artifact")
    team.emit("artifact_visibility", "artifact")
    team.freeze()
    team.drain()
    team.lineage.label("artifact", "visible_at_close")
    assert team.lineage.stages["artifact"] == "delivered"
    assert "visible_at_close" in team.lineage.labels["artifact"]
    assert "artifact" not in team.adopted
    assert team.obligations == set()


def test_EVD05_late_contradiction_does_not_mutate_accepted_payload() -> None:
    team = MockTeam(agents=("manager", "worker"))
    team.local_submit("manager")
    accepted = team.local_submission["manager"]
    team.freeze()
    team.produce("contradiction")
    team.queue_info("contradiction")
    team.emit("report", "contradiction")
    team.drain()
    team.lineage.label("contradiction", "contradiction_after_close")
    assert team.local_submission["manager"] == accepted
    assert team.lineage.stages["contradiction"] == "queued"
    assert "contradiction_after_close" in team.lineage.labels["contradiction"]
    assert team.late_events[-1][1:] == ("report", "contradiction")


def test_EVD06_duplicate_producers_preserve_provenance_without_runtime_dedup() -> None:
    team = MockTeam(agents=("a", "b", "manager"))
    for producer, ref in (("a", "a-evidence"), ("b", "b-evidence")):
        team.produce(ref, producer=producer)
        team.queue_info(ref)
        team.emit("report", ref)
    team.freeze()
    team.drain()
    for ref in ("a-evidence", "b-evidence"):
        team.make_model_visible(ref)
    team.adopt("a-evidence")
    assert team.adopted == {"a-evidence"}
    assert team.lineage.stages["b-evidence"] == "model_visible"
    assert team.lineage.producers == {"a-evidence": {"a"}, "b-evidence": {"b"}}


# The following cases are deliberately test-only lifecycle probes.  They do
# not add a runtime completion policy; they pin the distinctions that a future
# M4 topology contract must preserve.


def test_M4_report_is_produced_and_queued_before_freeze_but_not_model_visible() -> None:
    team = MockTeam(agents=("manager", "worker"), permits=1, reserve=1)
    team.produce("worker-report", producer="worker")
    team.queue_info("worker-report")
    team.emit("report", "worker-report")
    assert team.lineage.stages["worker-report"] == "queued"
    team.freeze()
    team.drain()
    assert team.lineage.stages["worker-report"] == "delivered"
    assert "worker-report" not in team.adopted
    assert team.lineage.stages["worker-report"] != "model_visible"


def test_M4_delivered_report_needs_explicit_visibility_then_adoption() -> None:
    team = MockTeam(agents=("manager", "worker"), permits=1, reserve=1)
    team.produce("worker-report", producer="worker")
    team.queue_info("worker-report")
    team.emit("report", "worker-report")
    team.freeze()
    team.drain()
    team.make_model_visible("worker-report")
    assert "worker-report" not in team.adopted
    team.adopt("worker-report")
    assert team.lineage.stages["worker-report"] == "adopted"


def test_M4_manager_second_list_tasks_is_rejected_after_hard_finalization() -> None:
    team = MockTeam(agents=("manager", "worker"), permits=2, reserve=1)
    team.model_call("manager", "manager_list_tasks")
    team.freeze()
    team.drain()
    team.hard_finalize(("manager",))
    with pytest.raises(GateDenied):
        team.model_call("manager", "manager_list_tasks")
    assert team.prohibited == [("manager", "manager_list_tasks")]
    assert team.provider.calls == [("manager", "manager_list_tasks")]


def test_M4_waiting_worker_is_not_done_and_resume_requires_lifecycle_event() -> None:
    team = MockTeam(agents=("manager", "worker"), permits=1, reserve=1)
    team.local_report("worker")
    team.set_waiting("worker")
    assert team.statuses["worker"] == "waiting"
    assert team.statuses["worker"] != "done"
    # This models an already-authorized assignment/resume event; it buys no
    # provider call and is legal before hard finalization.
    team.resume("worker")
    assert team.statuses["worker"] == "active"
    team.set_waiting("worker")
    team.freeze()
    team.drain()
    team.hard_finalize(("worker",))
    with pytest.raises(GateDenied):
        team.resume("worker")


def test_M4_late_worker_report_cannot_mutate_manager_accepted_submission() -> None:
    team = MockTeam(agents=("manager", "worker"))
    assert team.local_submit("manager")
    accepted = team.local_submission["manager"]
    team.freeze()
    team.produce("late-worker-report", producer="worker")
    team.queue_info("late-worker-report")
    team.emit("report", "late-worker-report")
    team.drain()
    assert team.local_submission["manager"] == accepted == "accepted"
    assert team.late_events[-1][1:] == ("report", "late-worker-report")


def test_candidate_e_bounded_drain_is_transport_only_and_no_call() -> None:
    team = MockTeam(agents=("manager", "worker"), permits=0, reserve=0)
    team.produce("queued-report", producer="worker")
    team.queue_info("queued-report")
    team.emit("report", "queued-report")
    team.freeze()
    before = list(team.provider.calls)
    team.drain()
    assert team.provider.calls == before == []
    assert team.lineage.stages["queued-report"] == "delivered"
    assert "queued-report" not in team.adopted


def test_candidate_coordinator_trigger_is_mock_only_and_does_not_buy_manager_call() -> None:
    team = MockTeam(agents=("manager", "worker"), permits=2, reserve=1)
    # A topology contract may expose a pre-existing coordinator-ready event.
    # This test only checks that the resulting lifecycle drain is no-call.
    team.model_call("manager", "coordinator_ready")
    before = list(team.provider.calls)
    team.freeze()
    team.drain()
    team.hard_finalize(("manager", "worker"))
    assert team.provider.calls == before


def test_current_per_agent_gate_baseline_records_truncated_manager_observation() -> None:
    team = MockTeam(agents=("manager", "worker"), permits=2, reserve=1)
    team.produce("report-1", producer="worker")
    team.queue_info("report-1")
    team.emit("report", "report-1")
    team.freeze()
    team.drain()
    team.hard_finalize(("manager",))
    with pytest.raises(GateDenied):
        team.model_call("manager", "manager_list_tasks")
    # Transport completed, but this baseline provides no model-visible or
    # adopted manager state after the gate.
    assert team.lineage.stages["report-1"] == "delivered"
    assert team.adopted == set()


def test_M4_fixture_does_not_silently_extend_steps_permits_or_drain_ticks() -> None:
    # The public calibration constants are explicit fixture inputs.  This
    # assertion is intentionally local to the mock and prevents a future M4
    # helper from quietly changing one of them to rescue the baseline.
    team = MockTeam(agents=("manager", "worker"), permits=12, reserve=8, drain_max_ticks=8)
    assert team.ledger.granted == 12
    assert team.ledger.reserve == 8
    assert team.drain_max_ticks == 8
    team.model_call("manager", "manager_list_tasks")
    assert team.ledger.remaining == 11
    assert not team.freeze_if_boundary()
