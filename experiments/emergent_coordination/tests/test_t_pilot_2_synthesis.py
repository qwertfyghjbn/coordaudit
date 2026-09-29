"""Zero-network T-Pilot 2 synthesis contract and budget matrix."""

from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from experiments.emergent_coordination.harness.budget import BudgetExhausted, BudgetTracker, TokenUsage
from experiments.emergent_coordination.harness.block_runner import BlockRunner
from experiments.emergent_coordination.harness.contract import ContractViolation, load_block_config
from experiments.emergent_coordination.harness.events import EventLog, TranscriptLog, reconcile_run
from experiments.emergent_coordination.harness.llm.client import LLMResponse, MockLLMClient
from experiments.emergent_coordination.harness.prompts import T_PILOT_1_PROFILE
from experiments.emergent_coordination.harness.prompts import T_PILOT_2_SYNTHESIS_INSTRUCTIONS
from experiments.emergent_coordination.harness.runner import RunConfig, classify_infrastructure_validity, run_experiment
from experiments.emergent_coordination.harness.synthesis_findings import validate_synthesis_payload
from experiments.emergent_coordination.harness.synthesis_runner import TeamSynthesisRunner
from experiments.emergent_coordination.harness.tools.specs import synthesis_tools
from experiments.emergent_coordination.harness.workspace import prepare_run_workspace


def _finding(ref: str) -> dict:
    anchor = {"file": "app.py", "function": "handler", "anchor": "dangerous(value)"}
    return {
        "title": "Untrusted value reaches dangerous handler", "category": "other", "severity": "high",
        "source": dict(anchor), "sink": dict(anchor),
        "guard": {"kind": "missing", "anchor": dict(anchor)},
        "affected_object": "document", "trust_boundary": "external to document",
        "reasoning_summary": "Untrusted value reaches the operation without a guard.",
        "evidence_refs": [ref],
        "verification": {"status": "not_attempted", "evidence_strength": "static", "recipe_ref": None},
        "variant_coverage": [], "confidence": 0.8,
    }


def _payload(raw_refs: list[str], action: str = "retain") -> dict:
    findings = []
    decisions = []
    for index, ref in enumerate(raw_refs):
        raw_id = f"raw_{index:02d}"
        final_id = f"fin_{index:02d}"
        findings.append({**_finding(ref), "final_id": final_id, "derived_from": [raw_id]})
        decisions.append({
            "raw_id": raw_id, "action": action, "target_final_id": final_id,
            "merged_with": None, "evidence_refs": [ref], "rationale": "The raw evidence supports this claim.",
        })
    return {"schema_version": "repository-v1-synthesis-v1", "findings": findings, "raw_decisions": decisions}


def _response(tool: str, args: dict, index: int) -> LLMResponse:
    return LLMResponse(
        content=None,
        tool_calls=[{"id": f"call_{index}", "name": tool, "arguments": json.dumps(args)}],
        usage=TokenUsage(input_tokens=12, output_tokens=20, model="mock"),
        raw={"mock": True},
    )


class _FailureOnce(MockLLMClient):
    def complete(self, messages, tools, *, agent_id, tool_choice=None):
        if not self.calls.get(agent_id):
            self.calls[agent_id] = 1
            raise TimeoutError("injected provider timeout")
        self.calls[agent_id] = 1
        return self.scripts[agent_id][0]


class _AlwaysFailure(MockLLMClient):
    def complete(self, messages, tools, *, agent_id, tool_choice=None):
        self.calls[agent_id] = self.calls.get(agent_id, 0) + 1
        raise TimeoutError("injected provider timeout")


class SynthesisFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        target = root / "source"
        target.mkdir()
        (target / "app.py").write_text("def handler(value):\n    dangerous(value)\n", encoding="utf-8")
        self.layout = prepare_run_workspace(root / "run", target, 1)
        self.events = EventLog(self.layout.logs / "events.jsonl", run_id="t-pilot-2-test")
        self.transcripts = TranscriptLog(self.layout.logs / "transcripts", "t-pilot-2-test", self.events)
        read = self.events.emit("file_read", agent_id="agent_001", payload={"path": "target/app.py"})
        self.ref = read["event_id"]
        self.finding = _finding(self.ref)
        self.events.emit("finding_submitted", agent_id="agent_001", payload={"finding_count": 1})

    def tearDown(self):
        self.tmp.cleanup()

    def run_synthesis(self, sequence: list[LLMResponse], *, reserve: int, read_cap: int):
        client = MockLLMClient(scripts={"team_finalizer": sequence})
        budget = BudgetTracker(hard_team_call_permits=192, synthesis_reserve_permits=reserve,
                               synthesis_window_seconds=60, wall_clock_timeout=1200)
        runner = TeamSynthesisRunner(
            layout=self.layout, event_log=self.events, transcript_log=self.transcripts,
            budget=budget, llm=client,
            agent_results=[{"agent_id": "agent_001", "stop_reason": "submitted"}],
            submissions={"agent_001": {"schema_version": "repository-v1", "findings": [self.finding]}},
            agent_ids=["agent_001"], read_file_cap=read_cap,
        )
        outcome = runner.run()
        return outcome, budget, self.events.read_all()

    def test_budget_matrix_selects_three_permits_and_one_read(self):
        good = _payload([self.ref])
        bad = copy.deepcopy(good)
        bad["findings"][0]["derived_from"] = []
        variants = {
            "direct": [("submit_team_findings", good)],
            "invalid_then_submit": [("submit_team_findings", bad), ("submit_team_findings", good)],
            "read_then_submit": [("read_file", {"path": "target/app.py"}), ("submit_team_findings", good)],
            "read_invalid_submit": [("read_file", {"path": "target/app.py"}), ("submit_team_findings", bad), ("submit_team_findings", good)],
            "two_reads_submit": [("read_file", {"path": "target/app.py"}), ("read_file", {"path": "target/app.py"}), ("submit_team_findings", good)],
        }
        for reserve in (2, 3, 4):
            for read_cap in (1, 2):
                for name, steps in variants.items():
                    with self.subTest(reserve=reserve, read_cap=read_cap, variant=name):
                        with SynthesisFixture._fresh_fixture() as fixture:
                            adapted = fixture._adapt_steps(steps)
                            outcome, budget, events = fixture.run_synthesis(
                                [_response(tool, args, index) for index, (tool, args) in enumerate(adapted)],
                                reserve=reserve, read_cap=read_cap,
                            )
                            needed_calls = len(steps)
                            supported = needed_calls <= reserve
                            self.assertEqual(outcome.status == "completed", supported)
                            self.assertEqual(outcome.provider_calls, min(needed_calls, reserve))
                            self.assertEqual(budget.synthesis_calls_used, min(needed_calls, reserve))
                            self.assertEqual(reconcile_run(fixture.events, fixture.transcripts, budget.snapshot())["status"], "valid")
                            if name == "two_reads_submit" and read_cap == 1:
                                self.assertEqual(outcome.read_file_calls, 1)
                                self.assertTrue(any(e["event_type"] == "prohibited_tool_attempt" and e["payload"].get("rejected_by") == "synthesis_read_cap" for e in events))
                            if name == "read_invalid_submit" and supported:
                                self.assertTrue(any(e["event_type"] == "team_findings_submission_rejected" for e in events))
                                requests = [json.loads(line)["content"] for line in (fixture.layout.logs / "transcripts/team_finalizer.jsonl").read_text().splitlines() if json.loads(line)["kind"] == "model_request"]
                                self.assertTrue(any(m.get("role") == "tool" and "dangerous(value)" in m.get("content", "") for m in requests[1]["messages"]))

    @staticmethod
    def _fresh_fixture():
        class Context:
            def __enter__(self):
                self.fixture = SynthesisFixture()
                self.fixture.setUp()
                return self.fixture
            def __exit__(self, *args):
                self.fixture.tearDown()
        return Context()

    def _adapt_steps(self, steps):
        adapted = []
        for tool, args in steps:
            copy_args = copy.deepcopy(args)
            if tool == "submit_team_findings":
                copy_args = _payload([self.ref]) if copy_args["findings"][0]["derived_from"] else _payload([self.ref])
                if not args["findings"][0]["derived_from"]:
                    copy_args["findings"][0]["derived_from"] = []
            adapted.append((tool, copy_args))
        return adapted

    def test_explicit_decision_and_provenance_rejections(self):
        good = _payload([self.ref])
        cases = []
        for change in ("missing", "duplicate", "unknown", "empty_source", "silent_drop", "false_merge"):
            value = copy.deepcopy(good)
            if change == "missing": value["raw_decisions"] = []
            if change == "duplicate": value["raw_decisions"].append(copy.deepcopy(value["raw_decisions"][0]))
            if change == "unknown": value["raw_decisions"][0]["raw_id"] = "raw_99"
            if change == "empty_source": value["findings"][0]["derived_from"] = []
            if change == "silent_drop": value["findings"] = []
            if change == "false_merge":
                value["raw_decisions"][0]["action"] = "merge"
                value["raw_decisions"][0]["merged_with"] = ["raw_99"]
            cases.append((change, value))
        for name, value in cases:
            with self.subTest(name=name):
                self.assertFalse(validate_synthesis_payload(value, {"raw_00"}, {"raw_00": self.finding}).accepted)
        self.assertTrue(validate_synthesis_payload(good, {"raw_00"}, {"raw_00": self.finding}).accepted)

    def test_single_provider_failure_consumes_permit_and_outer_loop_recovers(self):
        client = _FailureOnce(scripts={"team_finalizer": [_response("submit_team_findings", _payload([self.ref]), 1)]})
        budget = BudgetTracker(hard_team_call_permits=192, synthesis_reserve_permits=3,
                               synthesis_window_seconds=60, wall_clock_timeout=1200)
        runner = TeamSynthesisRunner(
            layout=self.layout, event_log=self.events, transcript_log=self.transcripts,
            budget=budget, llm=client,
            agent_results=[{"agent_id": "agent_001", "stop_reason": "submitted"}],
            submissions={"agent_001": {"schema_version": "repository-v1", "findings": [self.finding]}},
            agent_ids=["agent_001"], read_file_cap=1,
        )
        outcome = runner.run()
        self.assertEqual(outcome.status, "completed")
        self.assertEqual(outcome.provider_failures, 1)
        self.assertEqual(outcome.provider_calls, 2)
        self.assertEqual([e["outcome"] for e in budget.permit_ledger], ["timeout", "succeeded"])
        self.assertEqual(reconcile_run(self.events, self.transcripts, budget.snapshot())["status"], "valid")

    def test_provider_failure_degrades_without_hidden_retry_and_adr_counts_both(self):
        budget = BudgetTracker(hard_team_call_permits=192, synthesis_reserve_permits=2,
                               synthesis_window_seconds=60, wall_clock_timeout=1200)
        runner = TeamSynthesisRunner(
            layout=self.layout, event_log=self.events, transcript_log=self.transcripts,
            budget=budget, llm=_AlwaysFailure(),
            agent_results=[{"agent_id": "agent_001", "stop_reason": "submitted"}],
            submissions={"agent_001": {"schema_version": "repository-v1", "findings": [self.finding]}},
            agent_ids=["agent_001"], read_file_cap=1,
        )
        outcome = runner.run()
        self.assertEqual((outcome.status, outcome.reason), ("degraded", "provider_failure"))
        self.assertEqual(outcome.provider_calls, 2)
        self.assertEqual([entry["outcome"] for entry in budget.permit_ledger], ["timeout", "timeout"])
        self.assertEqual(classify_infrastructure_validity(budget.snapshot(), runner.agent_results)["status"], "infrastructure_invalid")
        self.assertEqual(reconcile_run(self.events, self.transcripts, budget.snapshot())["status"], "valid")

    def test_wall_clock_and_static_reserve_boundaries(self):
        budget = BudgetTracker(hard_team_call_permits=4, synthesis_reserve_permits=2,
                               synthesis_window_seconds=1, wall_clock_timeout=2)
        for _ in range(2):
            budget.acquire_call_permit("agent_001")
        with self.assertRaises(BudgetExhausted) as context:
            budget.acquire_call_permit("agent_001")
        self.assertEqual(context.exception.reason, "team_synthesis_reserved")
        budget._started_at -= 2
        with self.assertRaises(BudgetExhausted):
            budget.check_search_wall_clock()
        budget.open_synthesis_phase()
        budget._synthesis_opened_at -= 2
        with self.assertRaises(BudgetExhausted):
            budget.check_synthesis_window()


