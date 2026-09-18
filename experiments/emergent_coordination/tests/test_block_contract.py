from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from experiments.emergent_coordination.harness.block_runner import BlockRunner, BlockRunnerError, condition_hashes
from experiments.emergent_coordination.harness.cases import load_case
from experiments.emergent_coordination.harness.contract import (
    ConditionSpec,
    ContractViolation,
    N4M_FLOWISE_CONDITIONS,
    N4_PILOT_CONDITIONS,
    load_block_config,
)
from experiments.emergent_coordination.harness.tools.specs import tools_for_mode


MANIFESTS_DIR = Path(__file__).resolve().parents[1] / "manifests"
CONFIG_PATH = MANIFESTS_DIR / "n4_pilot_v0.json"
FLOWISE_CONFIG_PATH = MANIFESTS_DIR / "n4_flowise_v1.json"
FLOWISE_CASE = load_case("flowise_3_1_3_repository_v1")
FLOWISE_TARGET_EXISTS = FLOWISE_CASE.target_root.is_dir()


def _write_config(tmp: str, **overrides: object) -> Path:
    config = json.loads(FLOWISE_CONFIG_PATH.read_text(encoding="utf-8"))
    config.update(overrides)
    path = Path(tmp) / "block_config.json"
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return path


def _write_five_condition_config(tmp: str) -> Path:
    return _write_config(
        tmp,
        contract_id="n4m_flowise_v1",
        conditions=[condition.as_dict() for condition in N4M_FLOWISE_CONDITIONS],
    )


class N4PilotContractTest(unittest.TestCase):
    def test_config_encodes_exactly_the_four_registered_conditions(self):
        config = load_block_config(CONFIG_PATH)

        self.assertEqual(config.contract_id, "n4_pilot_v0")
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

            self.assertEqual(manifest["contract"]["contract_id"], "n4_pilot_v0")
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


