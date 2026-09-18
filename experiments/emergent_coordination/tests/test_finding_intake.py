from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from experiments.emergent_coordination.harness.events import EventLog
from experiments.emergent_coordination.harness.llm.client import LLMResponse, MockLLMClient
from experiments.emergent_coordination.harness.budget import TokenUsage
from experiments.emergent_coordination.harness.paths import TARGET_ROOT
from experiments.emergent_coordination.harness.runner import RunConfig, run_experiment
from experiments.emergent_coordination.harness.tools.sandbox import AgentSandbox
from experiments.emergent_coordination.harness.workspace import prepare_run_workspace


def _valid_finding(evidence_ref: str) -> dict:
    return {
        "title": "Potential debug disclosure",
        "category": "information_disclosure",
        "severity": "low",
        "source": {"file": "app/main.py", "function": "create_app", "anchor": "request.args"},
        "sink": {"file": "app/main.py", "function": "create_app", "anchor": "return response"},
        "reasoning_summary": "The reported code path exposes a response to a request.",
        "evidence_refs": [evidence_ref],
        "reproduction": {"attempted": False, "successful": False, "artifact_ref": None},
        "confidence": 0.4,
    }


def _response(*calls: dict, content: str | None = None) -> LLMResponse:
    return LLMResponse(
        content=content,
        tool_calls=list(calls),
        usage=TokenUsage(input_tokens=2, output_tokens=2, model="mock"),
        raw={"mock": True},
    )


def _tool_call(name: str, arguments: dict, call_id: str) -> dict:
    return {"id": call_id, "name": name, "arguments": json.dumps(arguments)}


