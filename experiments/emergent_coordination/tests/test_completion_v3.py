from __future__ import annotations

import json

import pytest

from experiments.emergent_coordination.harness.budget import BudgetExhausted, BudgetTracker, TokenUsage
from experiments.emergent_coordination.harness.completion_v3 import (
    FinalizationState,
    TeamFinalizationCoordinator,
)
from experiments.emergent_coordination.harness.llm.client import LLMResponse, MockLLMClient
from experiments.emergent_coordination.harness.runner import RunConfig, run_experiment


def _call(name: str, arguments: dict, call_id: str) -> dict:
    return {"id": call_id, "name": name, "arguments": json.dumps(arguments)}


def _response(*calls: dict) -> LLMResponse:
    return LLMResponse(
        content=None,
        tool_calls=list(calls),
        usage=TokenUsage(input_tokens=1, output_tokens=1, model="mock"),
        raw={"mock": True},
        model_metadata={"finish_reason": "tool_calls"},
    )


def test_m4_completion_v3_uses_snapshot_and_exactly_one_reserved_call(tmp_path) -> None:
    manager_script = [
        _response(_call("manager_create_task", {"worker_id": f"agent_{i:03d}", "description": "review"}, f"m{i}"))
        for i in (2, 3, 4)
    ] + [_response(_call("manager_list_tasks", {}, f"list{i}")) for i in range(2)]
    manager_script.append(_response(_call("submit_findings", {"schema_version": "repository-v1", "findings": []}, "final")))
    scripts = {"agent_001": manager_script}
    for i in (2, 3, 4):
        scripts[f"agent_{i:03d}"] = [
            _response(_call("worker_get_assignment", {}, f"get{i}")),
            _response(_call("worker_report_task", {"task_id": f"manager_task_{i-1:04d}", "result": f"report-{i}", "evidence_refs": []}, f"report{i}")),
        ]
    llm = MockLLMClient(scripts=scripts)
    llm.max_tokens = 4096
    summary = run_experiment(
        RunConfig(
            mode="manager_worker", agent_count=4, model="mock", max_steps=64,
            max_provider_retries=1,
            budgets={"hard_team_call_permits": 12, "reserved_final_synthesis_permits": 1},
            completion_generation="completion_v3", team_completion_policy="team_completion_v3",
            team_finalization_deadline_seconds=60,
            runs_dir=tmp_path, case_id="flowise_3_1_3_repository_v1", evaluate=False,
        ),
        llm,
    )
    assert summary["budget"]["attempted_llm_calls"] == 12
    assert summary["budget"]["enforced_limits"]["normal_work_permits"] == 11
    assert summary["team_completion"]["classification"] == "completed"
    events = [json.loads(line) for line in (tmp_path / summary["run_id"] / "logs" / "events.jsonl").read_text().splitlines()]
    final_calls = [event for event in events if event["event_type"] == "llm_call" and event["payload"].get("call_kind") == "final_synthesis"]
    assert len(final_calls) == 1
    visible = [event for event in events if event["event_type"] == "manager_report_model_visible"]
    assert len(visible) == 3
    assert len([event for event in events if event["event_type"] == "manager_report_queued"]) == 3
    assert len([event for event in events if event["event_type"] == "manager_report_delivered"]) == 3
    first_visible = min(event["sequence"] for event in visible)
    first_synthesis_call = min(event["sequence"] for event in final_calls)
    synthesis_started = min(event["sequence"] for event in events if event["event_type"] == "final_synthesis_started")
    assert synthesis_started < first_visible < first_synthesis_call
    snapshot_reports = summary["team_completion"]["snapshot"]["reports"]
    assert len(snapshot_reports) == 3
    assert all(report["transport_state"] == "delivered" for report in snapshot_reports)
    assert not [event for event in events if event["event_type"] == "llm_retry_scheduled" and event["payload"].get("call_kind") == "final_synthesis"]
    assert all(
        event["payload"].get("max_output_tokens") == 4096
        for event in events
        if event["event_type"] == "llm_call"
    )


