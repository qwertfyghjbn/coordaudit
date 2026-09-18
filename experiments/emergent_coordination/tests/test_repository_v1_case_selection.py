from __future__ import annotations

import json
import hashlib
import tempfile
import unittest
from pathlib import Path

from experiments.emergent_coordination.harness.cases import available_case_ids, load_case
from experiments.emergent_coordination.harness.block_runner import tree_digest
from experiments.emergent_coordination.harness.prompts import base_prompt
from experiments.emergent_coordination.harness.llm.client import LLMResponse, MockLLMClient
from experiments.emergent_coordination.harness.budget import TokenUsage
from experiments.emergent_coordination.harness.runner import RunConfig, run_experiment
from experiments.emergent_coordination.harness.tools.specs import tools_for_mode
from experiments.emergent_coordination.run_experiment import mock_client_for_case


CASE_ID = "flowise_3_1_3_repository_v1"


def _submit_empty(call_id: str) -> LLMResponse:
    return LLMResponse(
        content=None,
        tool_calls=[
            {
                "id": call_id,
                "name": "submit_findings",
                "arguments": json.dumps({"schema_version": "repository-v1", "findings": []}),
            }
        ],
        usage=TokenUsage(input_tokens=2, output_tokens=2, model="mock"),
        raw={"mock": True},
    )


