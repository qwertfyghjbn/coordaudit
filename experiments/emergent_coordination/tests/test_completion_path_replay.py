from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from experiments.emergent_coordination.analysis.replay_completion_path import replay_completion_path


def _jsonl(records: list[dict]) -> str:
    return "\n".join(json.dumps(record) for record in records) + "\n"


class CompletionPathReplayTest(unittest.TestCase):
    def test_detects_ceiling_truncated_submit_silently_accepted_as_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            transcript_dir = run_dir / "logs" / "transcripts"
            transcript_dir.mkdir(parents=True)
            (run_dir / "run_manifest.json").write_text(
                json.dumps({"model_profile": {"max_output_tokens": 10}}), encoding="utf-8"
            )
            (run_dir / "summary.json").write_text(
                json.dumps({
                    "run_id": "r1", "mode": "single", "agent_count": 1,
                    "agent_results": [{"agent_id": "agent_001", "stop_reason": "submitted"}],
                    "budget": {"permit_ledger": [
                        {"permit_id": "p1", "token_usage": {"output_tokens": 3}},
                        {"permit_id": "p2", "token_usage": {"output_tokens": 10}},
                    ]},
                }),
                encoding="utf-8",
            )
            records = [
                {
                    "sequence": 1, "agent_id": "agent_001", "kind": "model_response",
                    "content": {"step": 1, "permit_id": "p1", "content": "path traversal candidate", "tool_calls": [
                        {"id": "read-1", "name": "read_file", "arguments": '{"path":"target/app.py"}'}
                    ], "model_metadata": {}},
                },
                {
                    "sequence": 2, "agent_id": "agent_001", "kind": "tool_result",
                    "content": {"tool_call_id": "read-1", "name": "read_file", "content": json.dumps(
                        {"evidence_ref": "evt_1", "path": "target/app.py", "content": "source"}
                    )},
                },
                {
                    "sequence": 3, "agent_id": "agent_001", "kind": "model_response",
                    "content": {"step": 2, "permit_id": "p2", "content": "submit", "tool_calls": [
                        {"id": "submit-1", "name": "submit_findings", "arguments": '{"findings":[{"title":"cut'}
                    ], "model_metadata": {}},
                },
                {
                    "sequence": 4, "agent_id": "agent_001", "kind": "tool_result",
                    "content": {"tool_call_id": "submit-1", "name": "submit_findings", "content": '{"ok":true,"count":0}'},
                },
            ]
            (transcript_dir / "agent_001.jsonl").write_text(_jsonl(records), encoding="utf-8")

            result = replay_completion_path(run_dir, write=False)
            agent = result["agents"]["agent_001"]
            self.assertEqual(agent["failure_classification"], "malformed_submit_arguments_accepted_as_empty_payload")
            self.assertEqual(agent["output_ceiling_hit_steps"], [2])
            self.assertEqual(agent["evidence"]["refs"], ["evt_1"])
            self.assertEqual(agent["submissions"][0]["observable_title_field_count"], 1)
            self.assertEqual(result["diagnostic_signals"]["malformed_submit_calls"], 1)
            self.assertFalse(result["hidden_evaluator_used"])

    def test_recovers_lineage_fields_from_historically_redacted_invalid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            transcript_dir = run_dir / "logs" / "transcripts"
            transcript_dir.mkdir(parents=True)
            (run_dir / "run_manifest.json").write_text("{}", encoding="utf-8")
            (run_dir / "summary.json").write_text(
                json.dumps({
                    "agent_results": [{"agent_id": "agent_001", "stop_reason": "completed"}],
                    "budget": {"permit_ledger": []},
                }),
                encoding="utf-8",
            )
            records = [
                {
                    "sequence": 1, "agent_id": "agent_001", "kind": "model_response",
                    "content": {"step": 1, "permit_id": "p1", "content": "", "tool_calls": [
                        {"id": "read-1", "name": "read_file", "arguments": '{"path":"target/storage.py"}'}
                    ], "model_metadata": {}},
                },
                {
                    "sequence": 2, "agent_id": "agent_001", "kind": "tool_result",
                    "content": {
                        "tool_call_id": "read-1", "name": "read_file",
                        "content": '{"evidence_ref":"evt_9","path":"target/storage.py","content":"BASE=\\"<HOST_PATH>"\\nNEXT"}',
                    },
                },
            ]
            (transcript_dir / "agent_001.jsonl").write_text(_jsonl(records), encoding="utf-8")

            result = replay_completion_path(run_dir, write=False)
            evidence = result["agents"]["agent_001"]["evidence"]
            self.assertEqual(evidence["refs"], ["evt_9"])
            self.assertEqual(evidence["invalid_payload_json_count"], 1)
            self.assertFalse(evidence["records"][0]["payload_json_valid"])

    def test_classifies_budget_exhaustion_after_candidate_and_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            transcript_dir = run_dir / "logs" / "transcripts"
            transcript_dir.mkdir(parents=True)
            (run_dir / "run_manifest.json").write_text(
                json.dumps({"model_profile": {"max_output_tokens": 1024}}), encoding="utf-8"
            )
            (run_dir / "summary.json").write_text(
                json.dumps({
                    "run_id": "r2", "mode": "parallel", "agent_count": 1,
                    "agent_results": [{"agent_id": "agent_001", "stop_reason": "budget_exhausted"}],
                    "budget": {"permit_ledger": [{"permit_id": "p1", "token_usage": {"output_tokens": 20}}]},
                }),
                encoding="utf-8",
            )
            records = [
                {
                    "sequence": 1, "agent_id": "agent_001", "kind": "model_response",
                    "content": {"step": 1, "permit_id": "p1", "content": "verify SSRF", "tool_calls": [
                        {"id": "read-1", "name": "read_file", "arguments": '{"path":"target/http.py"}'}
                    ], "model_metadata": {}},
                },
                {
                    "sequence": 2, "agent_id": "agent_001", "kind": "tool_result",
                    "content": {"tool_call_id": "read-1", "name": "read_file", "content": json.dumps(
                        {"evidence_ref": "evt_2", "path": "target/http.py", "content": "requests.get(url)"}
                    )},
                },
            ]
            (transcript_dir / "agent_001.jsonl").write_text(_jsonl(records), encoding="utf-8")

            result = replay_completion_path(run_dir, write=False)
            self.assertEqual(
                result["agents"]["agent_001"]["failure_classification"],
                "candidate_signal_and_evidence_available_but_no_submission_before_budget_exhaustion",
            )


if __name__ == "__main__":
    unittest.main()
