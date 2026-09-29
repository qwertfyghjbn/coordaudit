"""Zero-network T-Pilot 1 checks at the production task-board seam."""

from __future__ import annotations

import tempfile
import unittest
import json
from pathlib import Path

from experiments.emergent_coordination.harness.budget import TokenUsage
from experiments.emergent_coordination.harness.budget import BudgetTracker
from experiments.emergent_coordination.harness.block_runner import BlockRunner
from experiments.emergent_coordination.harness.contract import load_block_config
from experiments.emergent_coordination.harness.events import EventLog, TranscriptLog
from experiments.emergent_coordination.harness.agent_loop import AgentRunner
from experiments.emergent_coordination.harness.completion import team_finalization_message
from experiments.emergent_coordination.harness.llm.client import LLMResponse, MockLLMClient
from experiments.emergent_coordination.harness.paths import TARGET_ROOT
from experiments.emergent_coordination.harness.prompts import T_PILOT_1_PROFILE, system_prompt, user_prompt
from experiments.emergent_coordination.harness.runner import RunConfig, run_experiment
from experiments.emergent_coordination.harness.task_board import TaskBoard
from experiments.emergent_coordination.harness.tools.specs import tools_for_mode
from experiments.emergent_coordination.harness.tools.sandbox import AgentSandbox
from experiments.emergent_coordination.harness.workspace import prepare_run_workspace


def _call(name: str, arguments: dict, call_id: str) -> LLMResponse:
    return LLMResponse(
        content=None,
        tool_calls=[{"id": call_id, "name": name, "arguments": json.dumps(arguments)}],
        usage=TokenUsage(input_tokens=1, output_tokens=1, model="mock"),
        raw={"mock": True},
    )


class OptionalBoardLeaseTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.log = EventLog(root / "events.jsonl", run_id="t-pilot-1-lease-test")
        self.board = TaskBoard(
            root / "board",
            self.log,
            initialization_policy="initialization_lease_v2_optional",
            agent_ids=["agent_001", "agent_002", "agent_003", "agent_004"],
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_no_board_agent_terminates_and_next_agent_can_observe(self):
        self.board.release_initialization_lease("agent_001", reason="agent_terminal")
        self.assertEqual(self.board._initialization_index, 1)
        self.assertEqual(self.board.list_tasks("agent_002"), [])

    def test_out_of_order_terminal_agent_is_skipped_after_predecessors(self):
        self.board.release_initialization_lease("agent_003", reason="agent_terminal")
        self.assertEqual(self.board._initialization_index, 0)
        self.board.release_initialization_lease("agent_001", reason="agent_terminal")
        self.assertEqual(self.board._initialization_index, 1)
        self.board.list_tasks("agent_002")
        self.board.release_initialization_lease("agent_002", reason="agent_terminal")
        self.assertEqual(self.board._initialization_index, 3)
        self.board.list_tasks("agent_004")

    def test_list_only_agent_releases_on_terminal(self):
        self.board.list_tasks("agent_001")
        self.board.release_initialization_lease("agent_001", reason="agent_terminal")
        self.assertEqual(self.board.list_tasks("agent_002"), [])

    def test_claim_releases_lease_and_preserves_board_visibility(self):
        self.board.list_tasks("agent_001")
        task = self.board.create_task("agent_001", "one bounded security question")
        self.board.claim_task("agent_001", task["id"])
        self.assertEqual(self.board.list_tasks("agent_002")[0]["owner"], "agent_001")

    def test_create_claim_complete_lifecycle(self):
        task = self.board.create_task("agent_001", "one bounded security question")
        self.board.claim_task("agent_001", task["id"])
        self.board.complete_task("agent_001", task["id"], "source checked", [])
        self.assertEqual(self.board._read_task(task["id"])["status"], "completed")
        self.assertEqual(self.board.claimed_tasks_for("agent_001"), [])

    def test_release_then_other_agent_claims(self):
        task = self.board.create_task("agent_001", "one bounded security question")
        self.board.claim_task("agent_001", task["id"])
        self.board.release_task("agent_001", task["id"])
        claimed = self.board.claim_task("agent_002", task["id"])
        self.assertEqual(claimed["owner"], "agent_002")

    def test_historical_v1_lease_does_not_gain_optional_skip(self):
        legacy = TaskBoard(
            Path(self.tmp.name) / "legacy_board",
            self.log,
            initialization_policy="initialization_lease_v1",
            agent_ids=["agent_001", "agent_002"],
        )
        legacy.release_initialization_lease("agent_001", reason="agent_terminal")
        self.assertEqual(legacy._initialization_index, 0)


class OptionalBoardRunPreflightTest(unittest.TestCase):
    def test_versioned_contract_freezes_without_changing_case_manifest(self):
        config = load_block_config(Path(__file__).parents[1] / "manifests/t_pilot_1_shared_objective_v1.json")
        config.validate()
        self.assertEqual(config.task_board_sequencing_policy, "initialization_lease_v2_optional")
        self.assertEqual(config.hard_team_call_permits, 192)
        with tempfile.TemporaryDirectory() as tmp:
            frozen = BlockRunner(config, Path(tmp)).freeze("t-pilot-1-contract-smoke")
            self.assertTrue(frozen.manifest_path.exists())

    def test_create_claim_investigate_complete_submit_with_new_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            layout = prepare_run_workspace(Path(tmp) / "run", TARGET_ROOT, 1)
            events = EventLog(layout.logs / "events.jsonl", run_id="t-pilot-1-case-c")
            board = TaskBoard(layout.runtime / "coordination", events, initialization_policy="initialization_lease_v2_optional", agent_ids=["agent_001"])
            runner = AgentRunner(
                agent_id="agent_001", mode="structured_team", agent_count=1,
                sandbox=AgentSandbox("agent_001", layout, events, board=board),
                llm=MockLLMClient(), event_log=events,
                transcript_log=TranscriptLog(layout.logs / "transcripts", "t-pilot-1-case-c", events),
                budget=BudgetTracker(hard_team_call_permits=12),
                prompt_profile=T_PILOT_1_PROFILE, finding_schema="repository_pilot_v0",
                completion_policy="convergent_v2", task_closure_policy="task_closure_gate_v1", max_steps=8,
            )
            created = json.loads(runner._dispatch("create_task", '{"description":"one bounded question"}', parent_event_id="evt_parent"))
            task_id = created["id"]
            runner._dispatch("claim_task", json.dumps({"task_id": task_id}), parent_event_id="evt_parent")
            read = json.loads(runner._dispatch("read_file", '{"path":"target/app/main.py"}', parent_event_id="evt_parent"))
            self.assertTrue(read.get("evidence_ref"))
            closed = json.loads(runner._dispatch("complete_task", json.dumps({"task_id": task_id, "result": "source checked", "evidence_refs": []}), parent_event_id="evt_parent"))
            self.assertEqual(closed["status"], "completed")
            submitted = json.loads(runner._dispatch("submit_findings", '{"findings":[]}', parent_event_id="evt_parent"))
            self.assertTrue(submitted.get("ok"))

    def test_no_board_agent_finishes_and_other_agents_can_use_board(self):
        scripts = {
            "agent_001": [
                _call("read_file", {"path": "target/package.json"}, "a1_read"),
                _call("submit_findings", {"schema_version": "repository-v1", "findings": []}, "a1_submit"),
            ],
            "agent_002": [
                _call("list_tasks", {}, "a2_list"),
                _call("read_file", {"path": "target/package.json"}, "a2_read"),
                _call("submit_findings", {"schema_version": "repository-v1", "findings": []}, "a2_submit"),
            ],
            "agent_003": [_call("submit_findings", {"schema_version": "repository-v1", "findings": []}, "a3_submit")],
            "agent_004": [_call("submit_findings", {"schema_version": "repository-v1", "findings": []}, "a4_submit")],
        }
        client = MockLLMClient(scripts=scripts)
        client.max_tokens = 4096
        with tempfile.TemporaryDirectory() as tmp:
            summary = run_experiment(
                RunConfig(
                    mode="structured_team",
                    agent_count=4,
                    model="mock",
                    model_profile={"requested_model": "mock", "provider": "mock", "thinking_mode": "disabled", "temperature": 0.0, "max_output_tokens": 4096},
                    seed="t-pilot-1-zero-network-a",
                    budgets={"hard_team_call_permits": 192},
                    max_steps=96,
                    max_provider_retries=1,
                    completion_policy="convergent_v2",
                    team_completion_policy="all_agents_terminal_v1",
                    team_finalization_policy="team_remaining_permits_v1",
                    team_finalization_reserve=32,
                    task_board_sequencing_policy="initialization_lease_v2_optional",
                    task_closure_policy="task_closure_gate_v1",
                    completion_generation="completion_v2_team",
                    prompt_profile=T_PILOT_1_PROFILE,
                    runs_dir=Path(tmp),
                    case_id="flowise_3_1_3_repository_v1",
                    evaluate=False,
                ),
                client,
            )
            self.assertEqual(summary["run_validity"]["status"], "valid")
            self.assertEqual(summary["reconciliation"]["status"], "valid")
            run_dir = Path(summary["run_dir"])
            events = [json.loads(line) for line in (run_dir / "logs/events.jsonl").read_text().splitlines()]
            self.assertTrue(any(item["event_type"] == "task_initialization_turn_skipped" and item["agent_id"] == "agent_001" for item in events))
            self.assertTrue(any(item["event_type"] == "tool_call" and item["agent_id"] == "agent_002" and item["payload"].get("tool") == "list_tasks" for item in events))
            frozen = json.loads((Path(__file__).parents[3] / "docs/plans/t_pilot_1_freeze/final_prompt_packet_v1.json").read_text())
            for index in range(1, 5):
                aid = f"agent_{index:03d}"
                records = [json.loads(line) for line in (run_dir / "logs/transcripts" / f"{aid}.jsonl").read_text().splitlines()]
                request = next(item["content"] for item in records if item["kind"] == "model_request")
                self.assertEqual(request["messages"], frozen["agents"][aid]["initial_model_request"]["messages"])
                self.assertEqual(request["tools"], frozen["tool_schema"])
                self.assertEqual(request["messages"][0]["content"], system_prompt("structured_team", aid, T_PILOT_1_PROFILE, completion_policy="convergent_v2"))
                self.assertEqual(request["messages"][1]["content"], user_prompt("structured_team", aid, 4, T_PILOT_1_PROFILE))
                self.assertEqual(request["tools"], tools_for_mode("structured_team", "repository_v1"))

    def test_finalization_no_open_and_claimed_task_semantics(self):
        for state in ("none", "open", "claimed"):
            with self.subTest(state=state), tempfile.TemporaryDirectory() as tmp:
                layout = prepare_run_workspace(Path(tmp) / "run", TARGET_ROOT, 1)
                events = EventLog(layout.logs / "events.jsonl", run_id=f"t-pilot-1-finalization-{state}")
                board = TaskBoard(
                    layout.runtime / "coordination",
                    events,
                    initialization_policy="initialization_lease_v2_optional",
                    agent_ids=["agent_001"],
                )
                task = None
                if state != "none":
                    task = board.create_task("agent_001", "one bounded question")
                    if state == "claimed":
                        board.claim_task("agent_001", task["id"])
                runner = AgentRunner(
                    agent_id="agent_001",
                    mode="structured_team",
                    agent_count=1,
                    sandbox=AgentSandbox("agent_001", layout, events, board=board),
                    llm=MockLLMClient(),
                    event_log=events,
                    transcript_log=TranscriptLog(layout.logs / "transcripts", f"t-pilot-1-finalization-{state}", events),
                    budget=BudgetTracker(hard_team_call_permits=1, team_finalization_policy="team_remaining_permits_v1", team_finalization_reserve=1),
                    prompt_profile=T_PILOT_1_PROFILE,
                    finding_schema="repository_pilot_v0",
                    completion_policy="convergent_v2",
                    team_finalization_policy="team_remaining_permits_v1",
                    task_closure_policy="task_closure_gate_v1",
                    max_steps=8,
                )
                tool_names = {item["function"]["name"] for item in runner._tools_for_step()}
                self.assertEqual(tool_names, {"read_file", "submit_findings", "complete_task"})
                self.assertEqual(runner._messages[-1]["content"], team_finalization_message("convergent_v2", task_lifecycle_reminder=True))
                submit = json.loads(runner._dispatch("submit_findings", '{"findings":[]}', parent_event_id="evt_parent"))
                if state == "claimed":
                    self.assertEqual(submit["error"]["code"], "task_closure_required")
                    close = json.loads(runner._dispatch("complete_task", json.dumps({"task_id": task["id"], "result": "done", "evidence_refs": []}), parent_event_id="evt_parent"))
                    self.assertEqual(close["status"], "completed")
                    submit = json.loads(runner._dispatch("submit_findings", '{"findings":[]}', parent_event_id="evt_parent"))
                self.assertTrue(submit.get("ok"))

    def test_claimed_task_finalization_message_enters_model_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            layout = prepare_run_workspace(Path(tmp) / "run", TARGET_ROOT, 1)
            events = EventLog(layout.logs / "events.jsonl", run_id="t-pilot-1-finalization-visible")
            board = TaskBoard(layout.runtime / "coordination", events, initialization_policy="initialization_lease_v2_optional", agent_ids=["agent_001"])
            task = board.create_task("agent_001", "one bounded question")
            board.claim_task("agent_001", task["id"])
            client = MockLLMClient(scripts={"agent_001": [
                _call("complete_task", {"task_id": task["id"], "result": "done", "evidence_refs": []}, "close"),
                _call("submit_findings", {"findings": []}, "submit"),
            ]})
            runner = AgentRunner(
                agent_id="agent_001", mode="structured_team", agent_count=1,
                sandbox=AgentSandbox("agent_001", layout, events, board=board),
                llm=client, event_log=events,
                transcript_log=TranscriptLog(layout.logs / "transcripts", "t-pilot-1-finalization-visible", events),
                budget=BudgetTracker(hard_team_call_permits=2, team_finalization_policy="team_remaining_permits_v1", team_finalization_reserve=2),
                prompt_profile=T_PILOT_1_PROFILE, finding_schema="repository_pilot_v0",
                completion_policy="convergent_v2", team_finalization_policy="team_remaining_permits_v1",
                task_closure_policy="task_closure_gate_v1", max_steps=8,
            )
            self.assertEqual(runner.run()["stop_reason"], "submitted")
            records = [json.loads(line) for line in (layout.logs / "transcripts/agent_001.jsonl").read_text().splitlines()]
            requests = [item["content"] for item in records if item["kind"] == "model_request"]
            self.assertEqual(len(requests), 2)
            self.assertEqual(requests[0]["messages"][-1]["content"], team_finalization_message("convergent_v2", task_lifecycle_reminder=True))
            self.assertEqual({item["function"]["name"] for item in requests[0]["tools"]}, {"read_file", "submit_findings", "complete_task"})


if __name__ == "__main__":
    unittest.main()