class _IntegrationClient(MockLLMClient):
    def complete(self, messages, tools, *, agent_id, tool_choice=None):
        count = self.calls.get(agent_id, 0)
        self.calls[agent_id] = count + 1
        if agent_id == "team_finalizer":
            snapshot = json.loads(messages[1]["content"].split(":\n", 1)[1])
            candidate = snapshot["raw_candidates"][0]
            ref = candidate["finding"]["evidence_refs"][0]
            payload = _payload([ref])
            payload["findings"][0] = {**candidate["finding"], "final_id": "fin_00", "derived_from": ["raw_00"]}
            return _response("submit_team_findings", payload, count)
        if agent_id == "agent_001" and count == 0:
            return _response("read_file", {"path": "target/package.json"}, count)
        if agent_id == "agent_001":
            refs = [json.loads(message["content"])["evidence_ref"] for message in messages if message.get("role") == "tool" and "evidence_ref" in message.get("content", "")]
            finding = _finding(refs[-1])
            anchor = {"file": "package.json", "function": "package", "anchor": "flowise"}
            finding["source"] = dict(anchor)
            finding["sink"] = dict(anchor)
            finding["guard"]["anchor"] = dict(anchor)
            return _response("submit_findings", {"schema_version": "repository-v1", "findings": [finding]}, count)
        return _response("submit_findings", {"schema_version": "repository-v1", "findings": []}, count)


