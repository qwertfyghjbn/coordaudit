"""Zero-network initialization_lease_v3 checks.

Design frozen in docs/plans/INITIALIZATION_LEASE_V3_DESIGN.md: the lease only
sequences the initial board bootstrap (list -> optional create -> claim) and
must never gate ordinary investigation.  All tests are deterministic and use
scripted local clients; no provider is contacted.
"""

from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path
from typing import Any, Callable

from experiments.emergent_coordination.harness.budget import BudgetTracker, TokenUsage
from experiments.emergent_coordination.harness.block_runner import BlockRunner
from experiments.emergent_coordination.harness.contract import ContractViolation, load_block_config
from experiments.emergent_coordination.harness.events import EventLog, TranscriptLog
from experiments.emergent_coordination.harness.agent_loop import AgentRunner
from experiments.emergent_coordination.harness.llm.client import LLMResponse, MockLLMClient
from experiments.emergent_coordination.harness.paths import TARGET_ROOT
from experiments.emergent_coordination.harness.prompts import T_PILOT_1_PROFILE
from experiments.emergent_coordination.harness.runner import RunConfig, run_experiment
from experiments.emergent_coordination.harness.task_board import (
    BOOTSTRAP_TOOL_DISPATCH_BOUND,
    CoordinationError,
    TaskBoard,
)
from experiments.emergent_coordination.harness.tools.sandbox import AgentSandbox
from experiments.emergent_coordination.harness.workspace import prepare_run_workspace

V3 = "initialization_lease_v3"
AGENT_IDS = ["agent_001", "agent_002", "agent_003", "agent_004"]
SUBMIT_ARGS = {"schema_version": "repository-v1", "findings": []}


def _call(name: str, arguments: dict, call_id: str) -> LLMResponse:
    return LLMResponse(
        content=None,
        tool_calls=[{"id": call_id, "name": name, "arguments": json.dumps(arguments)}],
        usage=TokenUsage(input_tokens=1, output_tokens=1, model="mock"),
        raw={"mock": True},
    )


def _read_round(call_id: str) -> LLMResponse:
    return _call("read_file", {"path": "target/app/main.py"}, call_id)


def _tool_results(messages: list[dict[str, Any]], name: str) -> list[Any]:
    results = []
    for message in messages:
        if message.get("role") == "tool" and message.get("name") == name:
            try:
                results.append(json.loads(message["content"]))
            except json.JSONDecodeError:
                continue
    return results


class _LogicClient:
    """Deterministic stand-in model: derives each action from model-visible context."""

    def __init__(self, logic: dict[str, Callable[[list[dict[str, Any]]], LLMResponse]]):
        self.logic = logic
        self.max_tokens = 4096

    def complete(self, messages, tools, *, agent_id: str, **_kwargs) -> LLMResponse:
        return self.logic[agent_id](messages)


class _FlakyOnceClient:
    """Fail the first provider call per agent once, then delegate to the script."""

    def __init__(self, scripts: dict[str, list[LLMResponse]]):
        self._inner = MockLLMClient(scripts=scripts)
        self._failed: set[str] = set()
        self.max_tokens = 4096

    def complete(self, messages, tools, *, agent_id: str, **_kwargs) -> LLMResponse:
        if agent_id not in self._failed:
            self._failed.add(agent_id)
            raise TimeoutError("mock provider timeout")
        return self._inner.complete(messages, tools, agent_id=agent_id)


