from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path

from experiments.emergent_coordination.harness.budget import BudgetExhausted, BudgetTracker, TokenUsage
from experiments.emergent_coordination.harness.events import EventLog
from experiments.emergent_coordination.harness.llm.client import LLMResponse, MockLLMClient
from experiments.emergent_coordination.harness.runner import RunConfig, run_experiment
from experiments.emergent_coordination.harness.shared_fs import SharedFilesystem
from experiments.emergent_coordination.harness.task_board import CoordinationError, TaskBoard
from experiments.emergent_coordination.harness.tools.sandbox import AgentSandbox, ToolError
from experiments.emergent_coordination.harness.workspace import prepare_run_workspace
from experiments.emergent_coordination.harness.paths import TARGET_ROOT, GROUND_TRUTH_PATH, PROVENANCE_PATH


def _tool_call(name: str, arguments: dict, call_id: str = "c1") -> dict:
    return {"id": call_id, "name": name, "arguments": json.dumps(arguments)}


def _response(*calls: dict, content: str | None = None, tokens: int = 3) -> LLMResponse:
    return LLMResponse(
        content=content,
        tool_calls=list(calls),
        usage=TokenUsage(input_tokens=tokens, output_tokens=tokens, model="mock"),
        raw={"mock": True},
    )


class IsolationAndSharedTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run_dir = Path(self.tmp.name) / "run"
        self.layout = prepare_run_workspace(
            self.run_dir,
            TARGET_ROOT,
            agent_count=2,
            ground_truth=GROUND_TRUTH_PATH,
            provenance=PROVENANCE_PATH,
        )
        self.log = EventLog(self.layout.logs / "events.jsonl", run_id="test")

    def tearDown(self):
        self.tmp.cleanup()

    def test_parallel_private_state_is_isolated(self):
        a = AgentSandbox("agent_001", self.layout, self.log)
        b = AgentSandbox("agent_002", self.layout, self.log)
        a.write_file("scratch/secret.txt", "only-a")
        with self.assertRaises(ToolError):
            b.read_file("../agent_001/scratch/secret.txt")
        with self.assertRaises(ToolError):
            b.read_file(str(self.layout.agent_scratch("agent_001") / "secret.txt"))
        self.assertTrue((self.layout.agent_scratch("agent_001") / "secret.txt").exists())
        self.assertFalse((self.layout.agent_scratch("agent_002") / "secret.txt").exists())

    def test_evaluator_private_is_blocked(self):
        sandbox = AgentSandbox("agent_001", self.layout, self.log)
        with self.assertRaises(ToolError):
            sandbox.read_file(str(self.layout.evaluator_private / "ground_truth.json"))
        with self.assertRaises(ToolError):
            sandbox.run_shell("cat ../evaluator_private/ground_truth.json")

    def test_blackboard_visibility(self):
        shared = SharedFilesystem(self.layout.shared, self.log, self.layout.artifacts / "snaps")
        a = AgentSandbox("agent_001", self.layout, self.log, shared=shared)
        b = AgentSandbox("agent_002", self.layout, self.log, shared=shared)
        a.shared_create("note.txt", "hello from a")
        self.assertEqual(b.shared_read("note.txt"), "hello from a")
        self.assertIn("note.txt", b.shared_list("."))

    def test_atomic_claim(self):
        board = TaskBoard(self.layout.runtime / "coordination", self.log)
        task = board.create_task("agent_001", "inspect routes")
        winners = []
        errors = []

        def claim(agent_id: str) -> None:
            try:
                board.claim_task(agent_id, task["id"])
                winners.append(agent_id)
            except CoordinationError as exc:
                errors.append(str(exc))

        threads = [
            threading.Thread(target=claim, args=("agent_001",)),
            threading.Thread(target=claim, args=("agent_002",)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(len(winners), 1)
        self.assertEqual(len(errors), 1)
        claimed = board._read_task(task["id"])
        self.assertEqual(claimed["owner"], winners[0])
        self.assertEqual(claimed["status"], "claimed")

    def test_target_copy_does_not_include_ground_truth(self):
        names = {path.name for path in self.layout.agent_target("agent_001").rglob("*")}
        self.assertNotIn("ground_truth.json", names)
        self.assertTrue((self.layout.evaluator_private / "ground_truth.json").exists())


class BudgetTest(unittest.TestCase):
    def test_global_cap_is_shared(self):
        tracker = BudgetTracker(global_input_token_cap=10, max_llm_calls=100)
        tracker.charge("agent_001", TokenUsage(input_tokens=6, output_tokens=1))
        with self.assertRaises(BudgetExhausted) as ctx:
            tracker.charge("agent_002", TokenUsage(input_tokens=6, output_tokens=1))
        self.assertEqual(ctx.exception.reason, "global_input_token_cap")

    def test_max_llm_calls(self):
        tracker = BudgetTracker(max_llm_calls=1)
        tracker.charge("agent_001", TokenUsage(input_tokens=1, output_tokens=1))
        with self.assertRaises(BudgetExhausted):
            tracker.charge("agent_002", TokenUsage(input_tokens=1, output_tokens=1))


class MockedHarnessTest(unittest.TestCase):
    def test_single_agent_lifecycle_and_scoring(self):
        with tempfile.TemporaryDirectory() as tmp:
            llm = MockLLMClient(
                scripts={
                    "agent_001": [
                        _response(_tool_call("list_files", {"path": "target"}, "c1")),
                        _response(
                            _tool_call(
                                "submit_findings",
                                {
                                    "findings": [
                                        {
                                            "title": "unguarded file join",
                                            "category": "path_traversal",
                                            "files": ["app/common/storage.py"],
                                            "functions": ["read_file"],
                                            "sink": "open(",
                                        },
                                        {
                                            "title": "unguarded fetch",
                                            "category": "ssrf",
                                            "files": ["app/common/http_client.py"],
                                            "functions": ["get_url"],
                                            "sink": "requests.get",
                                        },
                                        {
                                            "title": "title concatenated into template",
                                            "category": "ssti",
                                            "files": ["app/common/templates.py"],
                                            "functions": ["render_report_template"],
                                            "sink": "from_string",
                                        },
                                    ]
                                },
                                "c2",
                            )
                        ),
                    ]
                }
            )
            summary = run_experiment(
                RunConfig(
                    mode="single",
                    agent_count=1,
                    model="mock",
                    budgets={"max_llm_calls": 20, "global_input_token_cap": 1000, "global_output_token_cap": 1000},
                    runs_dir=Path(tmp),
                    max_steps=6,
                ),
                llm,
            )
            self.assertEqual(summary["evaluation"]["TP"], 3)
            self.assertEqual(summary["evaluation"]["FN"], 0)
            runtime_names = {path.name for path in (Path(summary["run_dir"]) / "runtime").rglob("*") if path.is_file()}
            self.assertNotIn("ground_truth.json", runtime_names)
            events = (Path(summary["run_dir"]) / "logs" / "events.jsonl").read_text(encoding="utf-8")
            self.assertIn("agent_started", events)
            self.assertIn("finding_submitted", events)
            self.assertIn("agent_finished", events)
            self.assertIn("llm_call", events)

    def test_parallel_no_shared_tools(self):
        with tempfile.TemporaryDirectory() as tmp:
            llm = MockLLMClient(
                scripts={
                    "agent_001": [
                        _response(_tool_call("shared_list", {"path": "."}, "c1")),
                        _response(_tool_call("submit_findings", {"findings": []}, "c2")),
                    ],
                    "agent_002": [
                        _response(_tool_call("submit_findings", {"findings": []}, "c1")),
                    ],
                }
            )
            summary = run_experiment(
                RunConfig(
                    mode="parallel",
                    agent_count=2,
                    model="mock",
                    budgets={"max_llm_calls": 20},
                    runs_dir=Path(tmp),
                    max_steps=4,
                ),
                llm,
            )
            events = [
                json.loads(line)
                for line in (Path(summary["run_dir"]) / "logs" / "events.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            shared_events = [event for event in events if event["event_type"].startswith("shared_")]
            self.assertEqual(shared_events, [])

    def test_blackboard_shared_create_is_logged(self):
        with tempfile.TemporaryDirectory() as tmp:
            llm = MockLLMClient(
                scripts={
                    "agent_001": [
                        _response(_tool_call("shared_create", {"path": "from_001.txt", "content": "hi"}, "c1")),
                        _response(_tool_call("submit_findings", {"findings": []}, "c2")),
                    ],
                    "agent_002": [
                        _response(_tool_call("shared_create", {"path": "from_002.txt", "content": "yo"}, "c1")),
                        _response(_tool_call("submit_findings", {"findings": []}, "c2")),
                    ],
                }
            )
            summary = run_experiment(
                RunConfig(
                    mode="raw_blackboard",
                    agent_count=2,
                    model="mock",
                    budgets={"max_llm_calls": 20},
                    runs_dir=Path(tmp),
                    max_steps=6,
                ),
                llm,
            )
            events = (Path(summary["run_dir"]) / "logs" / "events.jsonl").read_text(encoding="utf-8")
            self.assertIn("shared_create", events)
            shared = Path(summary["run_dir"]) / "runtime" / "shared"
            self.assertTrue((shared / "from_001.txt").exists())
            self.assertTrue((shared / "from_002.txt").exists())

    def test_structured_team_claim_and_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            llm = MockLLMClient(
                scripts={
                    "agent_001": [
                        _response(_tool_call("create_task", {"description": "review files.py"}, "c1")),
                        _response(_tool_call("submit_findings", {"findings": []}, "c2")),
                    ],
                    "agent_002": [
                        _response(_tool_call("list_tasks", {}, "c1")),
                        _response(_tool_call("submit_findings", {"findings": []}, "c2")),
                    ],
                }
            )
            summary = run_experiment(
                RunConfig(
                    mode="structured_team",
                    agent_count=2,
                    model="mock",
                    budgets={"max_llm_calls": 20},
                    runs_dir=Path(tmp),
                    max_steps=6,
                ),
                llm,
            )
            events = (Path(summary["run_dir"]) / "logs" / "events.jsonl").read_text(encoding="utf-8")
            self.assertIn("task_created", events)

    def test_budget_stop_is_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            llm = MockLLMClient(
                default=[
                    _response(_tool_call("list_files", {"path": "target"}, "c1"), tokens=20),
                    _response(_tool_call("list_files", {"path": "target"}, "c2"), tokens=20),
                ]
            )
            summary = run_experiment(
                RunConfig(
                    mode="single",
                    agent_count=1,
                    model="mock",
                    budgets={"global_input_token_cap": 25, "max_llm_calls": 10},
                    runs_dir=Path(tmp),
                    max_steps=6,
                ),
                llm,
            )
            self.assertEqual(summary["agent_results"][0]["stop_reason"], "budget_exhausted")
            events = (Path(summary["run_dir"]) / "logs" / "events.jsonl").read_text(encoding="utf-8")
            self.assertIn("budget_exhausted", events)


if __name__ == "__main__":
    unittest.main()
