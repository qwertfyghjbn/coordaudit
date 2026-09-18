from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from experiments.emergent_coordination.harness.llm.client import LLMResponse, MockLLMClient
from experiments.emergent_coordination.harness.budget import TokenUsage
from experiments.emergent_coordination.harness.events import sanitize_for_persistence
from experiments.emergent_coordination.harness.runner import RunConfig, run_experiment


def _response(
    *,
    content: str | None = None,
    tool_calls: list[dict[str, str]] | None = None,
    model_metadata: dict[str, object] | None = None,
) -> LLMResponse:
    return LLMResponse(
        content=content,
        tool_calls=tool_calls or [],
        usage=TokenUsage(input_tokens=3, output_tokens=2, model="mock"),
        raw={"mock": True},
        model_metadata=model_metadata or {},
    )


class TranscriptTest(unittest.TestCase):
    def test_host_path_redaction_preserves_embedded_tool_result_json(self):
        raw_tool_result = json.dumps(
            {
                "evidence_ref": "evt_00000001",
                "path": "target/app/common/storage.py",
                "content": 'BASE_DIR = "/home/lqs/private/data"\n',
            }
        )

        persisted = sanitize_for_persistence(raw_tool_result).value

        self.assertNotIn("/home/lqs/private/data", persisted)
        self.assertEqual(json.loads(persisted)["content"], 'BASE_DIR = "<HOST_PATH>"\n')

    def test_persists_provider_finish_reason_in_transcript_and_llm_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary = run_experiment(
                RunConfig(
                    mode="single", agent_count=1, model="mock",
                    budgets={"hard_team_call_permits": 1}, runs_dir=Path(tmp), max_steps=1,
                ),
                MockLLMClient(default=[_response(
                    content=json.dumps({"findings": []}), model_metadata={"finish_reason": "length"}
                )]),
            )
            run_dir = Path(summary["run_dir"])
            events = [json.loads(line) for line in (run_dir / "logs" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
            transcript = [
                json.loads(line)
                for line in (run_dir / "logs" / "transcripts" / "agent_001.jsonl").read_text(encoding="utf-8").splitlines()
            ]

            response_record = next(record for record in transcript if record["kind"] == "model_response")
            llm_event = next(event for event in events if event["event_type"] == "llm_call")
            self.assertEqual(response_record["content"]["model_metadata"]["finish_reason"], "length")
            self.assertEqual(llm_event["payload"]["model_metadata"]["finish_reason"], "length")

    def test_records_replayable_model_context_and_reconciles_permit_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            llm = MockLLMClient(
                scripts={
                    "agent_001": [
                        _response(tool_calls=[{
                            "id": "create-note",
                            "name": "shared_create",
                            "arguments": json.dumps({"path": "note.txt", "content": "hello from agent"}),
                        }]),
                        _response(content=json.dumps({"findings": []})),
                    ]
                }
            )
            summary = run_experiment(
                RunConfig(
                    mode="raw_blackboard", agent_count=1, model="mock",
                    budgets={"hard_team_call_permits": 4}, runs_dir=Path(tmp), max_steps=4,
                ),
                llm,
            )
            run_dir = Path(summary["run_dir"])
            events = [json.loads(line) for line in (run_dir / "logs" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
            transcript = [json.loads(line) for line in (run_dir / "logs" / "transcripts" / "agent_001.jsonl").read_text(encoding="utf-8").splitlines()]

            self.assertEqual(summary["reconciliation"]["status"], "valid")
            self.assertEqual([event["sequence"] for event in events], list(range(1, len(events) + 1)))
            self.assertTrue(all(event["event_id"].startswith("evt_") for event in events))
            self.assertEqual([record["kind"] for record in transcript], [
                "model_request", "model_response", "tool_result", "model_request", "model_response",
            ])
            self.assertIn("hello from agent", transcript[2]["content"]["content"])
            self.assertEqual(
                transcript[3]["content"]["messages"][-1]["content"],
                transcript[2]["content"]["content"],
            )

            tool_event = next(event for event in events if event["event_type"] == "tool_call")
            self.assertNotIn("hello from agent", json.dumps(tool_event, ensure_ascii=False))
            self.assertTrue(tool_event["artifact_refs"])
            llm_events = [event for event in events if event["event_type"] == "llm_call"]
            self.assertEqual(len(llm_events), 2)
            self.assertTrue(all(len(event["artifact_refs"]) >= 2 for event in llm_events))

    def test_private_content_is_redacted_and_invalidates_the_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            llm = MockLLMClient(default=[_response(content="copied evaluator_private/ground_truth.json: secret")])
            summary = run_experiment(
                RunConfig(
                    mode="single", agent_count=1, model="mock",
                    budgets={"hard_team_call_permits": 2}, runs_dir=Path(tmp), max_steps=2,
                ),
                llm,
            )
            run_dir = Path(summary["run_dir"])
            persisted = "\n".join(
                path.read_text(encoding="utf-8")
                for path in (run_dir / "logs").rglob("*.jsonl")
            )
            self.assertEqual(summary["run_validity"]["status"], "infrastructure_invalid")
            self.assertIn("hidden_evaluator_or_private_content", summary["reconciliation"]["reasons"])
            self.assertNotIn("ground_truth.json", persisted)
            self.assertIn("HIDDEN_CONTENT_REDACTED", persisted)

    def test_credentials_and_host_paths_are_not_persisted(self):
        with tempfile.TemporaryDirectory() as tmp:
            llm = MockLLMClient(default=[_response(content="Authorization: Bearer sk-super-secret /home/alice/token")])
            summary = run_experiment(
                RunConfig(
                    mode="single", agent_count=1, model="mock",
                    budgets={"hard_team_call_permits": 2}, runs_dir=Path(tmp), max_steps=2,
                ),
                llm,
            )
            run_dir = Path(summary["run_dir"])
            persisted = "\n".join(
                path.read_text(encoding="utf-8")
                for path in (run_dir / "logs").rglob("*.jsonl")
            )
            self.assertEqual(summary["run_validity"]["status"], "valid")
            self.assertNotIn("sk-super-secret", persisted)
            self.assertNotIn("/home/alice/token", persisted)
            self.assertIn("[REDACTED]", persisted)
            self.assertIn("<HOST_PATH>", persisted)


if __name__ == "__main__":
    unittest.main()
