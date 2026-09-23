"""No-network regression tests for the team-permit finalization epoch."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from experiments.emergent_coordination.harness.budget import BudgetTracker, TokenUsage
from experiments.emergent_coordination.harness.llm.client import LLMResponse, MockLLMClient
from experiments.emergent_coordination.harness.runner import RunConfig, run_experiment


def _response(name: str, arguments: dict, call_id: str) -> LLMResponse:
    return LLMResponse(
        content=None,
        tool_calls=[{"id": call_id, "name": name, "arguments": json.dumps(arguments)}],
        usage=TokenUsage(input_tokens=1, output_tokens=1, model="mock"),
        raw={"mock": True},
        model_metadata={"finish_reason": "tool_calls", "provider": "mock"},
    )


def _submit(call_id: str) -> LLMResponse:
    return _response("submit_findings", {"schema_version": "repository-v1", "findings": []}, call_id)


def test_trigger_boundary_and_exactly_once() -> None:
    budget = BudgetTracker(
        hard_team_call_permits=96,
        team_finalization_policy="team_remaining_permits_v1",
        team_finalization_reserve=32,
    )
    budget.register_agent("a")
    for index in range(64):
        permit = budget.acquire_call_permit("a")
        budget.settle_call_permit(permit, outcome="succeeded", usage=TokenUsage())
    assert budget.remaining_permits == 32
    trigger = budget.maybe_start_team_finalization()
    assert trigger is not None
    assert trigger["trigger_remaining_permits"] == 32
    assert trigger["trigger_call_index"] == 65
    assert budget.maybe_start_team_finalization() is None
    assert budget.snapshot()["team_finalization"]["active"] is True


def test_uneven_consumption_and_early_terminal_agent_are_not_per_agent_gates() -> None:
    budget = BudgetTracker(
        hard_team_call_permits=96,
        team_finalization_policy="team_remaining_permits_v1",
        team_finalization_reserve=32,
    )
    for agent in ("a", "b", "c", "d"):
        budget.register_agent(agent)
    budget.mark_agent_terminal("d")
    for agent, count in (("a", 28), ("b", 17), ("c", 19)):
        for _ in range(count):
            permit = budget.acquire_call_permit(agent)
            budget.settle_call_permit(permit, outcome="succeeded", usage=TokenUsage())
    assert budget.remaining_permits == 32
    trigger = budget.maybe_start_team_finalization()
    assert trigger["active_agents"] == ["a", "b", "c"]


def test_mock_parallel_run_gets_team_signal_submission_and_no_free_calls() -> None:
    scripts = {}
    for index in range(1, 5):
        agent = f"agent_{index:03d}"
        # 16 exploratory calls per agent consume 64 permits; the next call
        # enters the shared finalization epoch and the following call submits.
        scripts[agent] = [
            _response("read_file", {"path": "target/README.md"}, f"read-{index}-{step}")
            for step in range(16)
        ] + [_response("read_file", {"path": "target/README.md"}, f"final-read-{index}"), _submit(f"submit-{index}")]
    llm = MockLLMClient(scripts=scripts)
    llm.max_tokens = 4096
    with tempfile.TemporaryDirectory() as tmp:
        summary = run_experiment(
            RunConfig(
                mode="parallel",
                agent_count=4,
                model="mock",
                model_profile={"requested_model": "mock"},
                seed="team-finalization-unit",
                budgets={"hard_team_call_permits": 96},
                max_steps=96,
                completion_policy="convergent_v2",
                team_completion_policy="all_agents_terminal_v1",
                team_finalization_policy="team_remaining_permits_v1",
                team_finalization_reserve=32,
                runs_dir=Path(tmp),
                case_id="flowise_3_1_3_repository_v1",
                evaluate=False,
            ),
            llm,
        )
        run_dir = Path(summary["run_dir"])
        events = [json.loads(line) for line in (run_dir / "logs/events.jsonl").read_text().splitlines()]
        starts = [event for event in events if event["event_type"] == "team_finalization_started"]
        phases = [event for event in events if event["event_type"] == "completion_phase_started"]
        assert len(starts) == 1
        assert starts[0]["payload"]["trigger_remaining_permits"] == 32
        assert len(phases) == 4
        assert summary["budget"]["attempted_llm_calls"] <= 96
        assert {item["stop_reason"] for item in summary["agent_results"]} == {"submitted"}
        assert sum(item["submission_attempts"] for item in summary["agent_results"]) == 4
        assert not [event for event in events if event["event_type"] == "error"]