class LeaseV3UnitTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.log = EventLog(root / "events.jsonl", run_id="lease-v3-unit")
        self.board = TaskBoard(root / "board", self.log, initialization_policy=V3, agent_ids=AGENT_IDS)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _events(self, event_type: str) -> list[dict]:
        return [event for event in self.log.read_all() if event["event_type"] == event_type]

    def test_case_a_first_non_board_choice_opts_out_and_advances_slot(self):
        self.board.note_non_board_activity("agent_001", trigger="non_board_tool")
        self.assertEqual(self.board._initialization_index, 1)
        skipped = self._events("task_initialization_turn_skipped")
        self.assertEqual(len(skipped), 1)
        self.assertEqual(skipped[0]["agent_id"], "agent_001")
        self.assertEqual(skipped[0]["payload"]["reason"], "bootstrap_opt_out")
        # The successor bootstrap is immediately available.
        self.assertEqual(self.board.list_tasks("agent_002"), [])
        self.assertEqual(
            [event["agent_id"] for event in self._events("task_initialization_lease_acquired")],
            ["agent_002"],
        )

    def test_case_b_list_then_non_board_releases_after_snapshot_consumed(self):
        self.board.list_tasks("agent_001")
        self.assertEqual(self.board._bootstrap_dispatch_counts.get("agent_001"), 1)
        self.board.note_non_board_activity("agent_001", trigger="non_board_tool")
        released = self._events("task_initialization_lease_released")
        self.assertEqual(len(released), 1)
        self.assertEqual(released[0]["payload"]["reason"], "investigation_started")
        self.assertEqual(released[0]["payload"]["board_dispatches"], 1)
        self.assertEqual(
            [event["agent_id"] for event in self._events("task_initialization_lease_acquired")],
            ["agent_001"],
        )
        self.assertEqual(self.board._initialization_owner, None)
        self.assertEqual(self.board._initialization_index, 1)

    def test_case_c_full_bootstrap_releases_on_claim_without_hitting_bound(self):
        self.board.list_tasks("agent_001")
        task = self.board.create_task("agent_001", "one bounded security question")
        self.board.claim_task("agent_001", task["id"])
        released = self._events("task_initialization_lease_released")
        self.assertEqual(len(released), 1)
        self.assertEqual(released[0]["payload"]["reason"], "task_claimed")
        self.assertEqual(self.board._bootstrap_dispatch_counts.get("agent_001"), 3)
        # Later agent sees the allocation (sequencing goal).
        observed = self.board.list_tasks("agent_002")
        self.assertEqual(observed[0]["id"], task["id"])
        self.assertEqual(observed[0]["owner"], "agent_001")

    def test_case_d_list_then_claim_existing_releases(self):
        seeded = self.board.create_task("agent_001", "seed")
        self.board.claim_task("agent_001", seeded["id"])
        self.board.release_task("agent_001", seeded["id"])
        self.board.list_tasks("agent_002")
        self.board.claim_task("agent_002", seeded["id"])
        reasons = [event["payload"]["reason"] for event in self._events("task_initialization_lease_released")]
        self.assertEqual(reasons, ["task_claimed", "task_claimed"])

    def test_case_e_create_without_claim_releases_on_first_non_board_action(self):
        task = self.board.create_task("agent_001", "open question")
        self.assertEqual(task["status"], "open")
        self.board.note_non_board_activity("agent_001", trigger="non_board_tool")
        released = self._events("task_initialization_lease_released")
        self.assertEqual(released[0]["payload"]["reason"], "investigation_started")
        self.assertEqual(released[0]["payload"]["board_dispatches"], 1)
        # Task stays open for later agents to see and claim.
        self.assertEqual(self.board.list_tasks("agent_002")[0]["id"], task["id"])

    def test_case_e_bootstrap_bound_force_releases_repeated_board_dispatches(self):
        for _ in range(BOOTSTRAP_TOOL_DISPATCH_BOUND):
            self.board.list_tasks("agent_001")
        released = self._events("task_initialization_lease_released")
        self.assertEqual(len(released), 1)
        self.assertEqual(released[0]["payload"]["reason"], "bootstrap_bound_reached")
        self.assertEqual(released[0]["payload"]["board_dispatches"], BOOTSTRAP_TOOL_DISPATCH_BOUND)
        # The fourth board dispatch runs un-gated; the episode is over.
        self.assertEqual(self.board.list_tasks("agent_001"), [])
        self.assertEqual(len(self._events("task_initialization_lease_acquired")), 1)
        self.assertEqual(self.board.list_tasks("agent_002"), [])

    def test_case_f_claim_failure_via_unmet_dependency_cannot_deadlock(self):
        dependency = self.board.create_task("agent_001", "dependency question")
        dependent = self.board.create_task("agent_001", "dependent question", dependencies=[dependency["id"]])
        with self.assertRaises(CoordinationError):
            self.board.claim_task("agent_001", dependent["id"])
        released = self._events("task_initialization_lease_released")
        self.assertEqual(released[0]["payload"]["reason"], "bootstrap_bound_reached")
        self.assertEqual(self.board._bootstrap_dispatch_counts.get("agent_001"), 3)
        # The failing agent may still retry un-gated; peers are never blocked.
        claimed_dependency = self.board.claim_task("agent_001", dependency["id"])
        self.board.complete_task("agent_001", claimed_dependency["id"], "done", [])
        self.assertEqual(self.board.claim_task("agent_001", dependent["id"])["owner"], "agent_001")
        listed = {task["id"]: task["status"] for task in self.board.list_tasks("agent_002")}
        self.assertEqual(listed[dependent["id"]], "claimed")
        self.assertEqual(listed[dependency["id"]], "completed")

    def test_case_g_board_tool_error_counts_toward_the_bound(self):
        for _ in range(BOOTSTRAP_TOOL_DISPATCH_BOUND):
            with self.assertRaises(CoordinationError):
                self.board.claim_task("agent_001", "task_does_not_exist")
        self.assertEqual(
            self._events("task_initialization_lease_released")[0]["payload"]["reason"],
            "bootstrap_bound_reached",
        )
        self.assertEqual(self.board._initialization_owner, None)

    def test_case_i_terminal_release_still_covers_agents_that_never_acted(self):
        self.board.release_initialization_lease("agent_001", reason="agent_terminal")
        self.assertEqual(self.board._initialization_index, 1)
        skipped = self._events("task_initialization_turn_skipped")
        self.assertEqual(skipped[0]["payload"]["reason"], "agent_terminal_without_lease")
        self.assertEqual(self.board.list_tasks("agent_002"), [])

    def test_release_happens_exactly_once(self):
        self.board.list_tasks("agent_001")
        task = self.board.create_task("agent_001", "one bounded question")
        self.board.claim_task("agent_001", task["id"])
        self.board.note_non_board_activity("agent_001", trigger="non_board_tool")
        self.board.release_initialization_lease("agent_001", reason="agent_terminal")
        self.assertEqual(len(self._events("task_initialization_lease_released")), 1)

    def test_waiting_peer_proceeds_on_opt_out_not_on_terminal(self):
        """The T-Pilot 1 v1 failure mode, reproduced and fixed at unit level."""
        done = threading.Event()
        observed: list[list[dict]] = []

        def observe() -> None:
            observed.append(self.board.list_tasks("agent_002"))
            done.set()

        waiter = threading.Thread(target=observe)
        waiter.start()
        self.assertFalse(done.wait(0.05), "peer must wait while agent_001 holds the slot")
        self.board.list_tasks("agent_001")
        self.assertFalse(done.wait(0.05), "peers wait only during the bounded episode")
        # agent_001 moves on to investigation without claiming or terminating.
        self.board.note_non_board_activity("agent_001", trigger="non_board_tool")
        self.assertTrue(done.wait(2.0), "peer must proceed once the holder starts investigating")
        waiter.join(timeout=2.0)
        self.assertEqual(observed[0], [])
        self.assertEqual(
            self._events("task_initialization_lease_released")[0]["payload"]["reason"],
            "investigation_started",
        )

    def test_deterministic_canonical_turn_advancement(self):
        done = threading.Event()

        def observe() -> None:
            self.board.list_tasks("agent_003")
            done.set()

        waiter = threading.Thread(target=observe)
        waiter.start()
        self.board.list_tasks("agent_001")
        task = self.board.create_task("agent_001", "front")
        self.board.claim_task("agent_001", task["id"])
        self.board.list_tasks("agent_002")
        self.board.note_non_board_activity("agent_002", trigger="non_board_tool")
        self.assertTrue(done.wait(2.0))
        waiter.join(timeout=2.0)
        self.assertEqual(
            [event["agent_id"] for event in self._events("task_initialization_lease_acquired")],
            ["agent_001", "agent_002", "agent_003"],
        )
        self.assertLess(
            next(event["sequence"] for event in self._events("task_claimed")),
            next(event["sequence"] for event in self._events("task_initialization_lease_acquired") if event["agent_id"] == "agent_003"),
        )

    def test_v1_and_v2_semantics_are_not_changed(self):
        v1 = TaskBoard(
            Path(self.tmp.name) / "v1_board", self.log,
            initialization_policy="initialization_lease_v1", agent_ids=AGENT_IDS,
        )
        v1.list_tasks("agent_001")
        v1.note_non_board_activity("agent_001", trigger="non_board_tool")
        self.assertEqual(v1._initialization_owner, "agent_001", "v1 must keep holding until claim or terminal")
        v1.release_initialization_lease("agent_001", reason="agent_terminal")
        v2 = TaskBoard(
            Path(self.tmp.name) / "v2_board", self.log,
            initialization_policy="initialization_lease_v2_optional", agent_ids=AGENT_IDS,
        )
        v2.list_tasks("agent_001")
        v2.note_non_board_activity("agent_001", trigger="non_board_tool")
        self.assertEqual(v2._initialization_owner, "agent_001", "v2 has no in-life opt-out")
        v2.release_initialization_lease("agent_001", reason="agent_terminal")
        v2.release_initialization_lease("agent_003", reason="agent_terminal")
        self.assertEqual(v2._initialization_index, 1, "a non-front terminal agent does not advance v2's turn yet")
        v2.list_tasks("agent_002")
        v2.release_initialization_lease("agent_002", reason="agent_terminal")
        skipped = [
            event
            for event in self.log.read_all()
            if event["event_type"] == "task_initialization_turn_skipped" and event.get("run_id") == v2.event_log.run_id
        ]
        self.assertEqual([event["agent_id"] for event in skipped], ["agent_003"])
        self.assertTrue(all(event["payload"]["reason"] == "agent_terminal_without_lease" for event in skipped))
        self.assertEqual(v2._initialization_index, 3)
        self.assertEqual(v2.list_tasks("agent_004"), [])


