"""Deterministic, zero-network tests for the neutral T4 POST_SYNC window."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from experiments.emergent_coordination.analysis.analyze_run import _result_sync_metrics
from experiments.emergent_coordination.harness.agent_loop import AgentRunner
from experiments.emergent_coordination.harness.budget import BudgetExhausted, BudgetTracker, TokenUsage
from experiments.emergent_coordination.harness.events import EventLog, TranscriptLog
from experiments.emergent_coordination.harness.llm.client import LLMResponse, MockLLMClient
from experiments.emergent_coordination.harness.paths import TARGET_ROOT
from experiments.emergent_coordination.harness.runner import RunConfig, run_experiment
from experiments.emergent_coordination.harness.task_board import TaskBoard
from experiments.emergent_coordination.harness.tools.sandbox import AgentSandbox
from experiments.emergent_coordination.harness.workspace import prepare_run_workspace


def _tool(name: str, arguments: dict, call_id: str) -> LLMResponse:
    return LLMResponse(
        content=None,
        tool_calls=[{"id": call_id, "name": name, "arguments": json.dumps(arguments)}],
        usage=TokenUsage(input_tokens=1, output_tokens=1, model="mock"),
        raw={"mock": True},
        model_metadata={"finish_reason": "tool_calls"},
    )


class PostSyncWindowV1Test(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.agent_ids = ("agent_001", "agent_002")
        self.layout = prepare_run_workspace(Path(self.tmp.name) / "run", TARGET_ROOT, len(self.agent_ids))
        self.events = EventLog(self.layout.logs / "events.jsonl", run_id="post-sync-window-test")
        self.board = TaskBoard(
            self.layout.runtime / "coordination", self.events,
            agent_ids=list(self.agent_ids), result_sync_policy="result_sync_v1",
        )
        self.tasks = []
        for agent_id in self.agent_ids:
            task = self.board.create_task(agent_id, f"scope for {agent_id}")
            self.board.claim_task(agent_id, task["id"])
            self.tasks.append(task["id"])
        self.board.complete_task("agent_001", self.tasks[0], "own", ["evt_own"])
        self.board.complete_task("agent_002", self.tasks[1], "foreign", ["evt_foreign"])

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _runner(self, agent_id: str, responses: list[LLMResponse], *, version: int = 1) -> AgentRunner:
        budget = BudgetTracker(
            hard_team_call_permits=8,
            post_sync_reservation_per_agent=4,
            post_sync_eligible_agents=self.agent_ids,
            team_finalization_policy="team_remaining_permits_v1",
            team_finalization_reserve=2,
        )
        return AgentRunner(
            agent_id=agent_id,
            mode="structured_team",
            agent_count=2,
            sandbox=AgentSandbox(agent_id, self.layout, self.events, board=self.board),
            llm=MockLLMClient(default=responses),
            event_log=self.events,
            transcript_log=TranscriptLog(self.layout.logs / "transcripts", "post-sync-window-test", self.events),
            budget=budget,
            prompt_profile=f"repository_v1_t4_post_sync_window_v{version}",
            finding_schema="repository_pilot_v0",
            completion_policy="convergent_v2",
            team_finalization_policy="team_remaining_permits_v1",
            task_closure_policy="task_closure_gate_v1",
            result_sync_policy="result_sync_v1",
            post_sync_window_policy=f"t4_post_sync_window_v{version}",
            max_steps=1,
        )

    def test_general_pool_exhaustion_does_not_consume_post_sync_reservation(self):
        budget = BudgetTracker(
            hard_team_call_permits=10,
            post_sync_reservation_per_agent=2,
            post_sync_eligible_agents=("agent_001", "agent_002"),
        )
        for _ in range(6):
            permit = budget.acquire_call_permit("agent_001")
            budget.settle_call_permit(permit, outcome="succeeded")
        with self.assertRaisesRegex(BudgetExhausted, "post_sync_reservation_protected"):
            budget.acquire_call_permit("agent_001")
        budget.open_post_sync_window("agent_001")
        permit = budget.acquire_call_permit("agent_001", call_kind="post_sync_initial")
        budget.settle_call_permit(permit, outcome="succeeded")
        self.assertEqual(budget.snapshot()["attempted_llm_calls"], 7)
        self.assertEqual(budget.snapshot()["post_sync_reservation"]["normal_work_permits"], 6)

    def test_every_opened_window_gets_a_model_visible_admitted_call(self):
        for agent_id in self.agent_ids:
            runner = self._runner(agent_id, [_tool("submit_findings", {"findings": []}, f"submit-{agent_id}")])
            self.assertEqual(runner.run()["stop_reason"], "submitted")
        events = self.events.read_all()
        for event_type in ("post_sync_window_opened", "post_sync_instruction_model_visible", "post_sync_provider_call_admitted"):
            self.assertEqual({event["agent_id"] for event in events if event["event_type"] == event_type}, set(self.agent_ids))

    def test_four_of_four_static_reservations_admit_first_post_sync_request(self):
        agent_ids = tuple(f"agent_{index:03d}" for index in range(1, 5))
        budget = BudgetTracker(
            hard_team_call_permits=192,
            post_sync_reservation_per_agent=4,
            post_sync_eligible_agents=agent_ids,
        )
        # Consume the entire 176-call general pool first: this reproduces the
        # boundary that previously stranded RESULT_SYNC observers.
        for _ in range(176):
            permit = budget.acquire_call_permit("agent_001")
            budget.settle_call_permit(permit, outcome="succeeded")
        for agent_id in agent_ids:
            budget.open_post_sync_window(agent_id)
            permit = budget.acquire_call_permit(agent_id, call_kind="post_sync_initial")
            budget.settle_call_permit(permit, outcome="succeeded")
        self.assertEqual(budget.snapshot()["attempted_llm_calls"], 180)
        self.assertEqual(
            [budget.snapshot()["post_sync_reservation"]["windows"][agent_id]["initial_attempts"] for agent_id in agent_ids],
            [1, 1, 1, 1],
        )

    def test_direct_submit_is_legal_without_verification(self):
        runner = self._runner("agent_001", [_tool("submit_findings", {"findings": []}, "submit")])
        self.assertEqual(runner.run()["stop_reason"], "submitted")
        self.assertFalse(any(event["event_type"] == "verification_action_attempted" for event in self.events.read_all()))
        requests = [record for record in runner.transcript_log.read_all() if record["kind"] == "model_request"]
        self.assertEqual(len(requests), 1)
        names = {item["function"]["name"] for item in requests[0]["content"]["tools"]}
        self.assertEqual(names, {"read_file", "submit_findings"})

    def test_post_sync_does_not_restore_coordination_or_shell_tools(self):
        runner = self._runner("agent_001", [])
        before_creates = len([event for event in self.events.read_all() if event["event_type"] == "task_created"])
        runner._prepare_result_sync()
        for name, arguments in (
            ("create_task", {"description": "must stay closed"}),
            ("claim_task", {"task_id": self.tasks[0]}),
            ("run_shell", {"command": "rg token target"}),
        ):
            result = json.loads(runner._dispatch(name, json.dumps(arguments), parent_event_id="evt_parent"))
            self.assertEqual(result["error"]["code"], "prohibited_tool_during_finalization")
        self.assertEqual(len([event for event in self.events.read_all() if event["event_type"] == "task_created"]), before_creates)

    def test_bounded_verification_forces_evidence_consumption_call_then_submit(self):
        runner = self._runner("agent_001", [
            _tool("read_file", {"path": "target/package.json"}, "verify"),
            _tool("submit_findings", {"findings": []}, "submit"),
        ])
        self.assertEqual(runner.run()["stop_reason"], "submitted")
        events = self.events.read_all()
        self.assertEqual(len([event for event in events if event["event_type"] == "verification_action_attempted"]), 1)
        self.assertEqual(len([event for event in events if event["event_type"] == "verification_evidence_model_visible"]), 1)
        requests = [record for record in runner.transcript_log.read_all() if record["kind"] == "model_request"]
        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[1]["content"]["messages"][-1]["role"], "tool")
        self.assertEqual(requests[1]["content"]["messages"][-1]["name"], "read_file")
        self.assertEqual(
            {item["function"]["name"] for item in requests[1]["content"]["tools"]}, {"submit_findings"}
        )
        self.assertNotIn("run_shell", json.dumps(requests[0]["content"]["tools"]))

    def test_one_agent_unused_reservation_cannot_erase_another_agents_guarantee(self):
        first = self._runner("agent_001", [_tool("submit_findings", {"findings": []}, "submit-1")])
        self.assertEqual(first.run()["stop_reason"], "submitted")
        second = self._runner("agent_002", [_tool("submit_findings", {"findings": []}, "submit-2")])
        self.assertEqual(second.run()["stop_reason"], "submitted")
        self.assertEqual(
            len([event for event in self.events.read_all() if event["event_type"] == "post_sync_provider_call_admitted"]), 2
        )

    def test_retry_accounting_consumes_reserved_permits_without_refund(self):
        budget = BudgetTracker(
            hard_team_call_permits=8,
            post_sync_reservation_per_agent=4,
            post_sync_eligible_agents=("agent_001", "agent_002"),
        )
        budget.open_post_sync_window("agent_001")
        first = budget.acquire_call_permit("agent_001", call_kind="post_sync_initial")
        budget.settle_call_permit(first, outcome="timeout")
        retry = budget.acquire_call_permit("agent_001", retry_of=first.permit_id, call_kind="post_sync_initial")
        budget.settle_call_permit(retry, outcome="succeeded")
        budget.mark_post_sync_verification_attempted("agent_001")
        followup = budget.acquire_call_permit("agent_001", call_kind="post_sync_followup")
        budget.settle_call_permit(followup, outcome="provider_error")
        ledger = budget.snapshot()["permit_ledger"]
        self.assertEqual([entry["outcome"] for entry in ledger], ["timeout", "succeeded", "provider_error"])
        self.assertEqual([entry["call_kind"] for entry in ledger], ["post_sync_initial", "post_sync_initial", "post_sync_followup"])

    def test_v2_prompt_has_optional_review_without_legacy_inspection_gate(self):
        runner = self._runner("agent_001", [_tool("submit_findings", {"findings": []}, "submit")], version=2)
        self.assertEqual(runner.run()["stop_reason"], "submitted")
        request = next(record for record in runner.transcript_log.read_all() if record["kind"] == "model_request")
        content = "\n".join(str(message.get("content") or "") for message in request["content"]["messages"])
        self.assertIn("You may also decide that no check is useful", content)
        self.assertNotIn("Inspection is required", content)
        self.assertNotIn("In a visible response, identify", content)
        self.assertNotIn("list_tasks` operation remains authorized", content)

    def test_v2_invalid_submission_gets_submit_only_repair_call(self):
        malformed = LLMResponse(
            content=None,
            tool_calls=[{"id": "bad", "name": "submit_findings", "arguments": "{invalid"}],
            usage=TokenUsage(input_tokens=1, output_tokens=1, model="mock"),
            raw={"mock": True}, model_metadata={"finish_reason": "tool_calls"},
        )
        runner = self._runner("agent_001", [malformed, _tool("submit_findings", {"findings": []}, "fixed")], version=2)
        self.assertEqual(runner.run()["stop_reason"], "submitted")
        requests = [record for record in runner.transcript_log.read_all() if record["kind"] == "model_request"]
        self.assertEqual(len(requests), 2)
        self.assertEqual([entry["call_kind"] for entry in runner.budget.snapshot()["permit_ledger"]], ["post_sync_initial", "post_sync_submit"])
        self.assertEqual({tool["function"]["name"] for tool in requests[1]["content"]["tools"]}, {"submit_findings"})

    def test_v2_second_read_is_rejected_then_submit_can_recover(self):
        runner = self._runner("agent_001", [
            _tool("read_file", {"path": "target/README.md"}, "verify"),
            _tool("read_file", {"path": "target/README.md"}, "second-read"),
            _tool("submit_findings", {"findings": []}, "submit"),
        ], version=2)
        self.assertEqual(runner.run()["stop_reason"], "submitted")
        events = self.events.read_all()
        self.assertEqual(sum(event["event_type"] == "verification_action_attempted" for event in events), 1)
        self.assertEqual(sum(event["event_type"] == "verification_evidence_model_visible" for event in events), 1)
        self.assertEqual(sum(event["event_type"] == "file_read" and event["agent_id"] == "agent_001" for event in events), 1)
        requests = [record for record in runner.transcript_log.read_all() if record["kind"] == "model_request"]
        self.assertEqual(len(requests), 3)
        self.assertEqual({tool["function"]["name"] for tool in requests[2]["content"]["tools"]}, {"submit_findings"})
        self.assertEqual([entry["call_kind"] for entry in runner.budget.snapshot()["permit_ledger"]], ["post_sync_initial", "post_sync_followup", "post_sync_submit"])

    def test_v2_repair_stays_inside_own_four_permits(self):
        budget = BudgetTracker(
            hard_team_call_permits=8,
            post_sync_reservation_per_agent=4,
            post_sync_eligible_agents=self.agent_ids,
        )
        budget.open_post_sync_window("agent_001")
        kinds = ("post_sync_initial", "post_sync_initial", "post_sync_submit", "post_sync_submit")
        for index, kind in enumerate(kinds):
            permit = budget.acquire_call_permit("agent_001", call_kind=kind)
            budget.settle_call_permit(permit, outcome="timeout" if index == 0 else "succeeded")
        with self.assertRaisesRegex(BudgetExhausted, "post_sync_reservation_exhausted"):
            budget.acquire_call_permit("agent_001", call_kind="post_sync_submit")
        budget.open_post_sync_window("agent_002")
        permit = budget.acquire_call_permit("agent_002", call_kind="post_sync_initial")
        budget.settle_call_permit(permit, outcome="succeeded")
        self.assertEqual(budget.snapshot()["attempted_llm_calls"], 5)

    def test_analyzer_distinguishes_missing_opportunity_from_model_choice(self):
        missing = _result_sync_metrics([], [], ["agent_001"], [])["per_agent"]["agent_001"]
        self.assertEqual(missing["verification_opportunity_status"], "no_post_sync_provider_opportunity")
        self.events.emit("post_sync_provider_call_admitted", agent_id="agent_001", payload={})
        delivered = _result_sync_metrics(self.events.read_all(), [], ["agent_001"], [])["per_agent"]["agent_001"]
        self.assertEqual(delivered["verification_opportunity_status"], "opportunity_delivered_model_chose_not_to_verify")

    def test_zero_network_t4_scheduler_completes_and_reconciles_without_deadlock(self):
        class LifecycleClient:
            max_tokens = 4096
            thinking_mode = "disabled"
            temperature = 0.0

            def complete(self, messages, tools, *, agent_id, tool_choice=None):
                if any("bounded POST_SYNC review window" in str(message.get("content")) for message in messages):
                    return _tool("submit_findings", {"schema_version": "repository-v1", "findings": []}, f"post-{agent_id}")
                last = messages[-1]
                if last.get("role") == "user":
                    return _tool("create_task", {"description": f"scope {agent_id}"}, f"create-{agent_id}")
                parsed = json.loads(last.get("content") or "{}") if last.get("role") == "tool" else {}
                if last.get("name") == "create_task":
                    return _tool("claim_task", {"task_id": parsed["id"]}, f"claim-{agent_id}")
                if last.get("name") == "claim_task":
                    return _tool("complete_task", {"task_id": parsed["id"], "result": agent_id, "evidence_refs": []}, f"complete-{agent_id}")
                return _tool("list_tasks", {}, f"wait-{agent_id}")

        for version in (1, 2):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as tmp:
                summary = run_experiment(
                    RunConfig(
                        mode="structured_team", agent_count=4, model="mock",
                        budgets={"hard_team_call_permits": 192, "post_sync_reservation_per_agent": 4, "max_provider_retries": 0},
                        max_steps=20, completion_policy="convergent_v2", team_completion_policy="all_agents_terminal_v1",
                        team_finalization_policy="team_remaining_permits_v1", team_finalization_reserve=32,
                        task_board_sequencing_policy="initialization_lease_v1", task_closure_policy="task_closure_gate_v1",
                        result_sync_policy="result_sync_v1", post_sync_window_policy=f"t4_post_sync_window_v{version}",
                        prompt_profile=f"repository_v1_t4_post_sync_window_v{version}", runs_dir=Path(tmp),
                        case_id="flowise_3_1_3_repository_v1", evaluate=False,
                    ), LifecycleClient(),
                )
                metrics = json.loads((Path(summary["run_dir"]) / "metrics.json").read_text(encoding="utf-8"))
                self.assertEqual(summary["run_validity"]["status"], "valid")
                self.assertEqual(summary["reconciliation"]["status"], "valid")
                self.assertTrue(metrics["result_sync"]["exactly_once"])
                self.assertEqual(metrics["result_sync"]["post_sync_opportunity"]["provider_call_admitted_count"], 4)


if __name__ == "__main__":
    unittest.main()