def test_team_finalization_deadline_expires_before_final_synthesis() -> None:
    now = [0.0]
    coordinator = TeamFinalizationCoordinator(
        worker_ids=("w1",),
        finalization_deadline_seconds=60,
        clock=lambda: now[0],
    )
    coordinator.enter_barrier({"w1": "done"})
    now[0] = 61.0
    coordinator.drain_and_freeze()
    assert coordinator.deadline_exceeded() is True
    assert coordinator.finish_deadline() == "forced_unfinished"
    assert coordinator.state is FinalizationState.FORCED_UNFINISHED


def test_reserved_permit_is_inside_hard_budget_and_normal_calls_cannot_take_it() -> None:
    budget = BudgetTracker(hard_team_call_permits=4, reserved_final_synthesis_permits=1)
    for index in range(3):
        permit = budget.acquire_call_permit(f"worker-{index}")
        budget.settle_call_permit(permit, outcome="succeeded", usage=TokenUsage(model="mock"))
    assert budget.snapshot()["enforced_limits"]["normal_work_permits"] == 3
    with pytest.raises(BudgetExhausted, match="reserved_final_synthesis"):
        budget.acquire_call_permit("manager")
    budget.authorize_final_synthesis("manager")
    permit = budget.acquire_call_permit("manager", call_kind="final_synthesis")
    budget.settle_call_permit(permit, outcome="succeeded", usage=TokenUsage(model="mock"))
    assert budget.snapshot()["attempted_llm_calls"] == 4
    with pytest.raises(BudgetExhausted):
        budget.acquire_call_permit("manager", call_kind="final_synthesis")


def test_final_synthesis_provider_error_consumes_reserved_permit_without_retry() -> None:
    budget = BudgetTracker(hard_team_call_permits=2, reserved_final_synthesis_permits=1)
    permit = budget.acquire_call_permit("worker")
    budget.settle_call_permit(permit, outcome="succeeded", usage=TokenUsage(model="mock"))
    budget.authorize_final_synthesis("manager")
    final = budget.acquire_call_permit("manager", call_kind="final_synthesis")
    budget.settle_call_permit(final, outcome="provider_error", usage=TokenUsage(model="mock"))
    assert budget.snapshot()["attempted_llm_calls"] == 2
    with pytest.raises(BudgetExhausted):
        budget.acquire_call_permit("manager", call_kind="final_synthesis")


def test_barrier_terminalizes_waiting_workers_and_freezes_snapshot() -> None:
    coordinator = TeamFinalizationCoordinator(worker_ids=("w1", "w2", "w3"))
    coordinator.transport.produce("r1", "w1", "one", ["e1"])
    coordinator.transport.queue("r1")
    coordinator.transport.produce("r2", "w2", "two", ["e2"])
    coordinator.transport.queue("r2")
    states = coordinator.enter_barrier({"w1": "done", "w2": "waiting_for_assignment", "w3": "timed_out"})
    assert states["w2"] == "cancelled"
    snapshot = coordinator.drain_and_freeze(unresolved_tasks=("task-3",))
    assert coordinator.state is FinalizationState.FINAL_SNAPSHOT_READY
    assert {report.report_id for report in snapshot.reports} == {"r1", "r2"}
    with pytest.raises(ValueError):
        coordinator.transport.adopt("r1")
    coordinator.begin_final_synthesis()
    coordinator.record_final_synthesis_request()
    assert all(report.model_visible for report in coordinator.transport.reports)
    assert all(not report.adopted for report in coordinator.transport.reports)
    coordinator.transport.adopt("r1")
    assert coordinator.finish(submitted=True, worker_failure=True) == "completed_with_worker_failure"


def test_drain_never_makes_report_model_visible_and_late_report_is_deterministic() -> None:
    coordinator = TeamFinalizationCoordinator(worker_ids=("w1",))
    coordinator.transport.produce("r1", "w1", "one")
    coordinator.transport.queue("r1")
    coordinator.enter_barrier({"w1": "done"})
    coordinator.drain_and_freeze()
    assert coordinator.transport.reports[0].transport_state == "delivered"
    assert coordinator.transport.reports[0].model_visible is False
    late = coordinator.transport.produce("late", "w1", "late")
    assert late.late is True
    assert coordinator.transport.late_report_ids == ["late"]
    coordinator.begin_final_synthesis()
    coordinator.record_final_synthesis_request()
    by_id = {report.report_id: report for report in coordinator.transport.reports}
    assert by_id["r1"].model_visible is True
    assert by_id["late"].model_visible is False