class FindingIntakeTest(unittest.TestCase):
    def test_invalid_payload_is_rejected_atomically_with_field_errors_then_can_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            layout = prepare_run_workspace(Path(tmp) / "run", TARGET_ROOT, 1)
            events = EventLog(layout.logs / "events.jsonl", run_id="intake")
            sandbox = AgentSandbox("agent_001", layout, events)
            evidence = sandbox.read_file("target/app/main.py")["evidence_ref"]
            valid = _valid_finding(evidence)
            invalid = dict(valid)
            invalid["confidence"] = 2
            invalid["unexpected"] = "not allowed"

            rejected = sandbox.submit_findings([valid, invalid])
            self.assertFalse(rejected["ok"])
            self.assertIsNone(sandbox._submitted)
            self.assertEqual(sandbox.invalid_submission_attempts, 1)
            self.assertTrue(any(error["path"] == "findings[1].confidence" for error in rejected["errors"]))
            self.assertTrue(any(error["path"] == "findings[1].unexpected" for error in rejected["errors"]))

            accepted = sandbox.submit_findings([valid])
            self.assertTrue(accepted["ok"])
            self.assertEqual(sandbox._submitted, {"findings": [valid]})

    def test_target_prefixed_anchor_matches_target_prefixed_file_read_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            layout = prepare_run_workspace(Path(tmp) / "run", TARGET_ROOT, 1)
            events = EventLog(layout.logs / "events.jsonl", run_id="intake")
            sandbox = AgentSandbox("agent_001", layout, events)
            evidence = sandbox.read_file("target/app/main.py")["evidence_ref"]
            finding = _valid_finding(evidence)
            finding["source"]["file"] = "target/app/main.py"
            finding["sink"]["file"] = "target/app/main.py"

            accepted = sandbox.submit_findings([finding])

            self.assertTrue(accepted["ok"])
            self.assertEqual(sandbox._submitted, {"findings": [finding]})

    def test_unrelated_anchor_remains_rejected_after_path_normalization(self):
        with tempfile.TemporaryDirectory() as tmp:
            layout = prepare_run_workspace(Path(tmp) / "run", TARGET_ROOT, 1)
            events = EventLog(layout.logs / "events.jsonl", run_id="intake")
            sandbox = AgentSandbox("agent_001", layout, events)
            evidence = sandbox.read_file("target/app/main.py")["evidence_ref"]
            finding = _valid_finding(evidence)
            finding["source"]["file"] = "target/app/routes/files.py"
            finding["sink"]["file"] = "target/app/common/storage.py"

            rejected = sandbox.submit_findings([finding])

            self.assertFalse(rejected["ok"])
            self.assertTrue(any(error["path"] == "findings[0].evidence_refs" for error in rejected["errors"]))

    def test_final_invalid_payload_is_model_format_failure_not_infrastructure_failure(self):
        invalid = _valid_finding("evt_00000008")
        invalid.pop("source")
        with tempfile.TemporaryDirectory() as tmp:
            summary = run_experiment(
                RunConfig(
                    mode="single", agent_count=1, model="mock", max_steps=1,
                    budgets={"hard_team_call_permits": 1}, runs_dir=Path(tmp),
                ),
                MockLLMClient(default=[_response(content=json.dumps({"findings": [invalid]}))]),
            )

            self.assertEqual(summary["agent_results"][0]["stop_reason"], "model_format_failure")
            self.assertEqual(summary["invalid_submissions"], 1)
            self.assertEqual(summary["run_validity"]["status"], "valid")
            self.assertEqual(summary["evaluation"]["invalid_submissions"], 1)
            events = (Path(summary["run_dir"]) / "logs" / "events.jsonl").read_text(encoding="utf-8")
            self.assertIn("finding_submission_rejected", events)

    def test_malformed_tool_arguments_are_rejected_without_becoming_an_empty_submission(self):
        malformed_submit = {
            "id": "cut-off-submit",
            "name": "submit_findings",
            "arguments": '{"findings":[{"title":"truncated',
        }
        with tempfile.TemporaryDirectory() as tmp:
            summary = run_experiment(
                RunConfig(
                    mode="single", agent_count=1, model="mock", max_steps=2,
                    budgets={"hard_team_call_permits": 2}, runs_dir=Path(tmp),
                ),
                MockLLMClient(default=[
                    _response(malformed_submit),
                    _response(_tool_call("submit_findings", {"findings": []}, "valid-empty-submit")),
                ]),
            )

            self.assertEqual(summary["budget"]["attempted_llm_calls"], 2)
            self.assertEqual(summary["agent_results"][0]["submission_attempts"], 1)
            self.assertEqual(summary["agent_results"][0]["stop_reason"], "submitted")
            transcript = (
                Path(summary["run_dir"]) / "logs" / "transcripts" / "agent_001.jsonl"
            ).read_text(encoding="utf-8")
            self.assertIn("invalid_tool_arguments", transcript)
            events = (Path(summary["run_dir"]) / "logs" / "events.jsonl").read_text(encoding="utf-8")
            self.assertIn('"outcome": "rejected"', events)

    def test_non_object_tool_arguments_are_rejected_before_dispatch(self):
        non_object_submit = {"id": "array-submit", "name": "submit_findings", "arguments": "[]"}
        with tempfile.TemporaryDirectory() as tmp:
            summary = run_experiment(
                RunConfig(
                    mode="single", agent_count=1, model="mock", max_steps=2,
                    budgets={"hard_team_call_permits": 2}, runs_dir=Path(tmp),
                ),
                MockLLMClient(default=[
                    _response(non_object_submit),
                    _response(_tool_call("submit_findings", {"findings": []}, "valid-empty-submit")),
                ]),
            )

            self.assertEqual(summary["budget"]["attempted_llm_calls"], 2)
            self.assertEqual(summary["agent_results"][0]["submission_attempts"], 1)
            transcript = (
                Path(summary["run_dir"]) / "logs" / "transcripts" / "agent_001.jsonl"
            ).read_text(encoding="utf-8")
            self.assertIn("arguments_not_object", transcript)


if __name__ == "__main__":
    unittest.main()
