"""No-API integration/preflight for the actual coordination harness.

Unlike ``test_team_completion_semantics.py``, these tests call the production
``run_experiment`` path with the repository-v1 case, real sandboxes, event
logs, permit accounting, and mode policies.  The only model implementation is
the local scripted ``MockLLMClient``.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from experiments.emergent_coordination.harness.budget import TokenUsage
from experiments.emergent_coordination.harness.llm.client import LLMResponse, MockLLMClient
from experiments.emergent_coordination.harness.runner import RunConfig, run_experiment


CASE_ID = "flowise_3_1_3_repository_v1"
COMMON_MODEL_PROFILE = {
    "requested_model": "mock",
    "provider": "mock",
    "thinking_mode": "disabled",
    "temperature": 0.0,
    "max_output_tokens": 4096,
}


def _tool_call(name: str, arguments: dict, call_id: str) -> dict:
    return {"id": call_id, "name": name, "arguments": json.dumps(arguments)}


def _response(*calls: dict) -> LLMResponse:
    return LLMResponse(
        content=None,
        tool_calls=list(calls),
        usage=TokenUsage(input_tokens=1, output_tokens=1, model="mock"),
        raw={"mock": True},
        model_metadata={"finish_reason": "tool_calls", "provider": "mock"},
    )


def _submit(call_id: str) -> LLMResponse:
    return _response(
        _tool_call(
            "submit_findings",
            {"schema_version": "repository-v1", "findings": []},
            call_id,
        )
    )


def _events(run_dir: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in (run_dir / "logs" / "events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _run(
    mode: str,
    scripts: dict[str, list[LLMResponse]],
    *,
    agents: int = 4,
    max_steps: int = 12,
) -> tuple[dict, list[dict], dict]:
    llm = MockLLMClient(scripts=scripts)
    # MockLLMClient defaults to 1024 for historical smoke tests.  The
    # preflight explicitly exercises the frozen 4096 generation metadata.
    llm.max_tokens = 4096
    with tempfile.TemporaryDirectory() as tmp:
        summary = run_experiment(
            RunConfig(
                mode=mode,
                agent_count=agents,
                model="mock",
                model_profile=COMMON_MODEL_PROFILE,
                seed=f"preflight-{mode}-n{agents}",
                budgets={"hard_team_call_permits": 64},
                max_steps=max_steps,
                max_provider_retries=0,
                completion_policy="convergent_v2",
                runs_dir=Path(tmp),
                case_id=CASE_ID,
                evaluate=False,
            ),
            llm,
        )
        run_dir = Path(summary["run_dir"])
        # Copy read-only observables out of TemporaryDirectory before return.
        events = _events(run_dir)
        manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
        return summary, events, manifest


def _assert_common_preflight(
    summary: dict,
    events: list[dict],
    manifest: dict,
    agents: int,
    *,
    expected_submissions: int | None = None,
    expected_max_steps: int = 12,
    allow_prohibited: bool = False,
) -> None:
    assert summary["agent_count"] == agents
    assert summary["run_validity"]["status"] == "valid"
    assert summary["reconciliation"]["status"] == "valid"
    assert manifest["model"] == "mock"
    assert manifest["completion_policy"] == "convergent_v2"
    assert manifest["finding_schema"] == "repository_v1"
    assert manifest["prompt_profile"] == "repository_v1"
    assert manifest["model_profile"] == COMMON_MODEL_PROFILE
    assert manifest["max_steps"] == expected_max_steps
    assert manifest["budgets"]["hard_team_call_permits"] == 64
    assert len([event for event in events if event["event_type"] == "agent_started"]) == agents
    assert len([event for event in events if event["event_type"] == "finding_submitted"]) == (expected_submissions or agents)
    assert not [event for event in events if event["event_type"] in {"error", "llm_call"} and event.get("outcome") != "succeeded"]
    if not allow_prohibited:
        assert not [event for event in events if event["event_type"] == "prohibited_tool_attempt"]
    assert all(entry["outcome"] == "succeeded" for entry in summary["budget"]["permit_ledger"])
    assert summary["budget"]["attempted_llm_calls"] == len(summary["budget"]["permit_ledger"])


def _submit_scripts(agents: int) -> dict[str, list[LLMResponse]]:
    return {f"agent_{index:03d}": [_submit(f"submit-{index}")] for index in range(1, agents + 1)}


@pytest.mark.parametrize(
    ("mode", "expected_mode_events"),
    [
        ("single", {"agent_count": 1}),
        ("parallel", {"agent_started": 4}),
    ],
    ids=["S1", "P4"],
)
def test_actual_harness_s1_p4_mock_preflight(mode: str, expected_mode_events: dict[str, int]) -> None:
    agents = expected_mode_events["agent_count"] if "agent_count" in expected_mode_events else 4
    summary, events, manifest = _run(mode, _submit_scripts(agents), agents=agents)
    _assert_common_preflight(summary, events, manifest, agents)
    if mode == "parallel":
        assert len([event for event in events if event["event_type"] == "agent_finished"]) == 4


def test_actual_harness_b4_shared_store_preflight() -> None:
    scripts: dict[str, list[LLMResponse]] = {}
    for index in range(1, 5):
        agent = f"agent_{index:03d}"
        scripts[agent] = [
            _response(_tool_call("shared_create", {"path": f"preflight/{agent}.txt", "content": "mock"}, f"create-{index}")),
            _response(_tool_call("shared_list", {"path": "preflight"}, f"list-{index}")),
            _submit(f"submit-{index}"),
        ]
    summary, events, manifest = _run("raw_blackboard", scripts)
    _assert_common_preflight(summary, events, manifest, 4)
    assert len([event for event in events if event["event_type"] == "shared_create"]) == 4
    assert len([event for event in events if event["event_type"] == "shared_list"]) == 4
    assert manifest["mode"] == "raw_blackboard"


def test_actual_harness_t4_task_board_preflight() -> None:
    scripts: dict[str, list[LLMResponse]] = {}
    for index in range(1, 5):
        agent = f"agent_{index:03d}"
        scripts[agent] = [
            _response(_tool_call("create_task", {"description": f"preflight-{agent}"}, f"task-{index}")),
            _response(_tool_call("list_tasks", {}, f"list-{index}")),
            _submit(f"submit-{index}"),
        ]
    summary, events, manifest = _run("structured_team", scripts)
    _assert_common_preflight(summary, events, manifest, 4)
    assert len([event for event in events if event["event_type"] == "task_created"]) == 4
    # Each list_tasks invocation emits one sandbox tool_call plus one board
    # observation event; both are expected on the real harness path.
    assert len([event for event in events if event["event_type"] == "tool_call" and event.get("payload", {}).get("tool") == "list_tasks"]) >= 4
    assert manifest["mode"] == "structured_team"


def test_actual_harness_m4_manager_worker_preflight() -> None:
    scripts = {
        "agent_001": [
            _response(_tool_call("manager_create_task", {"worker_id": "agent_002", "description": "preflight-2"}, "m1")),
            _response(_tool_call("manager_create_task", {"worker_id": "agent_003", "description": "preflight-3"}, "m2")),
            _response(_tool_call("manager_create_task", {"worker_id": "agent_004", "description": "preflight-4"}, "m3")),
            _response(_tool_call("manager_list_tasks", {}, "m4")),
            _response(_tool_call("manager_list_tasks", {}, "m5")),
            _submit("m6"),
        ],
        "agent_002": [
            _response(_tool_call("worker_get_assignment", {}, "w2-1")),
            _response(_tool_call("worker_report_task", {"task_id": "manager_task_0001", "result": "mock report", "evidence_refs": []}, "w2-2")),
            _submit("w2-3"),
        ],
        "agent_003": [
            _response(_tool_call("worker_get_assignment", {}, "w3-1")),
            _response(_tool_call("worker_report_task", {"task_id": "manager_task_0002", "result": "mock report", "evidence_refs": []}, "w3-2")),
            _submit("w3-3"),
        ],
        "agent_004": [
            _response(_tool_call("worker_get_assignment", {}, "w4-1")),
            _response(_tool_call("worker_report_task", {"task_id": "manager_task_0003", "result": "mock report", "evidence_refs": []}, "w4-2")),
            _submit("w4-3"),
        ],
    }
    summary, events, manifest = _run("manager_worker", scripts)
    _assert_common_preflight(summary, events, manifest, 4, expected_submissions=1, allow_prohibited=True)
    assert len([event for event in events if event["event_type"] == "manager_task_created"]) == 3
    reported = [event for event in events if event["event_type"] == "manager_worker_reported"]
    observed = [event for event in events if event["event_type"] == "manager_report_observed"]
    assert len(reported) == 3
    report_ids = {event["payload"]["report_id"] for event in reported}
    observed_ids = {event["payload"]["report_id"] for event in observed}
    # The report event is the board's accepted produced/queued state.  The
    # board has all three reports, while the manager model observes only the
    # subset emitted by its successful list_tasks call.
    assert report_ids == {
        "manager_report_0001_manager_task_0001",
        "manager_report_0001_manager_task_0002",
        "manager_report_0001_manager_task_0003",
    }
    assert observed_ids <= report_ids
    assert 0 <= len(observed_ids) < len(report_ids)
    assert not [event for event in events if event["event_type"] in {"manager_report_model_visible", "manager_report_adopted"}]

    completion = [event for event in events if event["event_type"] == "completion_phase_started" and event.get("agent_id") == "agent_001"]
    assert len(completion) == 1
    assert completion[0]["payload"]["step"] == 5  # max_steps=12, reserve=8
    prohibited = [event for event in events if event["event_type"] == "prohibited_tool_attempt"]
    assert len(prohibited) == 1
    assert prohibited[0]["agent_id"] == "agent_001"
    assert prohibited[0]["payload"]["requested_tool"] == "manager_list_tasks"
    assert prohibited[0]["payload"]["step"] == 5
    assert prohibited[0]["payload"]["rejected_by"] == "hard_finalization_gate"

    manager_submit = [event for event in events if event["event_type"] == "finding_submitted" and event.get("agent_id") == "agent_001"]
    assert len(manager_submit) == 1
    assert manager_submit[0]["payload"]["count"] == 0
    workers_finished = [event for event in events if event["event_type"] == "agent_finished" and event.get("agent_id") != "agent_001"]
    assert len(workers_finished) == 3
    assert {event["payload"]["reason"] for event in workers_finished} == {"waiting_for_assignment"}
    # Individual binding is visible on the manager's step-5 gate; team
    # binding remains forced/unfinished because waiting workers and an
    # unobserved report coexist.  No runtime label is invented here.
    assert len(observed_ids) < 3 and len(workers_finished) == 3
    assert all(
        event["payload"].get("max_output_tokens") == 4096
        for event in events
        if event["event_type"] == "llm_call"
    )
    assert manifest["mode"] == "manager_worker"


def test_actual_harness_n4_hard_gate_preflight() -> None:
    scripts: dict[str, list[LLMResponse]] = {}
    for index in range(1, 5):
        calls = [
            _response(_tool_call("read_file", {"path": "target/README.md"}, f"read-{index}-{step}"))
            for step in range(1, 5)
        ]
        calls.extend(
            [
                _response(_tool_call("read_file", {"path": "target/README.md"}, f"blocked-{index}")),
                _submit(f"submit-{index}"),
            ]
        )
        scripts[f"agent_{index:03d}"] = calls
    summary, events, manifest = _run("parallel", scripts)
    _assert_common_preflight(summary, events, manifest, 4, allow_prohibited=True)
    prohibited = [event for event in events if event["event_type"] == "prohibited_tool_attempt"]
    assert len(prohibited) == 4
    assert all(event["payload"]["rejected_by"] == "hard_finalization_gate" for event in prohibited)
    completions = [event for event in events if event["event_type"] == "completion_phase_started"]
    assert len(completions) == 4
