from __future__ import annotations

import json
import os
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from experiments.emergent_coordination.harness.budget import BudgetExhausted, BudgetTracker, TokenUsage
from experiments.emergent_coordination.harness.events import EventLog
from experiments.emergent_coordination.harness.llm.client import LLMResponse, MockLLMClient
from experiments.emergent_coordination.harness.runner import RunConfig, run_experiment
from experiments.emergent_coordination.harness.shared_fs import SharedFilesystem
from experiments.emergent_coordination.harness.task_board import CoordinationError, TaskBoard
from experiments.emergent_coordination.harness.tools.sandbox import (
    AgentSandbox,
    SandboxUnavailable,
    ToolError,
    assert_os_sandbox_ready,
)
from experiments.emergent_coordination.harness.workspace import prepare_run_workspace
from experiments.emergent_coordination.harness.paths import MANIFEST_PATH, TARGET_ROOT, GROUND_TRUTH_PATH, PROVENANCE_PATH


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

    def test_shell_uses_bwrap_without_mounting_private_or_evaluator_state(self):
        sandbox = AgentSandbox("agent_001", self.layout, self.log)
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr="")
        with mock.patch("experiments.emergent_coordination.harness.tools.sandbox.shutil.which", return_value="/usr/bin/bwrap"), mock.patch(
            "experiments.emergent_coordination.harness.tools.sandbox.subprocess.run", return_value=completed
        ) as run:
            result = sandbox.run_shell("printf ok")

        invocation = run.call_args.args[0]
        self.assertEqual(result["stdout"], "ok")
        self.assertIn("--unshare-net", invocation)
        self.assertIn("--unshare-pid", invocation)
        self.assertIn("--unshare-ipc", invocation)
        self.assertIn("--unshare-uts", invocation)
        self.assertIn("--clearenv", invocation)
        self.assertIn("--ro-bind", invocation)
        self.assertIn(str(self.layout.agent_target("agent_001").resolve()), invocation)
        self.assertIn(str(self.layout.agent_scratch("agent_001").resolve()), invocation)
        mount_sources = [
            invocation[index + 1]
            for index, argument in enumerate(invocation[:-2])
            if argument in {"--bind", "--ro-bind"}
        ]
        self.assertNotIn(str(self.layout.agent_private("agent_001").resolve()), mount_sources)
        self.assertNotIn(str(self.layout.evaluator_private.resolve()), mount_sources)

    def test_sandbox_self_check_fails_closed(self):
        completed = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="/home/secret")
        with mock.patch("experiments.emergent_coordination.harness.tools.sandbox.shutil.which", return_value="/usr/bin/bwrap"), mock.patch(
            "experiments.emergent_coordination.harness.tools.sandbox.subprocess.run", return_value=completed
        ):
            with self.assertRaises(SandboxUnavailable) as ctx:
                assert_os_sandbox_ready()
        self.assertNotIn("/home/secret", str(ctx.exception))

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
        self.assertIn("task_claim_conflict", [event["event_type"] for event in self.log.read_all()])

    def test_initialization_lease_orders_visibility_before_first_claim(self):
        board = TaskBoard(
            self.layout.runtime / "coordination",
            self.log,
            initialization_policy="initialization_lease_v1",
            agent_ids=["agent_001", "agent_002", "agent_003", "agent_004"],
        )
        agent_002_result: list[list[dict]] = []
        agent_002_done = threading.Event()

        def observe_agent_002() -> None:
            agent_002_result.append(board.list_tasks("agent_002"))
            agent_002_done.set()

        waiting = threading.Thread(target=observe_agent_002)
        waiting.start()
        self.assertFalse(agent_002_done.wait(0.05))

        self.assertEqual(board.list_tasks("agent_001"), [])
        task = board.create_task("agent_001", "inspect an uncovered subsystem")
        board.claim_task("agent_001", task["id"])

        self.assertTrue(agent_002_done.wait(1.0))
        waiting.join(timeout=1.0)
        self.assertEqual(len(agent_002_result), 1)
        self.assertEqual(agent_002_result[0][0]["status"], "claimed")
        lease_events = [event for event in self.log.read_all() if event["event_type"].startswith("task_initialization_lease_")]
        self.assertEqual(sum(event["event_type"] == "task_initialization_lease_waited" for event in lease_events), 1)
        self.assertEqual(
            [event["agent_id"] for event in lease_events if event["event_type"] == "task_initialization_lease_acquired"],
            ["agent_001", "agent_002"],
        )
        self.assertEqual(
            [event["agent_id"] for event in lease_events if event["event_type"] == "task_initialization_lease_released"],
            ["agent_001"],
        )

    def test_completed_task_evidence_receipt_is_recorded_for_observer(self):
        board = TaskBoard(self.layout.runtime / "coordination", self.log)
        task = board.create_task("agent_001", "inspect routes")
        board.claim_task("agent_001", task["id"])
        board.complete_task("agent_001", task["id"], "route checked", ["evt_00000001"])
        board.list_tasks("agent_002")
        observed = [event for event in self.log.read_all() if event["event_type"] == "task_result_observed"]
        self.assertEqual(len(observed), 1)
        self.assertEqual(observed[0]["agent_id"], "agent_002")
        self.assertEqual(observed[0]["payload"]["evidence_refs"], ["evt_00000001"])

    def test_target_copy_does_not_include_ground_truth(self):
        names = {path.name for path in self.layout.agent_target("agent_001").rglob("*")}
        self.assertNotIn("ground_truth.json", names)
        self.assertTrue((self.layout.evaluator_private / "ground_truth.json").exists())

    def test_list_files_accepts_a_relative_run_directory(self):
        """CLI --runs-dir may be relative, but tool paths must remain coherent."""
        with tempfile.TemporaryDirectory() as tmp:
            absolute_run_dir = Path(tmp) / "run"
            relative_run_dir = Path(os.path.relpath(absolute_run_dir, Path.cwd()))
            layout = prepare_run_workspace(relative_run_dir, TARGET_ROOT, agent_count=1)
            log = EventLog(layout.logs / "events.jsonl", run_id="relative-run-dir")
            sandbox = AgentSandbox("agent_001", layout, log)

            entries = sandbox.list_files("target")

        self.assertTrue(layout.run_dir.is_absolute())
        self.assertIn("target/README.md", entries)


