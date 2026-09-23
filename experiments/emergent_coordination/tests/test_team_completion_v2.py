"""No-network tests for the production all-agents-terminal barrier."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from experiments.emergent_coordination.harness.budget import BudgetExhausted, BudgetTracker, TokenUsage
from experiments.emergent_coordination.harness.events import EventLog
from experiments.emergent_coordination.harness.llm.client import LLMResponse, MockLLMClient
from experiments.emergent_coordination.harness.runner import RunConfig, run_experiment
from experiments.emergent_coordination.harness.contract import load_block_config
from experiments.emergent_coordination.harness.team_completion import (
    ALL_AGENTS_TERMINAL_V1,
    TeamCompletionBarrier,
)


def _snapshot(*, used: int = 0, limit: int | None = 64, closed: bool = False, in_flight: int = 0) -> dict:
    return {
        "llm_calls": used,
        "attempted_llm_calls": used,
        "admission_closed": closed,
        "in_flight_provider_calls": in_flight,
        "enforced_limits": {"hard_team_call_permits": limit},
        "permit_ledger": [{"outcome": "granted"}] * in_flight,
    }


def _barrier(*agents: str) -> TeamCompletionBarrier:
    return TeamCompletionBarrier(agent_ids=agents, policy=ALL_AGENTS_TERMINAL_V1)


def test_early_clean_completion_leaves_permits_and_emits_once(tmp_path: Path) -> None:
    barrier = _barrier("agent_001", "agent_002")
    results = [{"agent_id": agent, "stop_reason": "submitted"} for agent in ("agent_001", "agent_002")]
    event_log = EventLog(tmp_path / "events.jsonl", run_id="r")
    event = barrier.emit(event_log, results, budget_snapshot=_snapshot(used=3))
    assert event is not None
    assert event["payload"]["classification"] == "clean_complete"
    assert event["payload"]["permits_remaining"] == 61
    assert barrier.emit(event_log, results, budget_snapshot=_snapshot(used=3)) is None
    assert len([item for item in event_log.read_all() if item["event_type"] == "team_completion"]) == 1


def test_partial_terminal_team_stays_running() -> None:
    barrier = _barrier("a", "b", "c", "d")
    assert barrier.evaluate(
        [{"agent_id": agent, "stop_reason": "submitted"} for agent in ("a", "b", "c")],
        budget_snapshot=_snapshot(used=4),
    ) is None
    assert barrier.state == "TEAM_RUNNING"


def test_forced_plus_submitted_requires_all_terminal() -> None:
    barrier = _barrier("a", "b")
    assert barrier.evaluate(
        [{"agent_id": "a", "stop_reason": "max_steps"}], budget_snapshot=_snapshot(used=4)
    ) is None
    result = barrier.evaluate(
        [{"agent_id": "a", "stop_reason": "max_steps"}, {"agent_id": "b", "stop_reason": "submitted"}],
        budget_snapshot=_snapshot(used=4),
    )
    assert result is not None and result.classification == "forced_complete"


def test_last_permit_closes_admission_but_in_flight_drain_is_not_completion() -> None:
    budget = BudgetTracker(hard_team_call_permits=1)
    permit = budget.acquire_call_permit("a")
    assert budget.snapshot()["admission_closed"] is True
    barrier = _barrier("a", "b")
    assert barrier.evaluate(
        [{"agent_id": "a", "stop_reason": "submitted"}, {"agent_id": "b", "stop_reason": "submitted"}],
        budget_snapshot=budget.snapshot(),
    ) is None
    budget.settle_call_permit(permit, outcome="succeeded", usage=TokenUsage(model="mock"))
    result = barrier.evaluate(
        [{"agent_id": "a", "stop_reason": "submitted"}, {"agent_id": "b", "stop_reason": "submitted"}],
        budget_snapshot=budget.snapshot(),
    )
    assert result is not None and result.trigger == "admission_closed_then_drained"


def test_admission_denies_next_call_without_overdraft_after_drain() -> None:
    budget = BudgetTracker(hard_team_call_permits=1)
    permit = budget.acquire_call_permit("a")
    budget.settle_call_permit(permit, outcome="succeeded", usage=TokenUsage(model="mock"))
    with pytest.raises(BudgetExhausted):
        budget.acquire_call_permit("b")
    assert budget.snapshot()["llm_calls"] == 1


def test_last_response_submit_is_accepted_after_admission_closes(tmp_path: Path) -> None:
    response = LLMResponse(
        content=None,
        tool_calls=[{"id": "submit", "name": "submit_findings", "arguments": json.dumps({"schema_version": "repository-v1", "findings": []})}],
        usage=TokenUsage(input_tokens=1, output_tokens=1, model="mock"),
        raw={"mock": True},
    )
    summary = run_experiment(
        RunConfig(
            mode="single", agent_count=1, model="mock", budgets={"hard_team_call_permits": 1}, max_steps=4,
            team_completion_policy=ALL_AGENTS_TERMINAL_V1, runs_dir=tmp_path,
            case_id="flowise_3_1_3_repository_v1", evaluate=False,
        ),
        MockLLMClient(scripts={"agent_001": [response]}),
    )
    assert summary["agent_results"][0]["stop_reason"] == "submitted"
    assert summary["budget"]["llm_calls"] == 1
    events = [json.loads(line) for line in (Path(summary["run_dir"]) / "logs/events.jsonl").read_text().splitlines()]
    completion = [event for event in events if event["event_type"] == "team_completion"]
    assert completion[0]["payload"]["classification"] == "clean_complete"
    assert not [event for event in events if event["event_type"] == "budget_exhausted"]


def test_post_close_next_turn_is_forced_without_extra_permit(tmp_path: Path) -> None:
    response = LLMResponse(
        content=None,
        tool_calls=[{"id": "write", "name": "shared_create", "arguments": json.dumps({"path": "x.txt", "content": "x"})}],
        usage=TokenUsage(input_tokens=1, output_tokens=1, model="mock"),
        raw={"mock": True},
    )
    summary = run_experiment(
        RunConfig(
            mode="raw_blackboard", agent_count=1, model="mock", budgets={"hard_team_call_permits": 1}, max_steps=4,
            team_completion_policy=ALL_AGENTS_TERMINAL_V1, runs_dir=tmp_path,
            case_id="flowise_3_1_3_repository_v1", evaluate=False,
        ),
        MockLLMClient(scripts={"agent_001": [response]}),
    )
    assert summary["agent_results"][0]["stop_reason"] == "budget_exhausted"
    assert summary["budget"]["llm_calls"] == 1
    events = [json.loads(line) for line in (Path(summary["run_dir"]) / "logs/events.jsonl").read_text().splitlines()]
    completion = [event for event in events if event["event_type"] == "team_completion"]
    assert completion[0]["payload"]["classification"] == "forced_complete"
    assert completion[0]["payload"]["in_flight"] == 0


def test_legacy_contract_has_no_implicit_team_policy() -> None:
    config = load_block_config(Path("experiments/emergent_coordination/manifests/n4_flowise_v1.json"))
    assert config.team_completion_policy is None


def test_infrastructure_invalid_is_not_forced() -> None:
    result = _barrier("a").evaluate(
        [{"agent_id": "a", "stop_reason": "budget_exhausted"}],
        budget_snapshot=_snapshot(used=1, closed=True),
        infrastructure_status="infrastructure_invalid",
    )
    assert result is not None and result.classification == "invalid"


def test_simultaneous_barrier_evaluation_is_exactly_once(tmp_path: Path) -> None:
    barrier = _barrier("a", "b", "c", "d")
    results = [{"agent_id": agent, "stop_reason": "submitted"} for agent in ("a", "b", "c", "d")]
    event_log = EventLog(tmp_path / "events.jsonl", run_id="race")
    with ThreadPoolExecutor(max_workers=8) as pool:
        events = list(pool.map(lambda _: barrier.emit(event_log, results, budget_snapshot=_snapshot(used=4)), range(8)))
    assert sum(event is not None for event in events) == 1
    assert len([event for event in event_log.read_all() if event["event_type"] == "team_completion"]) == 1


@pytest.mark.parametrize("mode,agents", [("single", 1), ("parallel", 4), ("raw_blackboard", 4), ("structured_team", 4)])
def test_topology_neutral_and_no_m4_policy(mode: str, agents: int, tmp_path: Path) -> None:
    scripts = {
        f"agent_{index:03d}": [
            LLMResponse(
                content=None,
                tool_calls=[{"id": f"s-{index}", "name": "submit_findings", "arguments": json.dumps({"schema_version": "repository-v1", "findings": []})}],
                usage=TokenUsage(input_tokens=1, output_tokens=1, model="mock"),
                raw={"mock": True},
            )
        ]
        for index in range(1, agents + 1)
    }
    summary = run_experiment(
        RunConfig(
            mode=mode,
            agent_count=agents,
            model="mock",
            budgets={"hard_team_call_permits": 64},
            max_steps=4,
            completion_policy="convergent_v2",
            team_completion_policy=ALL_AGENTS_TERMINAL_V1,
            runs_dir=tmp_path,
            case_id="flowise_3_1_3_repository_v1",
            evaluate=False,
        ),
        MockLLMClient(scripts=scripts),
    )
    events = [json.loads(line) for line in (Path(summary["run_dir"]) / "logs/events.jsonl").read_text().splitlines()]
    completions = [event for event in events if event["event_type"] == "team_completion"]
    assert len(completions) == 1
    assert completions[0]["payload"]["classification"] == "clean_complete"
    assert "manager" not in json.dumps(completions[0]["payload"])


def test_invariants_and_legacy_manifest_compatibility(tmp_path: Path) -> None:
    barrier = _barrier("a", "b")
    assert barrier.evaluate([{"agent_id": "a", "stop_reason": "submitted"}], budget_snapshot=_snapshot()) is None
    result = barrier.evaluate(
        [{"agent_id": "a", "stop_reason": "submitted"}, {"agent_id": "b", "stop_reason": "model_format_failure"}],
        budget_snapshot=_snapshot(used=2),
    )
    assert result is not None
    assert result.in_flight == 0
    assert result.permits_used <= 64
    assert result.classification == "forced_complete"