class ContractFamilyTest(unittest.TestCase):
    def test_flowise_contract_pins_case_permits_and_conditions(self):
        config = load_block_config(FLOWISE_CONFIG_PATH)

        self.assertEqual(config.contract_id, "n4_flowise_v1")
        self.assertEqual(config.repository_id, "flowise_3_1_3_repository_v1")
        self.assertEqual(config.conditions, N4_PILOT_CONDITIONS)
        self.assertEqual(config.hard_team_call_permits, 64)
        self.assertEqual(config.max_steps, 64)
        self.assertEqual(config.wall_clock_timeout_seconds, 1200)
        self.assertEqual(config.provider, "openai_compatible")
        self.assertEqual(config.requested_model, "deepseek-flash")
        self.assertEqual(config.max_output_tokens, 2048)

    def test_flowise_contract_rejects_drift(self):
        config = load_block_config(FLOWISE_CONFIG_PATH)
        with self.assertRaises(ContractViolation):
            replace(config, hard_team_call_permits=32).validate()
        with self.assertRaises(ContractViolation):
            replace(config, conditions=N4M_FLOWISE_CONDITIONS).validate()
        with self.assertRaises(ContractViolation):
            replace(config, repository_id="repo_pilot_v0").validate()
        with self.assertRaises(ContractViolation):
            replace(config, provider="other-provider").validate()
        with self.assertRaises(ContractViolation):
            replace(config, requested_model="other-model").validate()
        with self.assertRaises(ContractViolation):
            replace(config, max_output_tokens=1024).validate()

    def test_unknown_contract_family_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_config(tmp, contract_id="n8_flowise_v1")
            with self.assertRaises(ContractViolation):
                load_block_config(path)

    def test_five_condition_family_round_trips(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = load_block_config(_write_five_condition_config(tmp))

            self.assertEqual(config.contract_id, "n4m_flowise_v1")
            self.assertEqual(config.conditions, N4M_FLOWISE_CONDITIONS)
            self.assertIn(ConditionSpec("M4", "manager_worker", 4), config.conditions)
            self.assertEqual(config.hard_team_call_permits, 64)

    def test_freeze_rejects_conditions_the_case_does_not_declare(self):
        # A five-condition contract must be un-freezable against a case that
        # has not declared M4 in matched_conditions; a synthetic
        # pre-amendment manifest keeps this regression independent of the
        # live case amendment state.
        with tempfile.TemporaryDirectory() as tmp:
            config = load_block_config(_write_five_condition_config(tmp))
            pre_amendment = replace(
                FLOWISE_CASE,
                manifest={
                    **FLOWISE_CASE.manifest,
                    "matched_conditions": [
                        item for item in FLOWISE_CASE.manifest["matched_conditions"] if item["id"] != "M4"
                    ],
                },
            )
            with patch(
                "experiments.emergent_coordination.harness.block_runner.load_case",
                return_value=pre_amendment,
            ):
                with self.assertRaises(BlockRunnerError) as raised:
                    BlockRunner(config, Path(tmp) / "runs").freeze("premature-m4-block")

            self.assertIn("matched_conditions", str(raised.exception))


class ManagerWorkerConditionHashTest(unittest.TestCase):
    def test_non_manager_conditions_keep_the_flat_legacy_shape(self):
        hashes = condition_hashes(ConditionSpec("T4", "structured_team", 4), FLOWISE_CASE)

        self.assertEqual(
            set(hashes),
            {"system_prompt_template", "user_prompt_template", "tool_schema", "identity_rule"},
        )
        self.assertEqual(hashes["identity_rule"], "agent_001..agent_N")

    def test_manager_worker_records_both_role_surfaces(self):
        condition = ConditionSpec("M4", "manager_worker", 4)
        hashes = condition_hashes(condition, FLOWISE_CASE)

        self.assertEqual(set(hashes), {"manager", "worker"})
        for role_hashes in hashes.values():
            self.assertEqual(
                set(role_hashes),
                {"system_prompt_template", "user_prompt_template", "tool_schema", "identity_rule"},
            )
        self.assertNotEqual(hashes["manager"]["tool_schema"], hashes["worker"]["tool_schema"])
        self.assertNotEqual(
            hashes["manager"]["system_prompt_template"], hashes["worker"]["system_prompt_template"]
        )
        self.assertEqual(hashes["manager"]["identity_rule"], "agent_001")
        self.assertEqual(hashes["worker"]["identity_rule"], "agent_002..agent_N")


@unittest.skipUnless(FLOWISE_TARGET_EXISTS, "flowise target tree is not materialized")
class FlowiseBlockFreezeTest(unittest.TestCase):
    def test_freeze_flowise_block_one_contract(self):
        config = load_block_config(FLOWISE_CONFIG_PATH)
        with tempfile.TemporaryDirectory() as tmp:
            frozen = BlockRunner(config, Path(tmp)).freeze("flowise-block-one-test")
            manifest = json.loads(frozen.manifest_path.read_text(encoding="utf-8"))

            self.assertEqual(manifest["contract"]["contract_id"], "n4_flowise_v1")
            self.assertEqual(manifest["contract"]["hard_team_call_permits"], 64)
            self.assertEqual(manifest["contract"]["model"]["max_output_tokens"], 2048)
            self.assertEqual(set(manifest["hashes"]["conditions"]), {"S1", "P4", "B4", "T4"})
            for condition_id, entry in manifest["hashes"]["conditions"].items():
                self.assertEqual(
                    set(entry),
                    {"system_prompt_template", "user_prompt_template", "tool_schema", "identity_rule"},
                    condition_id,
                )
            self.assertIn("target_tree", manifest["digests"])
            self.assertIn("evaluator_private_tree", manifest["digests"])
            self.assertEqual(manifest["live_gate"]["status"], "open")

    def test_freeze_five_condition_contract_records_role_aware_hashes(self):
        # The amended case declares M4, so the five-condition family freezes
        # and the M4 entry records both role surfaces.
        with tempfile.TemporaryDirectory() as tmp:
            config = load_block_config(_write_five_condition_config(tmp))
            frozen = BlockRunner(config, Path(tmp)).freeze("flowise-m4-freeze-test")
            manifest = json.loads(frozen.manifest_path.read_text(encoding="utf-8"))

            self.assertEqual(manifest["contract"]["contract_id"], "n4m_flowise_v1")
            entries = manifest["hashes"]["conditions"]
            self.assertEqual(set(entries), {"S1", "P4", "B4", "T4", "M4"})
            self.assertEqual(set(entries["M4"]), {"manager", "worker"})
            for role_entry in entries["M4"].values():
                self.assertEqual(
                    set(role_entry),
                    {"system_prompt_template", "user_prompt_template", "tool_schema", "identity_rule"},
                )
            self.assertEqual(
                set(entries["T4"]),
                {"system_prompt_template", "user_prompt_template", "tool_schema", "identity_rule"},
            )


if __name__ == "__main__":
    unittest.main()