class LeaseV3AgentRunnerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _runner(
        self,
        client,
        *,
        agent_id: str = "agent_001",
        board_agents: list[str] | None = None,
        max_provider_retries: int = 0,
    ) -> tuple[AgentRunner, TaskBoard]:
        layout = prepare_run_workspace(Path(self.tmp.name) / f"run-{agent_id}", TARGET_ROOT, 1)
        events = EventLog(layout.logs / "events.jsonl", run_id=f"lease-v3-runner-{agent_id}")
        board = TaskBoard(
            layout.runtime / "coordination", events,
            initialization_policy=V3, agent_ids=board_agents or [agent_id],
        )
        runner = AgentRunner(
            agent_id=agent_id, mode="structured_team", agent_count=1,
            sandbox=AgentSandbox(agent_id, layout, events, board=board),
            llm=client, event_log=events,
            transcript_log=TranscriptLog(layout.logs / "transcripts", f"lease-v3-runner-{agent_id}", events),
            budget=BudgetTracker(hard_team_call_permits=8),
            prompt_profile=T_PILOT_1_PROFILE, finding_schema="repository_pilot_v0",
            completion_policy="convergent_v2", task_closure_policy="task_closure_gate_v1", max_steps=8,
            max_provider_retries=max_provider_retries,
        )
        return runner, board

    def _board_events(self, runner: AgentRunner, event_type: str) -> list[dict]:
        return [event for event in runner.event_log.read_all() if event["event_type"] == event_type]

    def test_malformed_gated_arguments_neither_acquire_nor_hold(self):
        runner, board = self._runner(MockLLMClient())
        rejected = json.loads(runner._dispatch("list_tasks", "{not json", parent_event_id="evt_parent"))
        self.assertEqual(rejected["error"]["code"], "invalid_tool_arguments")
        self.assertEqual(board._initialization_owner, None)
        self.assertEqual(self._board_events(runner, "task_initialization_lease_acquired"), [])
        read = json.loads(runner._dispatch("read_file", '{"path":"target/app/main.py"}', parent_event_id="evt_parent"))
        self.assertTrue(read.get("evidence_ref"))

    def test_submit_dispatch_releases_bootstrap_slot(self):
        runner, board = self._runner(MockLLMClient())
        listed = json.loads(runner._dispatch("list_tasks", "{}", parent_event_id="evt_parent"))
        self.assertEqual(listed, [])
        self.assertEqual(board._initialization_owner, "agent_001")
        submitted = json.loads(runner._dispatch("submit_findings", json.dumps(SUBMIT_ARGS), parent_event_id="evt_parent"))
        self.assertTrue(submitted.get("ok"))
        self.assertEqual(board._initialization_owner, None)
        self.assertEqual(
            self._board_events(runner, "task_initialization_lease_released")[0]["payload"]["reason"],
            "investigation_started",
        )

    def test_case_h_provider_retry_advances_state_exactly_once(self):
        client = _FlakyOnceClient(scripts={"agent_001": [
            _call("list_tasks", {}, "list"),
            _call("submit_findings", SUBMIT_ARGS, "submit"),
        ]})
        runner, board = self._runner(client, max_provider_retries=1)
        result = runner.run()
        self.assertEqual(result["stop_reason"], "submitted")
        self.assertEqual(len(self._board_events(runner, "llm_retry_scheduled")), 1)
        self.assertEqual(
            [event["agent_id"] for event in self._board_events(runner, "task_initialization_lease_acquired")],
            ["agent_001"],
        )
        released = self._board_events(runner, "task_initialization_lease_released")
        self.assertEqual(len(released), 1)
        self.assertEqual(released[0]["payload"]["reason"], "investigation_started")
        self.assertEqual(board._bootstrap_dispatch_counts.get("agent_001"), 1)
        ledger = runner.budget.snapshot()["permit_ledger"]
        self.assertEqual(len(ledger), 3, "one failed attempt, one retry, one submit round")

    def test_case_j_later_agent_needs_no_predecessor_terminal(self):
        """Deterministic manual interleave: peer bootstraps while holder is alive."""
        layout = prepare_run_workspace(Path(self.tmp.name) / "interleave", TARGET_ROOT, 2)
        events = EventLog(layout.logs / "events.jsonl", run_id="lease-v3-interleave")
        board = TaskBoard(layout.runtime / "coordination", events, initialization_policy=V3, agent_ids=["agent_001", "agent_002"])
        budget = BudgetTracker(hard_team_call_permits=8)
        client = MockLLMClient(scripts={
            "agent_001": [_read_round("a1_read"), _call("submit_findings", SUBMIT_ARGS, "a1_submit")],
            "agent_002": [_call("list_tasks", {}, "a2_list"), _call("submit_findings", SUBMIT_ARGS, "a2_submit")],
        })
        client.max_tokens = 4096
        runners = {
            agent_id: AgentRunner(
                agent_id=agent_id, mode="structured_team", agent_count=2,
                sandbox=AgentSandbox(agent_id, layout, events, board=board),
                llm=client, event_log=events,
                transcript_log=TranscriptLog(layout.logs / "transcripts", "lease-v3-interleave", events),
                budget=budget,
                prompt_profile=T_PILOT_1_PROFILE, finding_schema="repository_pilot_v0",
                completion_policy="convergent_v2", task_closure_policy="task_closure_gate_v1", max_steps=8,
            )
            for agent_id in ("agent_001", "agent_002")
        }
        # agent_001 starts investigating (opts out inside the read dispatch).
        runners["agent_001"].advance()
        self.assertEqual(board._initialization_index, 1)
        finished = threading.Event()

        def peer() -> None:
            runners["agent_002"].advance()  # list_tasks must not wait for agent_001 terminal
            runners["agent_002"].advance()  # submit
            finished.set()

        peer_thread = threading.Thread(target=peer)
        peer_thread.start()
        self.assertTrue(finished.wait(2.0), "peer bootstrap must complete while agent_001 is still alive")
        peer_thread.join(timeout=2.0)
        self.assertEqual(runners["agent_002"].result()["stop_reason"], "submitted")
        runners["agent_001"].advance()
        self.assertEqual(runners["agent_001"].result()["stop_reason"], "submitted")
        acquired = [event["agent_id"] for event in events.read_all() if event["event_type"] == "task_initialization_lease_acquired"]
        self.assertEqual(acquired, ["agent_002"])


