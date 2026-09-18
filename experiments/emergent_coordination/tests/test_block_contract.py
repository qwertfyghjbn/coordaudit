from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from experiments.emergent_coordination.harness.block_runner import BlockRunner, BlockRunnerError
from experiments.emergent_coordination.harness.contract import (
    ContractViolation,
    N4_PILOT_CONDITIONS,
    load_block_config,
)
from experiments.emergent_coordination.harness.tools.specs import tools_for_mode


CONFIG_PATH = Path(__file__).resolve().parents[1] / "manifests" / "n4_pilot_v0.json"


class N4PilotContractTest(unittest.TestCase):
    def test_config_encodes_exactly_the_four_registered_conditions(self):
        config = load_block_config(CONFIG_PATH)

        self.assertEqual(config.conditions, N4_PILOT_CONDITIONS)
        self.assertEqual(config.hard_team_call_permits, 32)
        self.assertEqual(config.max_output_tokens, 1024)
        self.assertEqual(config.max_steps, 32)
        self.assertEqual(config.max_provider_retries, 1)
        self.assertIsNone(config.per_agent_token_cap)
        self.assertEqual(config.thinking_mode, "disabled")

    def test_primary_t4_tool_surface_is_minimal_task_state(self):
        names = {item["function"]["name"] for item in tools_for_mode("structured_team")}

        self.assertTrue({"create_task", "list_tasks", "claim_task", "release_task", "complete_task"} <= names)
        self.assertFalse({"send_message", "list_messages", "publish_artifact", "list_artifacts"} & names)

    def test_rejects_a_condition_or_budget_drift(self):
        config = load_block_config(CONFIG_PATH)
        with self.assertRaises(ContractViolation):
            replace(config, hard_team_call_permits=40).validate()
        with self.assertRaises(ContractViolation):
            replace(config, conditions=config.conditions[:-1]).validate()
        with self.assertRaises(ContractViolation):
            replace(config, thinking_mode="enabled").validate()

    def test_freeze_writes_a_hash_addressable_block_manifest(self):
        config = load_block_config(CONFIG_PATH)
        with tempfile.TemporaryDirectory() as tmp:
            frozen = BlockRunner(config, Path(tmp)).freeze("n4-contract-test")
            manifest = json.loads(frozen.manifest_path.read_text(encoding="utf-8"))

            self.assertEqual(manifest["contract"]["conditions"], [condition.as_dict() for condition in N4_PILOT_CONDITIONS])
            self.assertEqual(manifest["contract"]["hard_team_call_permits"], 32)
            self.assertIn("target_tree", manifest["digests"])
            self.assertIn("evaluator_private_tree", manifest["digests"])
            self.assertIn("common_prompt", manifest["hashes"])
            self.assertEqual(set(manifest["hashes"]["conditions"]), {condition.id for condition in N4_PILOT_CONDITIONS})
            self.assertEqual(manifest["live_gate"]["status"], "open")
            self.assertEqual(
                {item["requirement"] for item in manifest["live_gate"]["satisfied_before_execution"]},
                {
                    "pre_call_permit_ledger",
                    "fail_closed_os_sandbox",
                    "model_visible_transcript_and_reconciliation",
                    "strict_finding_schema_dedup_and_private_verification",
                },
            )
            self.assertTrue(
                all(item["evidence"].strip() for item in manifest["live_gate"]["satisfied_before_execution"])
            )
            self.assertEqual(frozen.block_dir, Path(tmp) / "n4-contract-test")

            with self.assertRaises(BlockRunnerError):
                BlockRunner(config, Path(tmp)).freeze("n4-contract-test")


if __name__ == "__main__":
    unittest.main()
