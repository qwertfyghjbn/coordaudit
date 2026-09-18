from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from experiments.emergent_coordination.analysis.replay_evidence_lineage import replay_evidence_lineage


class EvidenceLineageReplayTest(unittest.TestCase):
    def test_distinguishes_namespace_prefix_mismatch_from_validator_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            transcript_dir = run_dir / "logs" / "transcripts"
            transcript_dir.mkdir(parents=True)
            records = [
                {
                    "sequence": 1,
                    "agent_id": "agent_001",
                    "kind": "model_response",
                    "content": {"step": 1, "tool_calls": [
                        {"id": "read-1", "name": "read_file", "arguments": '{"path":"target/app/source.py"}'}
                    ]},
                },
                {
                    "sequence": 2,
                    "agent_id": "agent_001",
                    "kind": "tool_result",
                    "content": {"tool_call_id": "read-1", "name": "read_file", "content": json.dumps({
                        "evidence_ref": "evt_00000001", "path": "target/app/source.py", "content": "x"
                    })},
                },
                {
                    "sequence": 3,
                    "agent_id": "agent_001",
                    "kind": "model_response",
                    "content": {"step": 2, "tool_calls": [
                        {"id": "submit-1", "name": "submit_findings", "arguments": json.dumps({"findings": [{
                            "category": "ssrf", "source": {"file": "target/app/source.py"},
                            "sink": {"file": "target/app/sink.py"}, "evidence_refs": ["evt_00000001"]
                        }]})}
                    ]},
                },
                {
                    "sequence": 4,
                    "agent_id": "agent_001",
                    "kind": "tool_result",
                    "content": {"tool_call_id": "submit-1", "name": "submit_findings", "content": json.dumps({
                        "ok": False, "errors": [{
                            "path": "findings[0].evidence_refs",
                            "message": "must include a file_read of the reported source or sink file",
                        }]
                    })},
                },
                {
                    "sequence": 5,
                    "agent_id": "agent_001",
                    "kind": "model_response",
                    "content": {"step": 3, "tool_calls": [
                        {"id": "submit-2", "name": "submit_findings", "arguments": json.dumps({"findings": [{
                            "category": "ssrf", "source": {"file": "app/source.py"},
                            "sink": {"file": "app/sink.py"}, "evidence_refs": ["evt_00000001"]
                        }]})}
                    ]},
                },
                {
                    "sequence": 6,
                    "agent_id": "agent_001",
                    "kind": "tool_result",
                    "content": {"tool_call_id": "submit-2", "name": "submit_findings", "content": '{"ok":true,"count":1}'},
                },
            ]
            (transcript_dir / "agent_001.jsonl").write_text(
                "\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8"
            )

            replay = replay_evidence_lineage(run_dir, write=False)

        self.assertEqual(replay["summary"]["submission_count"], 2)
        self.assertEqual(replay["summary"]["classifications"]["historical_namespace_prefix_rejection"], 1)
        self.assertEqual(replay["summary"]["classifications"]["validator_match"], 1)
        self.assertFalse(replay["hidden_evaluator_used"])
        self.assertEqual(replay["provider_calls"], 0)


if __name__ == "__main__":
    unittest.main()