class BudgetTest(unittest.TestCase):
    def test_snapshot_separates_enforced_limits_soft_stops_and_observed_usage(self):
        tracker = BudgetTracker(hard_team_call_permits=2, token_stop_threshold=10, wall_clock_timeout=30)
        permit = tracker.acquire_call_permit("agent_001")
        tracker.settle_call_permit(
            permit,
            outcome="succeeded",
            usage=TokenUsage(input_tokens=3, cached_input_tokens=2, output_tokens=1, reasoning_tokens=1),
        )

        snapshot = tracker.snapshot()

        self.assertEqual(snapshot["schema_version"], 3)
        self.assertEqual(snapshot["enforced_limits"], {"hard_team_call_permits": 2})
        self.assertEqual(snapshot["runtime_limits"], {"wall_clock_timeout_seconds": 30})
        self.assertEqual(snapshot["soft_stops"]["token_stop_threshold"], 10)
        self.assertEqual(snapshot["soft_stops"]["basis"], "provider_reported_input_plus_output")
        self.assertEqual(
            snapshot["observed_usage"],
            {"input_tokens": 3, "cached_input_tokens": 2, "output_tokens": 1, "reasoning_tokens": 1},
        )
        self.assertNotIn("caps", snapshot)

    def test_production_tracker_has_no_legacy_charge_api(self):
        self.assertFalse(hasattr(BudgetTracker(hard_team_call_permits=1), "charge"))

    def test_pre_call_permits_are_atomic_and_failures_are_not_refunded(self):
        tracker = BudgetTracker(hard_team_call_permits=2)
        first = tracker.acquire_call_permit("agent_001")
        tracker.settle_call_permit(first, outcome="timeout")
        retry = tracker.acquire_call_permit("agent_001", retry_of=first.permit_id)
        tracker.settle_call_permit(retry, outcome="provider_error")
        with self.assertRaises(BudgetExhausted) as ctx:
            tracker.acquire_call_permit("agent_002")

        snapshot = tracker.snapshot()
        self.assertEqual(ctx.exception.reason, "hard_team_call_permits")
        self.assertEqual(snapshot["attempted_llm_calls"], 2)
        self.assertEqual([entry["outcome"] for entry in snapshot["permit_ledger"]], ["timeout", "provider_error"])
        self.assertEqual(snapshot["permit_ledger"][1]["retry_of"], first.permit_id)

    def test_concurrent_agents_cannot_overissue_team_permits(self):
        tracker = BudgetTracker(hard_team_call_permits=3)
        permits = []
        denied = []
        lock = threading.Lock()

        def request(agent_id: str) -> None:
            try:
                permit = tracker.acquire_call_permit(agent_id)
                with lock:
                    permits.append(permit)
            except BudgetExhausted:
                with lock:
                    denied.append(agent_id)

        threads = [threading.Thread(target=request, args=(f"agent_{index:03d}",)) for index in range(1, 9)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(len(permits), 3)
        self.assertEqual(len(denied), 5)
        self.assertEqual(tracker.snapshot()["attempted_llm_calls"], 3)

    def test_token_stop_threshold_blocks_later_calls_after_reported_usage(self):
        tracker = BudgetTracker(hard_team_call_permits=3, token_stop_threshold=5)
        permit = tracker.acquire_call_permit("agent_001")
        tracker.settle_call_permit(permit, outcome="succeeded", usage=TokenUsage(input_tokens=3, output_tokens=2))
        with self.assertRaises(BudgetExhausted) as ctx:
            tracker.acquire_call_permit("agent_002")
        self.assertEqual(ctx.exception.reason, "token_stop_threshold")

    def test_token_stop_threshold_waits_for_inflight_call_then_continues_below_threshold(self):
        tracker = BudgetTracker(hard_team_call_permits=3, token_stop_threshold=10)
        first = tracker.acquire_call_permit("agent_001")
        started = threading.Event()
        result: dict[str, object] = {}

        def request() -> None:
            started.set()
            try:
                result["permit"] = tracker.acquire_call_permit("agent_002")
            except BudgetExhausted as exc:
                result["error"] = exc

        thread = threading.Thread(target=request)
        thread.start()
        self.assertTrue(started.wait(timeout=1))
        thread.join(timeout=0.05)
        self.assertTrue(thread.is_alive())

        tracker.settle_call_permit(first, outcome="succeeded", usage=TokenUsage(input_tokens=3, output_tokens=2))
        thread.join(timeout=1)

        self.assertFalse(thread.is_alive())
        self.assertIn("permit", result)
        self.assertNotIn("error", result)
        tracker.settle_call_permit(result["permit"], outcome="succeeded", usage=TokenUsage())

    def test_token_stop_threshold_waiter_stops_after_inflight_call_crosses_threshold(self):
        tracker = BudgetTracker(hard_team_call_permits=3, token_stop_threshold=5)
        first = tracker.acquire_call_permit("agent_001")
        started = threading.Event()
        result: dict[str, object] = {}

        def request() -> None:
            started.set()
            try:
                result["permit"] = tracker.acquire_call_permit("agent_002")
            except BudgetExhausted as exc:
                result["error"] = exc

        thread = threading.Thread(target=request)
        thread.start()
        self.assertTrue(started.wait(timeout=1))
        thread.join(timeout=0.05)
        self.assertTrue(thread.is_alive())

        tracker.settle_call_permit(first, outcome="succeeded", usage=TokenUsage(input_tokens=3, output_tokens=2))
        thread.join(timeout=1)

        self.assertFalse(thread.is_alive())
        self.assertNotIn("permit", result)
        self.assertEqual(result["error"].reason, "token_stop_threshold")
        self.assertEqual(tracker.snapshot()["attempted_llm_calls"], 1)


class BudgetConfigurationTest(unittest.TestCase):
    def test_repository_manifest_omits_legacy_token_caps(self):
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        legacy_keys = {"global_input_token_cap", "global_output_token_cap", "per_agent_token_cap", "max_llm_calls"}

        for budget_name in ("default_budgets", "smoke_budgets"):
            self.assertEqual(legacy_keys & set(manifest[budget_name]), set())

    def test_runner_rejects_legacy_budget_keys_before_creating_a_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp)
            with self.assertRaisesRegex(ValueError, "legacy budget fields"):
                run_experiment(
                    RunConfig(
                        mode="single",
                        agent_count=1,
                        model="mock",
                        budgets={"hard_team_call_permits": 1, "global_input_token_cap": 100},
                        runs_dir=runs_dir,
                        max_steps=1,
                    ),
                    MockLLMClient(),
                )
            self.assertEqual(list(runs_dir.iterdir()), [])


