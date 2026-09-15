from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from experiments.emergent_coordination.analysis.analyze_run import analyze_run
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


if __name__ == "__main__":
    unittest.main()