class LeaseV3IntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _run(self, client, *, permits: int = 48, finalization: bool = True) -> dict:
        summary = run_experiment(
            RunConfig(
                mode="structured_team",
                agent_count=4,
                model="mock",
                model_profile={"requested_model": "mock", "provider": "mock", "thinking_mode": "disabled", "temperature": 0.0, "max_output_tokens": 4096},
                seed="lease-v3-zero-network",
                budgets={"hard_team_call_permits": permits},
                max_steps=96,
                max_provider_retries=1,
                completion_policy="convergent_v2",
                team_completion_policy="all_agents_terminal_v1",
                team_finalization_policy="team_remaining_permits_v1" if finalization else None,
                team_finalization_reserve=32 if finalization else 0,
                task_board_sequencing_policy=V3,
                task_closure_policy="task_closure_gate_v1",
                completion_generation="completion_v2_team",
                prompt_profile=T_PILOT_1_PROFILE,
                runs_dir=Path(self.tmp.name),
                case_id="flowise_3_1_3_repository_v1",
                evaluate=False,
            ),
            client,
        )
        return summary

    def _events(self, summary: dict) -> list[dict]:
        return [json.loads(line) for line in (Path(summary["run_dir"]) / "logs/events.jsonl").read_text().splitlines()]

    def _seq(self, events: list[dict], event_type: str, agent_id: str, tool: str | None = None) -> int:
        for event in events:
            if event["event_type"] != event_type or event.get("agent_id") != agent_id:
                continue
            if tool is not None and (event.get("payload") or {}).get("tool") != tool:
                continue
            return event["sequence"]
        raise AssertionError(f"missing event {event_type}/{agent_id}/{tool}")

    def _board_observation_seq(self, events: list[dict], agent_id: str) -> int:
        """Sequence of the board-side list_tasks completion (post-lease-wait).

        The dispatch-level tool_call event is emitted before the lease wait,
        so only the TaskBoard's own observation event proves the snapshot was
        actually taken after the predecessor's episode ended.
        """
        for event in events:
            if event["event_type"] != "tool_call" or event.get("agent_id") != agent_id:
                continue
            payload = event.get("payload") or {}
            if payload.get("tool") == "list_tasks" and "count" in payload:
                return event["sequence"]
        raise AssertionError(f"missing board observation for {agent_id}")

    def test_sequencing_preserved_claim_visible_to_later_allocation_decision(self):
        """§6: create/claim by agent_001 must be model-visible before agent_002 allocates."""

        def agent_001_logic(messages):
            if not _tool_results(messages, "list_tasks"):
                return _call("list_tasks", {}, "a1_list")
            created = _tool_results(messages, "create_task")
            if not created:
                return _call("create_task", {"description": "auth question"}, "a1_create")
            if not [item for item in _tool_results(messages, "claim_task") if item.get("status") == "claimed"]:
                return _call("claim_task", {"task_id": created[-1]["id"]}, "a1_claim")
            if not _tool_results(messages, "read_file"):
                return _read_round("a1_read")
            if not [item for item in _tool_results(messages, "complete_task") if item.get("status") == "completed"]:
                return _call(
                    "complete_task",
                    {"task_id": created[-1]["id"], "result": "source checked", "evidence_refs": []},
                    "a1_complete",
                )
            return _call("submit_findings", SUBMIT_ARGS, "a1_submit")

        def agent_002_logic(messages):
            listed = _tool_results(messages, "list_tasks")
            if not listed:
                return _call("list_tasks", {}, "a2_list")
            foreign_claimed = [
                task for task in listed[-1]
                if task.get("owner") == "agent_001" and task.get("status") == "claimed"
            ]
            created = _tool_results(messages, "create_task")
            if foreign_claimed and not created:
                # Allocation decision taken only after observing agent_001's claim.
                return _call("create_task", {"description": "upload question"}, "a2_create")
            if created and not [item for item in _tool_results(messages, "claim_task") if item.get("status") == "claimed"]:
                return _call("claim_task", {"task_id": created[-1]["id"]}, "a2_claim")
            if created and not [item for item in _tool_results(messages, "complete_task") if item.get("status") == "completed"]:
                return _call(
                    "complete_task",
                    {"task_id": created[-1]["id"], "result": "source checked", "evidence_refs": []},
                    "a2_complete",
                )
            return _call("submit_findings", SUBMIT_ARGS, "a2_submit")

        client = _LogicClient(logic={
            "agent_001": agent_001_logic,
            "agent_002": agent_002_logic,
            "agent_003": lambda messages: (
                _call("list_tasks", {}, "a3_list") if not _tool_results(messages, "list_tasks")
                else _call("submit_findings", SUBMIT_ARGS, "a3_submit")
            ),
            "agent_004": lambda messages: (
                _call("list_tasks", {}, "a4_list") if not _tool_results(messages, "list_tasks")
                else _call("submit_findings", SUBMIT_ARGS, "a4_submit")
            ),
        })
        summary = self._run(client)
        self.assertEqual(summary["run_validity"]["status"], "valid")
        self.assertEqual(summary["reconciliation"]["status"], "valid")
        events = self._events(summary)

        created = [event for event in events if event["event_type"] == "task_created"]
        self.assertEqual(len(created), 2)
        first_task = next(event for event in created if event["agent_id"] == "agent_001")["payload"]["id"]
        second_task = next(event for event in created if event["agent_id"] == "agent_002")["payload"]["id"]
        for event in events:
            if event["event_type"] == "task_claimed":
                self.assertEqual((event.get("payload") or {}).get("task_id"), first_task if event["agent_id"] == "agent_001" else second_task)

        self.assertEqual(
            [event["agent_id"] for event in events if event["event_type"] == "task_initialization_lease_acquired"],
            AGENT_IDS,
            "canonical bootstrap order must be preserved",
        )
        self.assertEqual(
            [event["payload"]["reason"] for event in events if event["event_type"] == "task_initialization_lease_released"],
            ["task_claimed", "task_claimed", "investigation_started", "investigation_started"],
        )
        # Each later first board observation follows the previous episode's end.
        self.assertLess(self._seq(events, "task_claimed", "agent_001"), self._board_observation_seq(events, "agent_002"))
        self.assertLess(self._seq(events, "task_claimed", "agent_002"), self._board_observation_seq(events, "agent_003"))
        self.assertLess(self._seq(events, "task_initialization_lease_released", "agent_003"), self._board_observation_seq(events, "agent_004"))

        transcripts = Path(summary["run_dir"]) / "logs/transcripts"
        records = [json.loads(line) for line in (transcripts / "agent_002.jsonl").read_text().splitlines()]
        requests = [item["content"] for item in records if item["kind"] == "model_request"]
        # agent_002's allocation round (its second request, the one whose
        # response created its task) must already carry the claimed snapshot.
        allocation_messages = requests[1]["messages"]
        snapshot = json.loads(next(
            message["content"]
            for message in allocation_messages
            if message.get("role") == "tool" and message.get("name") == "list_tasks"
        ))
        observed_first = next(task for task in snapshot if task["id"] == first_task)
        self.assertEqual(observed_first["status"], "claimed")
        self.assertEqual(observed_first["owner"], "agent_001")
        for agent_id, expected_ids in (("agent_003", {first_task, second_task}), ("agent_004", {first_task, second_task})):
            records = [json.loads(line) for line in (transcripts / f"{agent_id}.jsonl").read_text().splitlines()]
            joined = "\n".join(
                json.dumps(item["content"]["messages"], ensure_ascii=False)
                for item in records
                if item["kind"] == "model_request"
            )
            for task_id in expected_ids:
                self.assertIn(task_id, joined, f"{agent_id} must have observed {task_id}")
        results = {item["agent_id"]: item for item in summary["agent_results"]}
        self.assertTrue(all(results[agent_id]["stop_reason"] == "submitted" for agent_id in AGENT_IDS))

    def test_shared_budget_starvation_stress_no_structural_denial(self):
        # agent_001 never uses the board and runs many steps; the other three
        # race to the board immediately, exactly like the T-Pilot 1 v1 live run.
        client = MockLLMClient(scripts={
            "agent_001": [
                *(_read_round(f"a1_read_{index}") for index in range(24)),
                _call("submit_findings", SUBMIT_ARGS, "a1_submit"),
            ],
            **{
                agent_id: [
                    _call("list_tasks", {}, f"{agent_id}_list"),
                    _read_round(f"{agent_id}_read"),
                    _call("submit_findings", SUBMIT_ARGS, f"{agent_id}_submit"),
                ]
                for agent_id in ("agent_002", "agent_003", "agent_004")
            },
        })
        client.max_tokens = 4096
        summary = self._run(client, finalization=False)
        self.assertEqual(summary["run_validity"]["status"], "valid")
        self.assertEqual(summary["reconciliation"]["status"], "valid")
        events = self._events(summary)
        finished_001 = self._seq(events, "agent_finished", "agent_001")
        for peer in ("agent_002", "agent_003", "agent_004"):
            self.assertLess(
                self._board_observation_seq(events, peer),
                finished_001,
                f"{peer} bootstrap must not wait for agent_001 termination",
            )
        # Structural opportunity, not fair quotas: every agent really ran.
        calls_per_agent = {
            agent_id: sum(1 for event in events if event["event_type"] == "llm_call" and event.get("agent_id") == agent_id)
            for agent_id in AGENT_IDS
        }
        self.assertTrue(all(count >= 2 for count in calls_per_agent.values()), calls_per_agent)
        self.assertNotIn(1, calls_per_agent.values(), "no agent may be reduced to a single call by the lease")
        self.assertEqual(
            [event["agent_id"] for event in events if event["event_type"] == "task_initialization_lease_acquired"],
            ["agent_002", "agent_003", "agent_004"],
        )
        skipped = [event for event in events if event["event_type"] == "task_initialization_turn_skipped"]
        self.assertEqual([event["agent_id"] for event in skipped], ["agent_001"])
        self.assertEqual(skipped[0]["payload"]["reason"], "bootstrap_opt_out")
        results = {item["agent_id"]: item for item in summary["agent_results"]}
        self.assertTrue(all(results[agent_id]["stop_reason"] == "submitted" for agent_id in AGENT_IDS))

    def test_all_board_opt_out_gives_every_agent_normal_investigation(self):
        client = MockLLMClient(scripts={
            agent_id: [_read_round(f"{agent_id}_read"), _call("submit_findings", SUBMIT_ARGS, f"{agent_id}_submit")]
            for agent_id in AGENT_IDS
        })
        client.max_tokens = 4096
        summary = self._run(client)
        self.assertEqual(summary["run_validity"]["status"], "valid")
        events = self._events(summary)
        self.assertEqual([event for event in events if event["event_type"] == "task_initialization_lease_acquired"], [])
        self.assertEqual(
            [event["agent_id"] for event in events if event["event_type"] == "task_initialization_turn_skipped"],
            AGENT_IDS,
        )
        calls_per_agent = {
            agent_id: sum(1 for event in events if event["event_type"] == "llm_call" and event.get("agent_id") == agent_id)
            for agent_id in AGENT_IDS
        }
        self.assertTrue(all(count >= 2 for count in calls_per_agent.values()), calls_per_agent)
        results = {item["agent_id"]: item for item in summary["agent_results"]}
        self.assertTrue(all(results[agent_id]["stop_reason"] == "submitted" for agent_id in AGENT_IDS))

    def test_mixed_board_and_non_board_agents(self):
        client = MockLLMClient(scripts={
            "agent_001": [
                _call("list_tasks", {}, "a1_list"),
                _read_round("a1_read0"),
                _call("submit_findings", SUBMIT_ARGS, "a1_submit"),
            ],
            "agent_002": [
                _read_round("a2_read"),
                _call("list_tasks", {}, "a2_list"),
                _call("submit_findings", SUBMIT_ARGS, "a2_submit"),
            ],
            "agent_003": [
                _call("list_tasks", {}, "a3_list"),
                _read_round("a3_read"),
                _call("submit_findings", SUBMIT_ARGS, "a3_submit"),
            ],
            "agent_004": [_call("submit_findings", SUBMIT_ARGS, "a4_submit")],
        })
        client.max_tokens = 4096
        summary = self._run(client)
        self.assertEqual(summary["run_validity"]["status"], "valid")
        self.assertEqual(summary["reconciliation"]["status"], "valid")
        events = self._events(summary)
        skipped = {
            event["agent_id"]: event["payload"]["reason"]
            for event in events
            if event["event_type"] == "task_initialization_turn_skipped"
        }
        self.assertEqual(skipped.get("agent_002"), "bootstrap_opt_out")
        self.assertEqual(skipped.get("agent_004"), "bootstrap_opt_out")
        released_001 = next(
            event["payload"]["reason"]
            for event in events
            if event["event_type"] == "task_initialization_lease_released" and event["agent_id"] == "agent_001"
        )
        self.assertEqual(released_001, "investigation_started")
        results = {item["agent_id"]: item for item in summary["agent_results"]}
        self.assertTrue(all(results[agent_id]["stop_reason"] == "submitted" for agent_id in AGENT_IDS))


