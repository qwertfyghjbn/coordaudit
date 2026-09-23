from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from experiments.emergent_coordination.harness.agent_loop import AgentRunner
from experiments.emergent_coordination.harness.budget import BudgetExhausted, BudgetTracker, TokenUsage
from experiments.emergent_coordination.harness.events import EventLog, TranscriptLog
from experiments.emergent_coordination.harness.llm.client import LLMResponse, MockLLMClient
from experiments.emergent_coordination.harness.paths import TARGET_ROOT
from experiments.emergent_coordination.harness.task_board import CoordinationError, TaskBoard
from experiments.emergent_coordination.harness.tools.sandbox import AgentSandbox
from experiments.emergent_coordination.harness.workspace import prepare_run_workspace
from experiments.emergent_coordination.harness.runner import RunConfig, run_experiment


def _submit_response() -> LLMResponse:
    return LLMResponse(
        content=None,
        tool_calls=[
            {
                "id": "submit",
                "name": "submit_findings",
                "arguments": json.dumps({"findings": []}),
            }
        ],
        usage=TokenUsage(input_tokens=1, output_tokens=1, model="mock"),
        raw={"mock": True},
        model_metadata={"finish_reason": "tool_calls"},
    )


class _LifecycleMockClient:
    """A zero-network model stub that follows only the public tool results."""

    max_tokens = 4096
    thinking_mode = "disabled"
    temperature = 0.0

    def __init__(self) -> None:
        self.calls: dict[str, int] = {}

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]], *, agent_id: str, tool_choice=None) -> LLMResponse:
        self.calls[agent_id] = self.calls.get(agent_id, 0) + 1
        if any("RESULT_SYNC (result_sync_v1)" in str(message.get("content")) for message in messages):
            if messages[-1].get("role") == "user" and "RESULT_SYNC (result_sync_v1)" in str(messages[-1].get("content")):
                return self._call("list_tasks", {}, f"sync-list-{agent_id}-{self.calls[agent_id]}")
        last = messages[-1]
        if last.get("role") == "user":
            return self._call("create_task", {"description": f"mock scope for {agent_id}"}, f"create-{agent_id}")
        if last.get("role") == "tool":
            content = str(last.get("content") or "")
            try:
                parsed = json.loads(content)
            except json.JSONDecodeError:
                parsed = {}
            if last.get("name") == "create_task":
                return self._call("claim_task", {"task_id": parsed["id"]}, f"claim-{agent_id}")
            if last.get("name") == "claim_task":
                return self._call(
                    "complete_task",
                    {"task_id": parsed["id"], "result": f"completed by {agent_id}", "evidence_refs": []},
                    f"complete-{agent_id}",
                )
            if last.get("name") == "complete_task":
                return self._call("list_tasks", {}, f"wait-list-{agent_id}-{self.calls[agent_id]}")
            if last.get("name") == "list_tasks":
                tasks = parsed if isinstance(parsed, list) else []
                if tasks and all(task.get("status") == "completed" for task in tasks):
                    return self._call(
                        "submit_findings",
                        {"schema_version": "repository-v1", "findings": []},
                        f"submit-{agent_id}",
                    )
                return self._call("list_tasks", {}, f"wait-list-{agent_id}-{self.calls[agent_id]}")
        return _submit_response()

    @staticmethod
    def _call(name: str, arguments: dict[str, Any], call_id: str) -> LLMResponse:
        return LLMResponse(
            content=None,
            tool_calls=[{"id": call_id, "name": name, "arguments": json.dumps(arguments)}],
            usage=TokenUsage(input_tokens=1, output_tokens=1, model="mock"),
            raw={"mock": True},
            model_metadata={"finish_reason": "tool_calls"},
        )