class MockedHarnessTest(unittest.TestCase):
    def test_single_agent_lifecycle_and_scoring(self):
        with tempfile.TemporaryDirectory() as tmp:
            llm = MockLLMClient(
                scripts={
                    "agent_001": [
                        _response(_tool_call("list_files", {"path": "target"}, "c1")),
                        _response(
                            _tool_call("read_file", {"path": "target/app/routes/files.py"}, "c2"),
                            _tool_call("read_file", {"path": "target/app/common/http_client.py"}, "c3"),
                            _tool_call("read_file", {"path": "target/app/common/templates.py"}, "c4"),
                        ),
                        _response(
                            _tool_call(
                                "submit_findings",
                                {
                                    "findings": [
                                        {
                                            "title": "unguarded file join",
                                            "category": "path_traversal",
                                            "severity": "high",
                                            "source": {"file": "app/routes/files.py", "function": "download", "anchor": "filename = request.args.get(\"filename\", \"\")"},
                                            "sink": {"file": "app/common/storage.py", "function": "read_file", "anchor": "with open(file_path, \"rb\") as f:"},
                                            "reasoning_summary": "The route passes filename to the unguarded open sink.",
                                            "evidence_refs": ["evt_00000014"],
                                            "reproduction": {"attempted": False, "successful": False, "artifact_ref": None},
                                            "confidence": 0.9,
                                        },
                                        {
                                            "title": "unguarded fetch",
                                            "category": "ssrf",
                                            "severity": "high",
                                            "source": {"file": "app/routes/integrations.py", "function": "fetch", "anchor": "url = request.args.get(\"url\", \"\")"},
                                            "sink": {"file": "app/common/http_client.py", "function": "get_url", "anchor": "resp = requests.get(url, timeout=5)"},
                                            "reasoning_summary": "The integration route reaches an outbound request sink.",
                                            "evidence_refs": ["evt_00000016"],
                                            "reproduction": {"attempted": False, "successful": False, "artifact_ref": None},
                                            "confidence": 0.9,
                                        },
                                        {
                                            "title": "title concatenated into template",
                                            "category": "ssti",
                                            "severity": "high",
                                            "source": {"file": "app/routes/reports.py", "function": "preview", "anchor": "title = request.args.get(\"title\", \"\")"},
                                            "sink": {"file": "app/common/templates.py", "function": "render_report_template", "anchor": "template = _env.from_string(template_str)"},
                                            "reasoning_summary": "The report title reaches template compilation.",
                                            "evidence_refs": ["evt_00000018"],
                                            "reproduction": {"attempted": False, "successful": False, "artifact_ref": None},
                                            "confidence": 0.9,
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
                    budgets={"hard_team_call_permits": 20},
                    runs_dir=Path(tmp),
                    max_steps=6,
                ),
                llm,
            )
            self.assertEqual(summary["evaluation"]["positive_recall"]["true_positives"], 3)
            self.assertEqual(summary["evaluation"]["positive_recall"]["false_negatives"], 0)
            self.assertNotIn("GT-001", (Path(summary["run_dir"]) / "evaluation.json").read_text(encoding="utf-8"))
            self.assertTrue((Path(summary["run_dir"]) / "evaluator_private" / "verification.json").exists())
            runtime_names = {path.name for path in (Path(summary["run_dir"]) / "runtime").rglob("*") if path.is_file()}
            self.assertNotIn("ground_truth.json", runtime_names)
            events = (Path(summary["run_dir"]) / "logs" / "events.jsonl").read_text(encoding="utf-8")
            self.assertIn("agent_started", events)
            self.assertIn("finding_submitted", events)
            self.assertIn("agent_finished", events)
            self.assertIn("llm_call", events)
            run_manifest = json.loads((Path(summary["run_dir"]) / "run_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(run_manifest["budget_semantics"]["schema_version"], 3)
            self.assertEqual(run_manifest["budget_semantics"]["primary_budget_unit"], "attempted_model_call")
            self.assertEqual(run_manifest["budget_semantics"]["token_usage_role"], "observed_outcome")
            self.assertEqual(run_manifest["max_steps"], 6)
            self.assertEqual(summary["budget"]["enforced_limits"]["hard_team_call_permits"], 20)
            self.assertNotIn("caps", summary["budget"])

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
                    budgets={"hard_team_call_permits": 20},
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

    def test_unparseable_submit_arguments_are_counted(self):
        with tempfile.TemporaryDirectory() as tmp:
            llm = MockLLMClient(
                scripts={
                    "agent_001": [
                        _response({"id": "c1", "name": "submit_findings", "arguments": '{"findings": ['}),
                        _response(_tool_call("submit_findings", {"findings": []}, "c2")),
                    ],
                }
            )
            summary = run_experiment(
                RunConfig(
                    mode="single",
                    agent_count=1,
                    model="mock",
                    budgets={"hard_team_call_permits": 20},
                    runs_dir=Path(tmp),
                    max_steps=4,
                ),
                llm,
            )
            agent = summary["agent_results"][0]
            self.assertEqual(agent["stop_reason"], "submitted")
            self.assertEqual(agent["submission_attempts"], 1)
            self.assertEqual(agent["invalid_submission_attempts"], 0)
            self.assertEqual(agent["invalid_submission_arguments"], 1)
            events = [
                json.loads(line)
                for line in (Path(summary["run_dir"]) / "logs" / "events.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            rejected = [
                event
                for event in events
                if event["event_type"] == "tool_call"
                and (event.get("payload") or {}).get("argument_error", {}).get("tool") == "submit_findings"
            ]
            self.assertEqual(len(rejected), 1)
            self.assertEqual(rejected[0]["payload"]["argument_error"]["reason"], "invalid_json")

    def test_llm_call_records_call_role_and_output_ceiling_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            llm = MockLLMClient(
                scripts={
                    "agent_001": [
                        _response(_tool_call("read_file", {"path": "target/missing.py"}, "c1")),
                        _response(_tool_call("submit_findings", {"findings": []}, "c2")),
                    ],
                }
            )
            summary = run_experiment(
                RunConfig(
                    mode="single",
                    agent_count=1,
                    model="mock",
                    budgets={"hard_team_call_permits": 20},
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
            calls = [event for event in events if event["event_type"] == "llm_call" and event["payload"]["outcome"] == "succeeded"]
            self.assertEqual([event["payload"]["call_role"] for event in calls], ["exploration", "submission"])
            for event in calls:
                for field in ("call_role", "output_tokens", "max_output_tokens", "finish_reason"):
                    self.assertIn(field, event["payload"])
                self.assertEqual(event["payload"]["max_output_tokens"], 1024)
            metrics = json.loads((Path(summary["run_dir"]) / "metrics.json").read_text(encoding="utf-8"))
            ceiling = metrics["output_ceiling"]
            self.assertEqual(ceiling["calls"], 2)
            self.assertEqual(ceiling["ceiling_hits"], 0)
            self.assertEqual(
                ceiling["calls_by_role"],
                {"exploration": 1, "coordination": 0, "submission": 1, "finalization": 0},
            )

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
                    budgets={"hard_team_call_permits": 20},
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

    def test_structured_team_claim(self):
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
                    budgets={"hard_team_call_permits": 20},
                    runs_dir=Path(tmp),
                    max_steps=6,
                ),
                llm,
            )
            events = (Path(summary["run_dir"]) / "logs" / "events.jsonl").read_text(encoding="utf-8")
            self.assertIn("task_created", events)

    def test_structured_team_rejects_unfrozen_message_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            llm = MockLLMClient(
                scripts={
                    "agent_001": [
                        _response(_tool_call("send_message", {"to": "agent_002", "body": "hello"}, "c1")),
                        _response(_tool_call("submit_findings", {"findings": []}, "c2")),
                    ]
                }
            )
            summary = run_experiment(
                RunConfig(
                    mode="structured_team",
                    agent_count=1,
                    model="mock",
                    budgets={"hard_team_call_permits": 20},
                    runs_dir=Path(tmp),
                    max_steps=4,
                ),
                llm,
            )
            events = (Path(summary["run_dir"]) / "logs" / "events.jsonl").read_text(encoding="utf-8")
            self.assertNotIn("message_sent", events)

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
                    budgets={"hard_team_call_permits": 1},
                    runs_dir=Path(tmp),
                    max_steps=6,
                ),
                llm,
            )
            self.assertEqual(summary["agent_results"][0]["stop_reason"], "budget_exhausted")
            events = (Path(summary["run_dir"]) / "logs" / "events.jsonl").read_text(encoding="utf-8")
            self.assertIn("budget_exhausted", events)
            self.assertIn("call_permit_denied", events)

    def test_timeout_is_an_attempted_call_and_consumes_a_permit(self):
        class TimeoutClient:
            def complete(self, messages, tools, *, agent_id):
                raise TimeoutError("provider timeout")

        with tempfile.TemporaryDirectory() as tmp:
            summary = run_experiment(
                RunConfig(
                    mode="single",
                    agent_count=1,
                    model="mock",
                    budgets={"hard_team_call_permits": 1},
                    runs_dir=Path(tmp),
                    max_steps=2,
                ),
                TimeoutClient(),
            )
            self.assertEqual(summary["agent_results"][0]["stop_reason"], "error")
            self.assertEqual(summary["budget"]["attempted_llm_calls"], 1)
            self.assertEqual(summary["budget"]["permit_ledger"][0]["outcome"], "timeout")
            events = (Path(summary["run_dir"]) / "logs" / "events.jsonl").read_text(encoding="utf-8")
            self.assertIn("llm_call_attempted", events)
            self.assertIn('"outcome": "timeout"', events)

    def test_one_recovered_timeout_is_a_warning_with_a_new_permit(self):
        class RecoveringClient:
            def __init__(self):
                self.calls = 0

            def complete(self, messages, tools, *, agent_id):
                self.calls += 1
                if self.calls == 1:
                    raise TimeoutError("provider timeout")
                return _response(content=json.dumps({"findings": []}))

        with tempfile.TemporaryDirectory() as tmp:
            summary = run_experiment(
                RunConfig(
                    mode="single",
                    agent_count=1,
                    model="mock",
                    budgets={"hard_team_call_permits": 2},
                    runs_dir=Path(tmp),
                    max_steps=2,
                    max_provider_retries=1,
                ),
                RecoveringClient(),
            )
            ledger = summary["budget"]["permit_ledger"]
            self.assertEqual(summary["run_validity"]["status"], "valid_with_infrastructure_warning")
            self.assertEqual([entry["outcome"] for entry in ledger], ["timeout", "succeeded"])
            self.assertEqual(ledger[1]["retry_of"], ledger[0]["permit_id"])

    def test_two_provider_failures_invalidate_the_run(self):
        class FailingClient:
            def complete(self, messages, tools, *, agent_id):
                raise ConnectionError("provider unavailable")

        with tempfile.TemporaryDirectory() as tmp:
            summary = run_experiment(
                RunConfig(
                    mode="single",
                    agent_count=1,
                    model="mock",
                    budgets={"hard_team_call_permits": 2},
                    runs_dir=Path(tmp),
                    max_steps=2,
                    max_provider_retries=1,
                ),
                FailingClient(),
            )
            self.assertEqual(summary["run_validity"]["status"], "infrastructure_invalid")
            self.assertEqual(summary["run_validity"]["provider_failure_attempts"], 2)


if __name__ == "__main__":
    unittest.main()