class ClosureAndFinalizationV3Test(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_closure_gate_and_full_lifecycle_unchanged_under_v3(self):
        layout = prepare_run_workspace(Path(self.tmp.name) / "run", TARGET_ROOT, 1)
        events = EventLog(layout.logs / "events.jsonl", run_id="lease-v3-closure")
        board = TaskBoard(layout.runtime / "coordination", events, initialization_policy=V3, agent_ids=["agent_001"])
        runner = AgentRunner(
            agent_id="agent_001", mode="structured_team", agent_count=1,
            sandbox=AgentSandbox("agent_001", layout, events, board=board),
            llm=MockLLMClient(), event_log=events,
            transcript_log=TranscriptLog(layout.logs / "transcripts", "lease-v3-closure", events),
            budget=BudgetTracker(hard_team_call_permits=12),
            prompt_profile=T_PILOT_1_PROFILE, finding_schema="repository_pilot_v0",
            completion_policy="convergent_v2", task_closure_policy="task_closure_gate_v1", max_steps=8,
        )
        created = json.loads(runner._dispatch("create_task", '{"description":"one bounded question"}', parent_event_id="evt_parent"))
        runner._dispatch("claim_task", json.dumps({"task_id": created["id"]}), parent_event_id="evt_parent")
        blocked = json.loads(runner._dispatch("submit_findings", json.dumps(SUBMIT_ARGS), parent_event_id="evt_parent"))
        self.assertEqual(blocked["error"]["code"], "task_closure_required")
        read = json.loads(runner._dispatch("read_file", '{"path":"target/app/main.py"}', parent_event_id="evt_parent"))
        self.assertTrue(read.get("evidence_ref"))
        closed = json.loads(
            runner._dispatch(
                "complete_task",
                json.dumps({"task_id": created["id"], "result": "source checked", "evidence_refs": []}),
                parent_event_id="evt_parent",
            )
        )
        self.assertEqual(closed["status"], "completed")
        submitted = json.loads(runner._dispatch("submit_findings", json.dumps(SUBMIT_ARGS), parent_event_id="evt_parent"))
        self.assertTrue(submitted.get("ok"))

    def test_finalization_surface_unchanged_under_v3(self):
        layout = prepare_run_workspace(Path(self.tmp.name) / "final", TARGET_ROOT, 1)
        events = EventLog(layout.logs / "events.jsonl", run_id="lease-v3-finalization")
        board = TaskBoard(layout.runtime / "coordination", events, initialization_policy=V3, agent_ids=["agent_001"])
        runner = AgentRunner(
            agent_id="agent_001", mode="structured_team", agent_count=1,
            sandbox=AgentSandbox("agent_001", layout, events, board=board),
            llm=MockLLMClient(), event_log=events,
            transcript_log=TranscriptLog(layout.logs / "transcripts", "lease-v3-finalization", events),
            budget=BudgetTracker(hard_team_call_permits=1, team_finalization_policy="team_remaining_permits_v1", team_finalization_reserve=1),
            prompt_profile=T_PILOT_1_PROFILE, finding_schema="repository_pilot_v0",
            completion_policy="convergent_v2", team_finalization_policy="team_remaining_permits_v1",
            task_closure_policy="task_closure_gate_v1", max_steps=8,
        )
        tool_names = {item["function"]["name"] for item in runner._tools_for_step()}
        self.assertEqual(tool_names, {"read_file", "submit_findings", "complete_task"})
        submitted = json.loads(runner._dispatch("submit_findings", json.dumps(SUBMIT_ARGS), parent_event_id="evt_parent"))
        self.assertTrue(submitted.get("ok"))


class ContractRegistrationTest(unittest.TestCase):
    def test_v2_manifest_loads_validates_and_freezes_with_lease_v3(self):
        config = load_block_config(Path(__file__).parents[1] / "manifests/t_pilot_1_shared_objective_v2.json")
        config.validate()
        self.assertEqual(config.task_board_sequencing_policy, V3)
        self.assertEqual(config.hard_team_call_permits, 192)
        self.assertEqual(config.prompt_profile, "repository_v1_t_pilot_1_shared_objective")
        with tempfile.TemporaryDirectory() as tmp:
            frozen = BlockRunner(config, Path(tmp)).freeze("t-pilot-1-v2-contract-smoke")
            self.assertTrue(frozen.manifest_path.exists())
            manifest = json.loads(frozen.manifest_path.read_text())
            self.assertEqual(manifest["contract"]["task_board_sequencing_policy"], V3)

    def test_v1_manifest_remains_frozen_on_v2_optional(self):
        config = load_block_config(Path(__file__).parents[1] / "manifests/t_pilot_1_shared_objective_v1.json")
        self.assertEqual(config.task_board_sequencing_policy, "initialization_lease_v2_optional")

    def test_unknown_lease_policy_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = json.loads((Path(__file__).parents[1] / "manifests/t_pilot_1_shared_objective_v2.json").read_text())
            raw["task_board_sequencing_policy"] = "initialization_lease_v4"
            path = Path(tmp) / "bad.json"
            path.write_text(json.dumps(raw))
            with self.assertRaises(ContractViolation):
                load_block_config(path)


if __name__ == "__main__":
    unittest.main()