class RepositoryV1CaseSelectionTest(unittest.TestCase):
    def test_registered_case_is_trusted_and_does_not_change_v0_default(self):
        self.assertIn("repo_pilot_v0", available_case_ids())
        self.assertIn(CASE_ID, available_case_ids())
        self.assertEqual(load_case().case_id, "repo_pilot_v0")
        case = load_case(CASE_ID)
        self.assertEqual(case.prompt_profile, "repository_v1")
        self.assertEqual(case.finding_schema, "repository_v1")
        self.assertEqual(case.evaluator, "repository_v1")
        self.assertTrue(case.target_root.is_dir())
        self.assertTrue(case.ground_truth_path.is_file())
        self.assertFalse(str(case.evaluator_private_root).startswith(str(case.target_root)))

    def test_manifest_hashes_bind_target_private_prompt_schema_and_tools(self):
        case = load_case(CASE_ID)
        digests = case.manifest["digests"]
        common, schema = base_prompt("repository_v1")
        canonical = lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        tool_surface = {mode: tools_for_mode(mode, "repository_v1") for mode in ("single", "parallel", "raw_blackboard", "structured_team")}
        self.assertEqual(digests["target_tree_sha256"], tree_digest(case.target_root))
        self.assertEqual(digests["evaluator_private_tree_sha256"], tree_digest(case.evaluator_private_root))
        self.assertEqual(digests["base_prompt_sha256"], hashlib.sha256((common + "\n" + schema).encode()).hexdigest())
        self.assertEqual(
            digests["finding_schema_sha256"],
            hashlib.sha256(Path("experiments/emergent_coordination/harness/repository_v1_findings.py").read_bytes()).hexdigest(),
        )
        self.assertEqual(digests["tool_surface_sha256"], hashlib.sha256(canonical(tool_surface).encode()).hexdigest())

    def test_v1_tool_surface_has_its_own_schema_but_no_blackboard_or_team_leakage(self):
        for mode in ("single", "parallel", "raw_blackboard", "structured_team"):
            tools = tools_for_mode(mode, "repository_v1")
            submit = next(item for item in tools if item["function"]["name"] == "submit_findings")
            self.assertEqual(submit["function"]["parameters"]["required"], ["schema_version", "findings"])
            names = {item["function"]["name"] for item in tools}
            if mode == "raw_blackboard":
                self.assertIn("shared_create", names)
                self.assertFalse({"claim_task", "send_message", "list_messages"} & names)
            elif mode == "structured_team":
                self.assertIn("claim_task", names)
                self.assertFalse({"shared_create", "send_message", "list_messages"} & names)
            else:
                self.assertFalse({"shared_create", "claim_task", "send_message", "list_messages"} & names)

    def test_cli_mock_default_uses_selected_case_schema(self):
        response = mock_client_for_case(load_case(CASE_ID).manifest).complete([], [], agent_id="agent_001")
        self.assertEqual(json.loads(response.content or "{}"), {"schema_version": "repository-v1", "findings": []})

    def test_flowise_target_has_no_private_benchmark_or_fix_leakage(self):
        target = load_case(CASE_ID).target_root
        needles = (
            "ghsa-",
            "cve-",
            "ground_truth",
            "evaluator_private",
            "09f099dbfda179e439ec677d06ad737375899eef",
            "a65f81bb43ef66d3ce734bf0dff4223ae8041c95",
            CASE_ID,
            "/home/lqs/coordaudit",
            "provenance",
        )
        hits = []
        for path in target.rglob("*"):
            if not path.is_file():
                continue
            content = path.read_text(encoding="utf-8", errors="ignore").lower()
            hits.extend(f"{path.relative_to(target)}:{needle}" for needle in needles if needle in content)
        self.assertEqual(hits, [])
        self.assertFalse((target / ".git").exists())

    def test_mock_s_p_b_t_share_flowise_target_prompt_schema_and_team_budget(self):
        case = load_case(CASE_ID)
        expected_budgets = dict(case.manifest["default_budgets"])
        runs: list[Path] = []
        with tempfile.TemporaryDirectory() as tmp:
            for mode, agent_count in (("single", 1), ("parallel", 4), ("raw_blackboard", 4), ("structured_team", 4)):
                scripts = {f"agent_{index:03d}": [_submit_empty(f"{mode}-{index}")] for index in range(1, agent_count + 1)}
                summary = run_experiment(
                    RunConfig(
                        mode=mode,
                        agent_count=agent_count,
                        model="mock",
                        budgets=expected_budgets,
                        max_steps=1,
                        max_provider_retries=expected_budgets["max_provider_retries"],
                        runs_dir=Path(tmp),
                        case_id=CASE_ID,
                    ),
                    MockLLMClient(scripts=scripts),
                )
                run_dir = Path(summary["run_dir"])
                runs.append(run_dir)
                manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
                self.assertEqual(manifest["repository"], CASE_ID)
                self.assertEqual(manifest["prompt_profile"], "repository_v1")
                self.assertEqual(manifest["finding_schema"], "repository_v1")
                self.assertEqual(manifest["budgets"], expected_budgets)
                self.assertEqual(tree_digest(run_dir / "runtime" / "target"), case.manifest["digests"]["target_tree_sha256"])
                self.assertEqual(summary["evaluation"]["positive_recall"]["true_positives"], 0)
                self.assertEqual(summary["evaluation"]["unmatched_review"]["count"], 0)
                self.assertFalse((run_dir / "runtime" / "target" / "ground_truth.json").exists())
                self.assertTrue((run_dir / "evaluator_private" / "ground_truth.json").exists())

            prompts = []
            for run_dir in runs:
                request = next(
                    json.loads(line)
                    for line in (run_dir / "logs" / "transcripts" / "agent_001.jsonl").read_text(encoding="utf-8").splitlines()
                    if json.loads(line)["kind"] == "model_request"
                )
                prompts.append(request["content"])
            common, schema = base_prompt("repository_v1")
            expected_system_prefix = common + "\n\nYour agent identity is agent_001.\n\n" + schema
            self.assertTrue(all(item["messages"][0]["content"].startswith(expected_system_prefix) for item in prompts))
            self.assertTrue(all(item["messages"][1]["content"].split(" You are process")[0] == prompts[0]["messages"][1]["content"].split(" You are process")[0] for item in prompts))
            self.assertTrue(all(any(tool["function"]["name"] == "submit_findings" and tool["function"]["parameters"]["required"] == ["schema_version", "findings"] for tool in item["tools"]) for item in prompts))


if __name__ == "__main__":
    unittest.main()