class ResultSyncV1Test(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.layout = prepare_run_workspace(Path(self.tmp.name) / "run", TARGET_ROOT, 2)
        self.events = EventLog(self.layout.logs / "events.jsonl", run_id="result-sync-test")
        self.board = TaskBoard(
            self.layout.runtime / "coordination",
            self.events,
            agent_ids=["agent_001", "agent_002"],
            result_sync_policy="result_sync_v1",
        )
        self.tasks = []
        for agent_id in ("agent_001", "agent_002"):
            task = self.board.create_task(agent_id, f"scope for {agent_id}")
            self.board.claim_task(agent_id, task["id"])
            self.tasks.append(task["id"])

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _complete_all(self) -> None:
        self.board.complete_task("agent_001", self.tasks[0], "own result", ["evt_own"])
        self.board.complete_task("agent_002", self.tasks[1], "foreign result", ["evt_foreign"])

    def _runner(self, agent_id: str, *, prompt_profile: str = "repository_v1_t4_result_sync_v1") -> AgentRunner:
        sandbox = AgentSandbox(agent_id, self.layout, self.events, board=self.board)
        return AgentRunner(
            agent_id=agent_id,
            mode="structured_team",
            agent_count=2,
            sandbox=sandbox,
            llm=MockLLMClient(default=[_submit_response()]),
            event_log=self.events,
            transcript_log=TranscriptLog(self.layout.logs / "transcripts", "result-sync-test", self.events),
            budget=BudgetTracker(hard_team_call_permits=12),
            prompt_profile=prompt_profile,
            finding_schema="repository_pilot_v0",
            completion_policy="convergent_v2",
            team_finalization_policy="team_remaining_permits_v1",
            task_closure_policy="task_closure_gate_v1",
            result_sync_policy="result_sync_v1",
            max_steps=8,
        )

    def test_initial_tasks_trigger_result_sync_exactly_once(self):
        self.board.complete_task("agent_001", self.tasks[0], "own result", ["evt_own"])
        self.assertFalse(self.board.result_sync_status("agent_001")["triggered"])

        self.board.complete_task("agent_002", self.tasks[1], "foreign result", ["evt_foreign"])
        self.assertTrue(self.board.result_sync_status("agent_001")["triggered"])
        self.assertEqual(
            len([event for event in self.events.read_all() if event["event_type"] == "result_sync_triggered"]),
            1,
        )
        with self.assertRaises(CoordinationError):
            self.board.complete_task("agent_002", self.tasks[1], "duplicate", [])
        self.assertEqual(
            len([event for event in self.events.read_all() if event["event_type"] == "result_sync_triggered"]),
            1,
        )

    def test_raw_completed_artifacts_are_visible_with_foreign_provenance(self):
        self._complete_all()
        snapshot = self.board.observe_result_sync("agent_001")
        assert snapshot is not None
        self.assertEqual(snapshot["foreign_completed_task_ids"], [self.tasks[1]])
        foreign = next(item for item in snapshot["completed_tasks"] if item["id"] == self.tasks[1])
        self.assertEqual(foreign["owner"], "agent_002")
        self.assertEqual(foreign["result"], "foreign result")
        self.assertEqual(foreign["evidence_refs"], ["evt_foreign"])
        self.assertEqual(self.board.observe_result_sync("agent_001"), snapshot)
        self.assertEqual(
            len([event for event in self.events.read_all() if event["event_type"] == "result_sync_observed" and event["agent_id"] == "agent_001"]),
            1,
        )

    def test_post_sync_inspection_v2_message_is_delivered_only_after_sync_without_model_call(self):
        runner = self._runner("agent_001")
        runner.prompt_profile = "repository_v1_t4_post_sync_inspection_v2"
        runner._prepare_result_sync()
        self.assertEqual(runner._messages, [])
        self._complete_all()
        runner._prepare_result_sync()
        self.assertEqual(len(runner._messages), 1)
        message = runner._messages[0]["content"]
        self.assertIn("RESULT_SYNC (result_sync_v1)", message)
        self.assertIn("Inspect at least one completed task owned by another agent", message)
        self.assertIn("foreign result", message)
        self.assertIn("evt_foreign", message)
        self.assertIn("list_tasks", message)
        self.assertEqual(runner.budget.snapshot()["attempted_llm_calls"], 0)

    def test_post_sync_relevance_v1_message_arrives_after_closure_without_budget_change(self):
        runner = self._runner("agent_001", prompt_profile="repository_v1_t4_post_sync_relevance_v1")
        self.assertTrue(runner._task_lifecycle_prompt)
        runner._prepare_result_sync()
        self.assertEqual(runner._messages, [])
        self._complete_all()
        runner._prepare_result_sync()
        self.assertEqual(len(runner._messages), 1)
        message = runner._messages[0]["content"]
        self.assertIn("task_", message)
        self.assertIn("evt_foreign", message)
        self.assertIn("no direct relation", message)
        self.assertEqual(runner.budget.snapshot()["attempted_llm_calls"], 0)

    def test_permission_profile_allows_optional_target_read_during_finalization(self):
        self._complete_all()
        runner = self._runner("agent_001", prompt_profile="repository_v1_t4_post_sync_verification_permission_v1")
        runner.budget = BudgetTracker(
            hard_team_call_permits=12,
            team_finalization_policy="team_remaining_permits_v1",
            team_finalization_reserve=12,
        )
        read = LLMResponse(
            content="Checking the named foreign target before submission.",
            tool_calls=[{"id": "verify", "name": "read_file", "arguments": json.dumps({"path": "target/README.md"})}],
            usage=TokenUsage(input_tokens=1, output_tokens=1, model="mock"),
            raw={"mock": True},
        )
        runner.llm = MockLLMClient(default=[read, _submit_response()])
        result = runner.run()
        self.assertEqual(result["stop_reason"], "submitted")
        requests = [record for record in runner.transcript_log.read_all() if record["kind"] == "model_request"]
        self.assertEqual(len(requests), 2)
        messages = requests[0]["content"]["messages"]
        self.assertIn("Team finalization phase is active", messages[-2]["content"])
        self.assertIn("one bounded, target-aligned verification action", messages[-1]["content"])
        first_tools = {item["function"]["name"] for item in requests[0]["content"]["tools"]}
        self.assertIn("read_file", first_tools)
        self.assertNotIn("run_shell", first_tools)
        events = self.events.read_all()
        self.assertEqual(len([event for event in events if event["event_type"] == "file_read" and event["agent_id"] == "agent_001"]), 1)
        self.assertEqual(len([event for event in events if event["event_type"] == "result_sync_observed" and event["agent_id"] == "agent_001"]), 1)
        denied = json.loads(runner._dispatch("run_shell", json.dumps({"command": "rg pattern target"}), parent_event_id="evt_parent"))
        self.assertEqual(denied["error"]["code"], "prohibited_tool_during_finalization")
        self.assertEqual(runner.budget.snapshot()["attempted_llm_calls"], 2)

    def test_permission_profile_does_not_force_verification(self):
        self._complete_all()
        runner = self._runner("agent_001", prompt_profile="repository_v1_t4_post_sync_verification_permission_v1")
        result = runner.run()
        self.assertEqual(result["stop_reason"], "submitted")
        self.assertFalse(any(event["event_type"] == "file_read" for event in self.events.read_all()))
        self.assertEqual(runner.budget.snapshot()["attempted_llm_calls"], 1)

    def test_zero_network_relevance_profile_delivers_instruction_to_model(self):
        self._complete_all()
        runner = self._runner("agent_001", prompt_profile="repository_v1_t4_post_sync_relevance_v1")
        result = runner.run()
        self.assertEqual(result["stop_reason"], "submitted")
        requests = [
            record for record in runner.transcript_log.read_all()
            if record["agent_id"] == "agent_001" and record["kind"] == "model_request"
        ]
        self.assertEqual(len(requests), 1)
        messages = requests[0]["content"]["messages"]
        self.assertIn("no direct relation", messages[-1]["content"])
        self.assertIn("evt_foreign", messages[-1]["content"])
        self.assertEqual(
            len([event for event in self.events.read_all() if event["event_type"] == "result_sync_observed" and event["agent_id"] == "agent_001"]),
            1,
        )

    def test_submission_waits_without_consuming_permit_then_succeeds_after_visibility(self):
        self.board.complete_task("agent_001", self.tasks[0], "own result", ["evt_own"])
        runner = self._runner("agent_001")
        before = runner.budget.snapshot()["attempted_llm_calls"]
        pending = json.loads(runner._dispatch("submit_findings", '{"findings": []}', parent_event_id="evt_parent"))
        self.assertEqual(pending["error"]["code"], "result_sync_pending")
        self.assertEqual(runner.budget.snapshot()["attempted_llm_calls"], before)

        self.board.complete_task("agent_002", self.tasks[1], "foreign result", ["evt_foreign"])
        runner._prepare_result_sync()
        self.assertTrue(json.loads(runner._dispatch("submit_findings", '{"findings": []}', parent_event_id="evt_parent"))["ok"])

    def test_model_visible_context_can_be_inspected_without_forced_reuse(self):
        self._complete_all()
        runner = self._runner("agent_001")
        result = runner.run()
        self.assertEqual(result["stop_reason"], "submitted")
        transcripts = self.events.read_all()
        self.assertTrue(any(event["event_type"] == "result_sync_observed" and event["agent_id"] == "agent_001" for event in transcripts))
        transcript_text = "\n".join(
            json.dumps(record, ensure_ascii=False)
            for record in TranscriptLog(self.layout.logs / "transcripts", "result-sync-test", self.events).read_all()
        )
        self.assertIn("RESULT_SYNC (result_sync_v1)", transcript_text)
        self.assertIn("foreign result", transcript_text)
        self.assertEqual(result["findings"]["findings"], [])

    def test_finalization_keeps_existing_read_only_board_observation(self):
        self._complete_all()
        runner = self._runner("agent_001")
        runner.budget = BudgetTracker(
            hard_team_call_permits=4,
            team_finalization_policy="team_remaining_permits_v1",
            team_finalization_reserve=4,
        )
        runner.budget.register_agent("agent_001")
        runner._prepare_result_sync()
        names = [tool["function"]["name"] for tool in runner._tools_for_step()]
        self.assertIn("list_tasks", names)
        self.assertIn("complete_task", names)
        self.assertEqual(runner.budget.snapshot()["enforced_limits"]["hard_team_call_permits"], 4)

    def test_result_sync_does_not_wait_for_or_consume_exhausted_permit(self):
        budget = BudgetTracker(hard_team_call_permits=1)
        budget.register_agent("agent_001")
        permit = budget.acquire_call_permit("agent_001")
        budget.settle_call_permit(permit, outcome="succeeded", usage=TokenUsage(input_tokens=1, output_tokens=1))
        self._complete_all()
        before = budget.snapshot()["attempted_llm_calls"]

        snapshot = self.board.observe_result_sync("agent_001")

        self.assertIsNotNone(snapshot)
        self.assertEqual(budget.snapshot()["attempted_llm_calls"], before)
        with self.assertRaises(BudgetExhausted):
            budget.acquire_call_permit("agent_001")

    def test_zero_network_run_exercises_scheduler_transcript_and_team_completion(self):
        llm = _LifecycleMockClient()
        with tempfile.TemporaryDirectory() as tmp:
            summary = run_experiment(
                RunConfig(
                    mode="structured_team",
                    agent_count=2,
                    model="mock",
                    model_profile={"requested_model": "mock", "max_output_tokens": 4096},
                    budgets={
                        "hard_team_call_permits": 40,
                        "max_provider_retries": 0,
                        "team_finalization_policy": "team_remaining_permits_v1",
                        "team_finalization_reserve": 8,
                    },
                    max_steps=20,
                    completion_policy="convergent_v2",
                    team_completion_policy="all_agents_terminal_v1",
                    team_finalization_policy="team_remaining_permits_v1",
                    team_finalization_reserve=8,
                    task_board_sequencing_policy="initialization_lease_v1",
                    task_closure_policy="task_closure_gate_v1",
                    result_sync_policy="result_sync_v1",
                    prompt_profile="repository_v1_t4_result_sync_v1",
                    runs_dir=Path(tmp),
                    case_id="flowise_3_1_3_repository_v1",
                    evaluate=False,
                ),
                llm,
            )
            run_dir = Path(summary["run_dir"])
            metrics = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
            events = [json.loads(line) for line in (run_dir / "logs" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(summary["run_validity"]["status"], "valid")
        self.assertEqual(summary["reconciliation"]["status"], "valid")
        self.assertEqual(len([event for event in events if event["event_type"] == "result_sync_triggered"]), 1)
        self.assertEqual(len([event for event in events if event["event_type"] == "result_sync_observed"]), 2)
        self.assertEqual(len([event for event in events if event["event_type"] == "task_completed"]), 2)
        # The mock only re-lists the board; it does not emit the explicit
        # task/evidence/relevance inspection declaration required by v2.
        self.assertEqual(metrics["result_sync"]["outcome_counts"], {"R1": 2})
        self.assertEqual(summary["budget"]["enforced_limits"]["hard_team_call_permits"], 40)

    def test_permission_profile_t4_zero_network_preflight_preserves_lifecycle(self):
        class _SubmitAtSyncClient(_LifecycleMockClient):
            def complete(self, messages, tools, *, agent_id, tool_choice=None):
                if any("RESULT_SYNC (result_sync_v1)" in str(message.get("content")) for message in messages):
                    return self._call(
                        "submit_findings",
                        {"schema_version": "repository-v1", "findings": []},
                        f"submit-{agent_id}",
                    )
                return super().complete(messages, tools, agent_id=agent_id, tool_choice=tool_choice)

        with tempfile.TemporaryDirectory() as tmp:
            summary = run_experiment(
                RunConfig(
                    mode="structured_team",
                    agent_count=4,
                    model="mock",
                    model_profile={"requested_model": "mock", "max_output_tokens": 4096},
                    budgets={
                        "hard_team_call_permits": 192,
                        "max_provider_retries": 0,
                        "team_finalization_policy": "team_remaining_permits_v1",
                        "team_finalization_reserve": 32,
                    },
                    max_steps=96,
                    completion_policy="convergent_v2",
                    team_completion_policy="all_agents_terminal_v1",
                    team_finalization_policy="team_remaining_permits_v1",
                    team_finalization_reserve=32,
                    task_board_sequencing_policy="initialization_lease_v1",
                    task_closure_policy="task_closure_gate_v1",
                    result_sync_policy="result_sync_v1",
                    prompt_profile="repository_v1_t4_post_sync_verification_permission_v1",
                    runs_dir=Path(tmp),
                    case_id="flowise_3_1_3_repository_v1",
                    evaluate=False,
                ),
                _SubmitAtSyncClient(),
            )
            run_dir = Path(summary["run_dir"])
            metrics = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
            transcripts = list(TranscriptLog(run_dir / "logs" / "transcripts", run_dir.name, self.events).read_all())
        self.assertEqual(summary["run_validity"]["status"], "valid")
        self.assertEqual(summary["reconciliation"]["status"], "valid")
        self.assertEqual(summary["team_completion"]["classification"], "clean_complete", summary["agent_results"])
        self.assertEqual([metrics["structured_team"][key] for key in ("tasks_created", "tasks_claimed", "tasks_completed")], [4, 4, 4])
        self.assertTrue(metrics["result_sync"]["exactly_once"])
        self.assertEqual(len(metrics["result_sync"]["per_agent"]), 4)
        self.assertEqual(summary["budget"]["enforced_limits"]["hard_team_call_permits"], 192)
        self.assertEqual(summary["budget"]["team_finalization"]["reserve"], 32)
        self.assertTrue(any(
            record["kind"] == "model_request"
            and "one bounded, target-aligned verification action" in str(record["content"]["messages"])
            for record in transcripts
        ))


if __name__ == "__main__":
    unittest.main()
