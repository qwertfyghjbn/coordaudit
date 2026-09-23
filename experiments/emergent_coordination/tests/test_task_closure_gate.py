"""Zero-network lifecycle-gate tests.

These tests deliberately describe the new contract before the runtime is
changed: a successful terminal submission must not bypass an owned claimed
task, while an already completed (or absent) task remains unaffected.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from experiments.emergent_coordination.harness.agent_loop import AgentRunner
from experiments.emergent_coordination.harness.budget import BudgetTracker
from experiments.emergent_coordination.harness.events import EventLog, TranscriptLog
from experiments.emergent_coordination.harness.llm.client import MockLLMClient
from experiments.emergent_coordination.harness.runner import RunConfig, run_experiment
from experiments.emergent_coordination.harness.task_board import CoordinationError, TaskBoard
from experiments.emergent_coordination.harness.tools.sandbox import AgentSandbox
from experiments.emergent_coordination.harness.workspace import prepare_run_workspace
from experiments.emergent_coordination.harness.paths import TARGET_ROOT


class TaskClosureGateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.layout = prepare_run_workspace(Path(self.tmp.name) / "run", TARGET_ROOT, 1)
        self.events = EventLog(self.layout.logs / "events.jsonl", run_id="closure-test")
        self.board = TaskBoard(self.layout.runtime / "coordination", self.events)
        self.task = self.board.create_task("agent_001", "inspect one focused area")
        self.board.claim_task("agent_001", self.task["id"])

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _runner(self, *, policy: str | None = "task_closure_gate_v1") -> AgentRunner:
        sandbox = AgentSandbox("agent_001", self.layout, self.events, board=self.board)
        return AgentRunner(
            agent_id="agent_001",
            mode="structured_team",
            agent_count=1,
            sandbox=sandbox,
            llm=MockLLMClient(),
            event_log=self.events,
            transcript_log=TranscriptLog(self.layout.logs / "transcripts", "closure-test", self.events),
            budget=BudgetTracker(hard_team_call_permits=12),
            prompt_profile="repository_v1_t4_sequenced_bootstrap_v1",
            finding_schema="repository_pilot_v0",
            completion_policy="convergent_v2",
            team_finalization_policy="team_remaining_permits_v1",
            task_closure_policy=policy,
            max_steps=8,
        )

    def _submit(self, runner: AgentRunner) -> dict:
        return json.loads(runner._dispatch("submit_findings", '{"findings": []}', parent_event_id="evt_parent"))

    def _complete(self, runner: AgentRunner) -> dict:
        return json.loads(
            runner._dispatch(
                "complete_task",
                json.dumps({"task_id": self.task["id"], "result": "checked", "evidence_refs": []}),
                parent_event_id="evt_parent",
            )
        )

    def test_claimed_task_direct_submit_is_rejected(self):
        result = self._submit(self._runner())
        self.assertEqual(result["error"]["code"], "task_closure_required")
        self.assertEqual(self.board._read_task(self.task["id"])["status"], "claimed")

    def test_claimed_task_complete_then_submit_succeeds(self):
        self._complete(self._runner())
        self.assertTrue(self._submit(self._runner()).get("ok"))

    def test_completed_task_submit_is_unaffected(self):
        runner = self._runner()
        self._complete(runner)
        self.assertTrue(self._submit(runner).get("ok"))

    def test_no_owned_task_submit_is_unaffected(self):
        runner = self._runner()
        self.board.release_task("agent_001", self.task["id"])
        self.assertTrue(self._submit(runner).get("ok"))

    def test_invalid_complete_task_does_not_auto_complete(self):
        runner = self._runner()
        result = json.loads(
            runner._dispatch("complete_task", json.dumps({"task_id": "task_missing"}), parent_event_id="evt_parent")
        )
        self.assertIn("error", result)
        self.assertEqual(self.board._read_task(self.task["id"])["status"], "claimed")

    def test_non_owner_cannot_close_claimed_task(self):
        with self.assertRaises(CoordinationError):
            self.board.complete_task("agent_002", self.task["id"], "bad", [])
        self.assertEqual(self.board._read_task(self.task["id"])["status"], "claimed")

    def test_invalid_evidence_refs_do_not_close_task(self):
        with self.assertRaises(CoordinationError):
            self.board.complete_task("agent_001", self.task["id"], "checked", "not-a-list")
        self.assertEqual(self.board._read_task(self.task["id"])["status"], "claimed")

    def test_complete_transition_is_exactly_once(self):
        runner = self._runner()
        self._complete(runner)
        result = json.loads(
            runner._dispatch(
                "complete_task",
                json.dumps({"task_id": self.task["id"], "result": "second", "evidence_refs": []}),
                parent_event_id="evt_parent",
            )
        )
        self.assertIn("error", result)
        self.assertEqual(
            len([e for e in self.events.read_all() if e["event_type"] == "task_completed"]),
            1,
        )

    def test_gate_does_not_issue_a_provider_permit(self):
        runner = self._runner()
        before = runner.budget.snapshot()["attempted_llm_calls"]
        self._submit(runner)
        after = runner.budget.snapshot()["attempted_llm_calls"]
        self.assertEqual(before, after)

    def test_gate_never_auto_completes(self):
        runner = self._runner()
        self._submit(runner)
        self.assertIsNone(self.board._read_task(self.task["id"])["result"])
        self.assertEqual(self.board._read_task(self.task["id"])["status"], "claimed")

    def test_gate_emits_deterministic_event(self):
        self._submit(self._runner())
        events = [e for e in self.events.read_all() if e["event_type"] == "task_closure_gate_rejected"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["payload"]["task_ids"], [self.task["id"]])

    def test_legacy_policy_allows_historical_submit_semantics(self):
        self.assertTrue(self._submit(self._runner(policy=None)).get("ok"))

    def test_finalization_surface_keeps_complete_task_available(self):
        runner = self._runner()
        runner._step = 4
        tools = runner._tools_for_step()
        self.assertIn("complete_task", [tool["function"]["name"] for tool in tools])

    def test_sequencing_policy_is_not_touched_by_closure_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary = run_experiment(
                RunConfig(
                    mode="structured_team",
                    agent_count=1,
                    model="mock",
                    budgets={"hard_team_call_permits": 4},
                    runs_dir=Path(tmp),
                    max_steps=2,
                    task_board_sequencing_policy="initialization_lease_v1",
                    task_closure_policy="task_closure_gate_v1",
                ),
                MockLLMClient(default=[]),
            )
            events = [json.loads(line) for line in (Path(summary["run_dir"]) / "logs/events.jsonl").read_text().splitlines()]
            self.assertTrue(any(e["event_type"] == "run_started" for e in events))


if __name__ == "__main__":
    unittest.main()
