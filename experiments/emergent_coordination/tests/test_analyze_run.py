from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from experiments.emergent_coordination.analysis.analyze_run import analyze_matched_block, analyze_run
from experiments.emergent_coordination.harness.events import EventLog


class AnalyzeRunTest(unittest.TestCase):
    def test_summarizes_shared_activity_without_emergence_claims(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            log = EventLog(run_dir / "logs" / "events.jsonl", run_id="r1")
            log.emit("agent_started", agent_id="agent_001")
            log.emit("agent_started", agent_id="agent_002")
            log.emit("shared_create", agent_id="agent_001", payload={"path": "notes/hello.txt", "filename": "hello.txt"})
            log.emit("shared_read", agent_id="agent_002", payload={"path": "notes/hello.txt"})
            log.emit("agent_finished", agent_id="agent_001")
            log.emit("agent_finished", agent_id="agent_002")
            (run_dir / "evaluation.json").write_text(
                json.dumps({"TP": 1, "FP": 0, "FN": 2, "precision": 1.0, "recall": 0.33}),
                encoding="utf-8",
            )
            result = analyze_run(run_dir)
            self.assertEqual(result["agents_started"], 2)
            self.assertEqual(result["shared_writes"], 1)
            self.assertEqual(result["cross_agent_reads"], 1)
            self.assertIn("evidence only", " ".join(result["notes"]).lower())
            self.assertNotIn("leader emerged", json.dumps(result))

    def test_writes_observational_duplicate_resource_blackboard_and_task_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            log = EventLog(run_dir / "logs" / "events.jsonl", run_id="r-metrics")
            log.emit("run_started")
            log.emit("agent_started", agent_id="agent_001")
            log.emit("agent_started", agent_id="agent_002")
            first_read = log.emit("file_read", agent_id="agent_001", payload={"path": "target/app/a.py"})
            log.emit("file_read", agent_id="agent_002", payload={"path": "target/app/a.py"})
            log.emit("tool_call", agent_id="agent_001", payload={"tool": "run_shell", "arguments": {"command": "rg token target/app/a.py"}})
            log.emit("tool_call", agent_id="agent_002", payload={"tool": "run_shell", "arguments": {"command": "rg token target/app/a.py"}})
            log.emit("shared_create", agent_id="agent_001", payload={"path": "notes/a.txt", "content_hash": "h1"})
            log.emit("shared_read", agent_id="agent_002", payload={"path": "notes/a.txt", "content_hash": "h1"})
            log.emit("task_created", agent_id="agent_001", payload={"id": "task_a", "description": "inspect app a"})
            log.emit("task_claimed", agent_id="agent_001", payload={"task_id": "task_a"})
            log.emit("task_claim_conflict", agent_id="agent_002", payload={"task_id": "task_a"}, outcome="rejected")
            log.emit("task_completed", agent_id="agent_001", payload={"task_id": "task_a", "evidence_refs": [first_read["event_id"]]})
            log.emit("task_result_observed", agent_id="agent_002", payload={"task_id": "task_a", "evidence_refs": [first_read["event_id"]]})
            log.emit("agent_finished", agent_id="agent_001")
            log.emit("agent_finished", agent_id="agent_002")
            (run_dir / "merged_findings.json").write_text(
                json.dumps({"findings": [{
                    "category": "other", "source": {"file": "app/a.py", "function": "source"},
                    "sink": {"file": "app/a.py", "function": "sink"}, "submitted_by": "agent_002",
                    "evidence_refs": [first_read["event_id"]],
                }]}),
                encoding="utf-8",
            )
            (run_dir / "summary.json").write_text(
                json.dumps({
                    "run_id": "r-metrics", "mode": "structured_team", "agent_count": 2,
                    "run_validity": {"status": "valid"},
                    "budget": {
                        "enforced_limits": {"hard_team_call_permits": 4},
                        "runtime_limits": {"wall_clock_timeout_seconds": 60},
                        "soft_stops": {"token_stop_threshold": None},
                        "observed_usage": {
                            "input_tokens": 6, "cached_input_tokens": 0,
                            "output_tokens": 4, "reasoning_tokens": 0,
                        },
                        "permit_ledger": [
                            {"agent_id": "agent_001", "outcome": "succeeded"},
                            {"agent_id": "agent_002", "outcome": "succeeded"},
                        ],
                        "per_agent": {
                            "agent_001": {"input_tokens": 4, "output_tokens": 2},
                            "agent_002": {"input_tokens": 2, "output_tokens": 2},
                        },
                    },
                }),
                encoding="utf-8",
            )
            result = analyze_run(run_dir)

            self.assertTrue((run_dir / "metrics.json").exists())
            self.assertEqual(result["duplicate_work"]["categories"]["files"]["cross_agent_repeated_observations"], 1)
            self.assertEqual(result["duplicate_work"]["categories"]["searches"]["cross_agent_repeated_observations"], 1)
            self.assertEqual(result["resource_allocation"]["team"]["unused_permits"], 2)
            self.assertEqual(result["blackboard"]["cross_agent_read_count"], 1)
            self.assertTrue(result["structured_team"]["available"])
            self.assertTrue(result["structured_team"]["lifecycle_activity_observed"])
            self.assertEqual(result["structured_team"]["claim_conflicts"]["count"], 1)
            self.assertEqual(result["structured_team"]["task_result_evidence_adoption"]["count"], 1)
            self.assertIn("does not prove", result["blackboard"]["lineage_note"])

    def test_distinguishes_coordination_tool_exposure_from_activity_and_deduplicates_list_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            log = EventLog(run_dir / "logs" / "events.jsonl", run_id="r-list-tasks")
            log.emit("run_started")
            dispatch = log.emit(
                "tool_call",
                agent_id="agent_001",
                payload={"tool": "list_tasks", "arguments": {}},
            )
            # TaskBoard records the observable result as a child event.  It is
            # evidence about the one dispatch above, not a second invocation.
            log.emit(
                "tool_call",
                agent_id="agent_001",
                payload={"tool": "list_tasks", "count": 0},
                parent_event_ids=[dispatch["event_id"]],
            )
            (run_dir / "summary.json").write_text(
                json.dumps({"run_id": "r-list-tasks", "mode": "structured_team", "agent_count": 1}),
                encoding="utf-8",
            )

            result = analyze_run(run_dir, write=False)

            structured = result["structured_team"]
            self.assertEqual(result["schema_version"], 2)
            self.assertTrue(structured["available"])
            self.assertTrue(structured["tool_activity_observed"])
            self.assertFalse(structured["lifecycle_activity_observed"])
            self.assertEqual(structured["model_tool_invocations"]["list_tasks"], 1)
            self.assertEqual(structured["task_list_reads"]["invocation_count"], 1)
            self.assertEqual(structured["task_list_reads"]["observed_result_count"], 1)
            self.assertEqual(structured["task_list_reads"]["empty_result_count"], 1)

            (run_dir / "summary.json").write_text(
                json.dumps({"run_id": "r-blackboard", "mode": "raw_blackboard", "agent_count": 1}),
                encoding="utf-8",
            )
            blackboard = analyze_run(run_dir, write=False)["blackboard"]
            self.assertTrue(blackboard["available"])
            self.assertFalse(blackboard["tool_activity_observed"])

    def test_matched_block_reports_complete_and_incomplete_conditions_without_causal_claims(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            conditions = [
                {"id": "S1", "mode": "single", "agent_count": 1},
                {"id": "P4", "mode": "parallel", "agent_count": 4},
                {"id": "B4", "mode": "raw_blackboard", "agent_count": 4},
                {"id": "T4", "mode": "structured_team", "agent_count": 4},
            ]
            (root / "block_manifest.json").write_text(
                json.dumps({"block_id": "block-test", "manifest_hash": "hash", "contract": {"conditions": conditions}}),
                encoding="utf-8",
            )
            mappings = {}
            for condition in conditions:
                run_dir = root / condition["id"]
                run_dir.mkdir()
                (run_dir / "summary.json").write_text(
                    json.dumps({
                        "run_id": condition["id"], "mode": condition["mode"], "agent_count": condition["agent_count"],
                        "run_validity": {"status": "valid"}, "budget": {"caps": {}, "permit_ledger": [], "per_agent": {}},
                    }),
                    encoding="utf-8",
                )
                mappings[condition["id"]] = run_dir
            comparison = analyze_matched_block(root, mappings)

            self.assertEqual(comparison["status"], "complete")
            self.assertTrue((root / "block_comparison.json").exists())
            self.assertEqual(comparison["comparisons_to_S1"]["status"], "observational")
            self.assertIn("不宣称", " ".join(comparison["contract_verification_limits"]))

            incomplete = analyze_matched_block(root, {"S1": mappings["S1"]}, write=False)
            self.assertEqual(incomplete["status"], "incomplete_or_invalid")
            self.assertEqual(incomplete["conditions"]["P4"]["status"], "missing_or_ambiguous")


if __name__ == "__main__":
    unittest.main()
