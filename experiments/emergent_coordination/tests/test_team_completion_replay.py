"""Replay review for the Candidate E mock tapes.

The replay runner consumes checked-in JSON event tapes and the test-only
MockTeam fixture.  It intentionally has no provider/network path.  Replaying
the same tape twice must produce the same canonical snapshot.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from experiments.emergent_coordination.tests.test_team_completion_semantics import (
    GateDenied,
    MockTeam,
)


FIXTURE = Path(__file__).parent / "fixtures" / "team_completion_replay_cases.json"
CASES = json.loads(FIXTURE.read_text(encoding="utf-8"))


def _snapshot(team: MockTeam, errors: list[str]) -> dict:
    return {
        "phase": team.phase,
        "outcome": list(team.outcome()),
        "event_seq": team.event_seq,
        "cutoff": team.cutoff,
        "statuses": dict(sorted(team.statuses.items())),
        "local_submission": dict(sorted(team.local_submission.items())),
        "permits": {
            "granted": team.ledger.granted,
            "consumed": team.ledger.consumed,
            "remaining": team.ledger.remaining,
        },
        "provider_calls": [list(call) for call in team.provider.calls],
        "prohibited": [list(call) for call in team.prohibited],
        "lineage": dict(sorted(team.lineage.stages.items())),
        "labels": {
            ref: sorted(values) for ref, values in sorted(team.lineage.labels.items())
        },
        "producers": {
            ref: sorted(values) for ref, values in sorted(team.lineage.producers.items())
        },
        "adopted": sorted(team.adopted),
        "late_events": len(team.late_events),
        "queue_size": len(team.queue),
        "errors": list(errors),
    }


def _replay(case: dict) -> dict:
    initial = case["initial"]
    team = MockTeam(
        agents=tuple(initial["agents"]),
        permits=initial["permits"],
        reserve=initial["reserve"],
        drain_max_ticks=initial.get("drain_max_ticks", 8),
    )
    seen_ids: set[str] = set()
    errors: list[str] = []

    for event in case["events"]:
        event_id = event["id"]
        if event_id in seen_ids:
            raise AssertionError(f"duplicate replay event id: {event_id}")
        seen_ids.add(event_id)

        op = event["op"]
        if op == "model_call":
            team.model_call(event["agent"], event["action"])
        elif op == "expect_error":
            with pytest.raises(GateDenied):
                team.model_call(event["agent"], event["action"])
            errors.append(event["error"])
        elif op == "local_submit":
            team.local_submit(event["agent"])
        elif op == "local_report":
            team.local_report(event["agent"])
        elif op == "set_waiting":
            team.set_waiting(event["agent"])
        elif op == "resume":
            team.resume(event["agent"])
        elif op == "expect_resume_error":
            with pytest.raises(GateDenied):
                team.resume(event["agent"])
            errors.append(event["error"])
        elif op == "mark_done":
            team.mark_done(event["agent"])
        elif op == "add_obligation":
            team.obligations.add(event["value"])
        elif op == "produce":
            team.produce(event["ref"], producer=event.get("producer"))
        elif op == "queue_info":
            team.queue_info(event["ref"])
        elif op == "emit":
            team.emit(event["kind"], event.get("ref"))
        elif op == "freeze_if_boundary":
            assert team.freeze_if_boundary()
        elif op == "freeze":
            team.freeze()
        elif op == "drain":
            team.drain()
        elif op == "hard_finalize":
            team.hard_finalize(tuple(event["agents"]))
        elif op == "force_stage":
            team.lineage.set(event["ref"], event["stage"])
        elif op == "make_model_visible":
            team.make_model_visible(event["ref"])
        elif op == "adopt":
            team.adopt(event["ref"])
        elif op == "label":
            team.lineage.label(event["ref"], event["value"])
        else:
            raise AssertionError(f"unknown replay operation: {op}")

    return _snapshot(team, errors)


def _assert_expected(snapshot: dict, expected: dict) -> None:
    for key, value in expected.items():
        assert snapshot[key] == value, (key, snapshot[key], value)


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_mock_replay_is_deterministic_and_matches_expected_snapshot(case: dict) -> None:
    first = _replay(case)
    second = _replay(deepcopy(case))
    assert first == second
    _assert_expected(first, case["expected"])


def test_replay_rejects_duplicate_event_ids() -> None:
    case = deepcopy(CASES[0])
    case["events"].append(deepcopy(case["events"][0]))
    with pytest.raises(AssertionError, match="duplicate replay event id"):
        _replay(case)


def test_replay_rejects_adoption_before_model_visibility() -> None:
    team = MockTeam(agents=("manager",))
    team.produce("r")
    team.queue_info("r")
    with pytest.raises(AssertionError):
        team.adopt("r")


def test_replay_rejects_semantic_adoption_inside_drain() -> None:
    team = MockTeam(agents=("manager",))
    team.produce("r")
    team.queue_info("r")
    team.emit("semantic_adopt", "r")
    team.freeze()
    with pytest.raises(AssertionError, match="semantic adoption"):
        team.drain()