class SynthesisIntegrationTest(unittest.TestCase):
    def test_finalizer_prompt_packet_is_exact_and_has_no_historical_case_hints(self):
        packet = json.loads((Path(__file__).parents[3] / "docs/plans/t_pilot_2_freeze/finalizer_prompt_packet_v1.json").read_text())
        self.assertEqual(packet["system_message"], T_PILOT_2_SYNTHESIS_INSTRUCTIONS)
        self.assertEqual(packet["tool_schema"], synthesis_tools())
        self.assertEqual(packet["hashes"]["system_message_sha256"], hashlib.sha256(T_PILOT_2_SYNTHESIS_INSTRUCTIONS.encode()).hexdigest())
        visible = json.dumps({"system_message": packet["system_message"], "tool_schema": packet["tool_schema"]}, ensure_ascii=False).lower()
        for marker in ("#0/#5", "ground_truth", "matched_gt", "pilot 1", "avoid-duplicate", "inspect-others", "result_sync", "post_sync"):
            self.assertNotIn(marker, visible)

    def test_registered_contract_freezes_search_hashes_and_rejects_drift(self):
        root = Path(__file__).parents[1]
        config_path = root / "manifests/t_pilot_2_final_synthesis_v1.json"
        case_path = root / "cases/flowise_3_1_3_repository_v1.json"
        before = case_path.read_bytes() if case_path.exists() else None
        config = load_block_config(config_path)
        with tempfile.TemporaryDirectory() as tmp:
            manifest = json.loads(BlockRunner(config, Path(tmp)).freeze("t-pilot-2-contract-test").manifest_path.read_text())
        previous = json.loads((Path(__file__).parents[3] / "docs/plans/t_pilot_1_freeze/t_pilot_1_shared_objective_v2/block_manifest.json").read_text())
        self.assertEqual(manifest["hashes"]["conditions"]["T4"], previous["hashes"]["conditions"]["T4"])
        self.assertEqual(manifest["digests"]["target_tree"], previous["digests"]["target_tree"])
        if before is not None:
            self.assertEqual(case_path.read_bytes(), before)
        wrong = json.loads(config_path.read_text())
        wrong["budget"]["synthesis_reserve_permits"] = 2
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "wrong.json"
            p.write_text(json.dumps(wrong))
            with self.assertRaises(ContractViolation):
                load_block_config(p)

    def test_full_t4_mock_preserves_search_packet_and_evaluates_both_sets(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = _IntegrationClient()
            client.max_tokens = 4096
            summary = run_experiment(
                RunConfig(
                    mode="structured_team", agent_count=4, model="mock",
                    model_profile={"requested_model": "mock", "provider": "mock", "thinking_mode": "disabled", "temperature": 0, "max_output_tokens": 4096},
                    seed="t-pilot-2-zero-network-integration", run_id="mock-t-pilot-2", runs_dir=Path(tmp),
                    budgets={"hard_team_call_permits": 192, "wall_clock_timeout": 1200},
                    max_steps=96, max_provider_retries=1,
                    completion_policy="convergent_v2", team_completion_policy="all_agents_terminal_v1",
                    team_finalization_policy="team_remaining_permits_v1", team_finalization_reserve=32,
                    task_board_sequencing_policy="initialization_lease_v3", task_closure_policy="task_closure_gate_v1",
                    completion_generation="completion_v2_team", prompt_profile=T_PILOT_1_PROFILE,
                    synthesis_phase_policy="team_synthesis_v1", synthesis_reserve_permits=3,
                    synthesis_window_seconds=60, synthesis_read_file_cap=1,
                    case_id="flowise_3_1_3_repository_v1", evaluate=True,
                ), client,
            )
            self.assertEqual(summary["run_validity"]["status"], "valid")
            self.assertEqual(summary["reconciliation"]["status"], "valid")
            self.assertEqual(summary["team_completion"]["classification"], "clean_complete")
            self.assertEqual(summary["synthesis"]["status"], "completed")
            run_dir = Path(summary["run_dir"])
            self.assertTrue((run_dir / "evaluation_raw.json").exists())
            self.assertTrue((run_dir / "evaluation_final.json").exists())
            self.assertEqual((run_dir / "evaluation.json").read_bytes(), (run_dir / "evaluation_raw.json").read_bytes())
            self.assertEqual(json.loads((run_dir / "synthesis_delta.json").read_text())["raw_decision_counts"]["retain"], 1)
            frozen = json.loads((Path(__file__).parents[3] / "docs/plans/t_pilot_1_freeze/final_prompt_packet_v1.json").read_text())
            for agent_id in (f"agent_{i:03d}" for i in range(1, 5)):
                records = [json.loads(line) for line in (run_dir / "logs/transcripts" / f"{agent_id}.jsonl").read_text().splitlines()]
                request = next(record["content"] for record in records if record["kind"] == "model_request")
                self.assertEqual(request["messages"], frozen["agents"][agent_id]["initial_model_request"]["messages"])
                self.assertEqual(request["tools"], frozen["tool_schema"])
            events = [json.loads(line) for line in (run_dir / "logs/events.jsonl").read_text().splitlines()]
            types = [event["event_type"] for event in events]
            self.assertLess(types.index("team_completion"), types.index("raw_candidate_set_frozen"))
            self.assertLess(types.index("raw_candidate_set_frozen"), types.index("synthesis_started"))
            raw_artifact = json.loads((run_dir / "artifacts/raw_candidate_set.json").read_text())
            snapshot = raw_artifact["model_snapshot"]
            self.assertEqual(set(snapshot), {"schema_version", "raw_candidates", "contributor_terminal_states"})
            self.assertEqual(set(snapshot["raw_candidates"][0]), {"raw_id", "contributor", "finding", "evidence_map", "submission_sequence"})
            self.assertEqual(set(snapshot["raw_candidates"][0]["evidence_map"].values()), {"target/package.json"})
            finalizer_request = next(json.loads(line)["content"] for line in (run_dir / "logs/transcripts/team_finalizer.jsonl").read_text().splitlines() if json.loads(line)["kind"] == "model_request")
            self.assertIn(raw_artifact["model_snapshot_sha256"], finalizer_request["messages"][1]["content"])
            self.assertEqual(finalizer_request["tools"], synthesis_tools())


if __name__ == "__main__":
    unittest.main()
