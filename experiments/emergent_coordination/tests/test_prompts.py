from __future__ import annotations

import unittest

from experiments.emergent_coordination.harness.prompts import result_sync_message, system_prompt, user_prompt
from experiments.emergent_coordination.harness.tools.specs import tools_for_mode


class PromptPolicyTest(unittest.TestCase):
    def test_post_sync_verification_permission_only_appends_to_relevance_message(self):
        baseline = "repository_v1_t4_post_sync_relevance_v1"
        treatment = "repository_v1_t4_post_sync_verification_permission_v1"
        for agent_id in ("agent_001", "agent_004"):
            self.assertEqual(
                system_prompt("structured_team", agent_id, baseline, completion_policy="convergent_v2"),
                system_prompt("structured_team", agent_id, treatment, completion_policy="convergent_v2"),
            )
            self.assertEqual(
                user_prompt("structured_team", agent_id, 4, baseline),
                user_prompt("structured_team", agent_id, 4, treatment),
            )
        snapshot = {"completed_tasks": [{"id": "task_1", "owner": "agent_002", "result": "finding", "evidence_refs": ["evt_1"]}]}
        prior = result_sync_message(snapshot, profile=baseline)
        changed = result_sync_message(snapshot, profile=treatment)
        self.assertTrue(changed.startswith(prior + "\n\n"))
        addition = changed[len(prior):]
        for phrase in ("one bounded", "target-aligned", "read_file", "read-only search", "optional", "finalization"):
            self.assertIn(phrase, addition)
        for forbidden in ("must reuse", "must cite", "must change", "must perform"):
            self.assertNotIn(forbidden, addition.lower())

    def test_post_sync_relevance_v1_only_appends_relevance_instruction(self):
        baseline = "repository_v1_t4_post_sync_inspection_v2"
        treatment = "repository_v1_t4_post_sync_relevance_v1"
        for agent_id in ("agent_001", "agent_004"):
            self.assertEqual(
                system_prompt("structured_team", agent_id, baseline, completion_policy="convergent_v2"),
                system_prompt("structured_team", agent_id, treatment, completion_policy="convergent_v2"),
            )
            self.assertEqual(
                user_prompt("structured_team", agent_id, 4, baseline),
                user_prompt("structured_team", agent_id, 4, treatment),
            )
        snapshot = {"completed_tasks": [{"id": "task_1", "owner": "agent_002", "result": "finding", "evidence_refs": ["evt_1"]}]}
        prior = result_sync_message(snapshot, profile=baseline)
        changed = result_sync_message(snapshot, profile=treatment)
        self.assertTrue(changed.startswith(prior + "\n\n"))
        addition = changed[len(prior):]
        for phrase in ("direct relation", "code path", "security control", "no direct relation", "verification target"):
            self.assertIn(phrase, addition)
        for forbidden in ("must reuse", "must cite", "must change your finding", "must perform a check"):
            self.assertNotIn(forbidden, addition.lower())

    def test_post_sync_inspection_v2_changes_only_sync_message(self):
        baseline = "repository_v1_t4_result_sync_v1"
        treatment = "repository_v1_t4_post_sync_inspection_v2"
        self.assertEqual(system_prompt("structured_team", "agent_001", baseline, completion_policy="convergent_v2"),
                         system_prompt("structured_team", "agent_001", treatment, completion_policy="convergent_v2"))
        self.assertEqual(user_prompt("structured_team", "agent_001", 4, baseline),
                         user_prompt("structured_team", "agent_001", 4, treatment))
        snapshot = {"completed_tasks": [{"id": "task_1", "owner": "agent_002", "result": "finding", "evidence_refs": ["evt_1"]}]}
        baseline_message = result_sync_message(snapshot, profile=baseline)
        treatment_message = result_sync_message(snapshot, profile=treatment)
        self.assertNotIn("Inspect at least one completed task", baseline_message)
        for phrase in ("Inspect at least one completed task owned by another agent", "Choose the artifact that appears most relevant",
                       "Examine its result and supporting evidence", "Decide independently", "Do not incorporate foreign evidence"):
            self.assertIn(phrase, treatment_message)
        self.assertIn("list_tasks", treatment_message)
        self.assertIn("task_1", treatment_message)
        self.assertNotIn("must reuse", treatment_message.lower())

    def test_blackboard_prompt_does_not_induce_organization(self):
        text = system_prompt("raw_blackboard", "agent_001") + user_prompt("raw_blackboard", "agent_001", 2)
        forbidden = [
            "you are a team",
            "please cooperate",
            "divide the work",
            "mailbox",
            "claim a task",
            "elect a leader",
            "look at other agents",
        ]
        lowered = text.lower()
        for phrase in forbidden:
            self.assertNotIn(phrase, lowered)
        self.assertIn("/shared is a persistent directory", text)

    def test_tool_sets_differ_by_mode(self):
        names = lambda mode: {item["function"]["name"] for item in tools_for_mode(mode)}
        self.assertNotIn("shared_create", names("single"))
        self.assertNotIn("shared_create", names("parallel"))
        self.assertIn("shared_create", names("raw_blackboard"))
        self.assertNotIn("claim_task", names("raw_blackboard"))
        self.assertIn("claim_task", names("structured_team"))
        self.assertNotIn("list_agents", names("raw_blackboard"))

    def test_manager_worker_prompt_exposes_canonical_worker_ids(self):
        system = system_prompt("manager_worker", "agent_001", "repository_v1", role="manager")
        user = user_prompt("manager_worker", "agent_001", 4, "repository_v1", role="manager")

        for worker_id in ("agent_002", "agent_003", "agent_004"):
            self.assertIn(worker_id, user)
        self.assertIn("exact canonical worker ID", system)
        self.assertIn("Do not invent aliases", system)

        manager_create = next(
            item for item in tools_for_mode("manager_worker", "repository_v1", role="manager")
            if item["function"]["name"] == "manager_create_task"
        )
        self.assertIn("exact canonical agent ID", manager_create["function"]["description"])

    def test_completion_policy_is_opt_in(self):
        baseline = system_prompt("single", "agent_001", "repository_v1")
        calibrated = system_prompt("single", "agent_001", "repository_v1", completion_policy="convergent_v1")
        self.assertNotIn("bounded audit loop", baseline)
        self.assertIn("bounded audit loop", calibrated)
        guidance = system_prompt("single", "agent_001", "repository_v1", completion_policy="guidance_only")
        scheduler = system_prompt("single", "agent_001", "repository_v1", completion_policy="scheduler_only")
        self.assertIn("bounded audit loop", guidance)
        self.assertNotIn("bounded audit loop", scheduler)
        self.assertNotEqual(baseline, calibrated)
        with self.assertRaises(ValueError):
            system_prompt("single", "agent_001", completion_policy="unknown")

    def test_completion_generation_two_policies_keep_the_guidance_factor_split(self):
        # Factor A (guidance text) is byte-identical across generations; only
        # the runtime finalization gate differs.
        self.assertEqual(
            system_prompt("single", "agent_001", "repository_v1", completion_policy="convergent_v1"),
            system_prompt("single", "agent_001", "repository_v1", completion_policy="convergent_v2"),
        )
        scheduler_v2 = system_prompt("single", "agent_001", "repository_v1", completion_policy="scheduler_only_v2")
        scheduler_v1 = system_prompt("single", "agent_001", "repository_v1", completion_policy="scheduler_only")
        self.assertEqual(scheduler_v1, scheduler_v2)
        self.assertNotIn("bounded audit loop", scheduler_v2)
        self.assertIn("bounded audit loop", system_prompt("single", "agent_001", "repository_v1", completion_policy="convergent_v2"))
        self.assertIn("bounded audit loop", system_prompt("single", "agent_001", "repository_v1", completion_policy="guidance_only"))

    def test_t4_nonoverlap_prompt_is_weak_and_preserves_lifecycle(self):
        text = system_prompt("structured_team", "agent_001", "repository_v1_t4_nonoverlap_v1")
        self.assertIn("Call `list_tasks` and inspect both open and claimed task scopes", text)
        self.assertIn("materially distinct", text)
        self.assertIn("Treat two tasks as overlapping", text)
        self.assertIn("primary code scope or subsystem", text)
        self.assertIn("complete it with a concise result and valid `evidence_refs`", text)
        self.assertIn("This is a weak coordination constraint", text)
        self.assertIn("does not assign scopes", text)
        self.assertIn("does not require exhaustive repository partitioning", text)
        self.assertNotIn("auth/SSRF/file/OAuth", text)

    def test_t4_nonoverlap_profile_keeps_tool_schema_identical(self):
        baseline = {item["function"]["name"] for item in tools_for_mode("structured_team", "repository_v1")}
        nonoverlap = {item["function"]["name"] for item in tools_for_mode("structured_team", "repository_v1")}
        self.assertEqual(nonoverlap, baseline)

    def test_sequenced_bootstrap_prompt_is_identical_to_lifecycle_baseline(self):
        baseline = system_prompt("structured_team", "agent_001", "repository_v1_t4_task_lifecycle_v2")
        sequenced = system_prompt("structured_team", "agent_001", "repository_v1_t4_sequenced_bootstrap_v1")
        self.assertEqual(baseline, sequenced)
        self.assertEqual(
            user_prompt("structured_team", "agent_001", 4, "repository_v1_t4_task_lifecycle_v2"),
            user_prompt("structured_team", "agent_001", 4, "repository_v1_t4_sequenced_bootstrap_v1"),
        )

    def test_result_inspection_prompt_requires_inspection_without_forcing_adoption(self):
        baseline = system_prompt("structured_team", "agent_001", "repository_v1_t4_result_sync_v1")
        inspected = system_prompt("structured_team", "agent_001", "repository_v1_t4_result_inspection_prompt_v1")
        self.assertNotEqual(baseline, inspected)
        for phrase in (
            "Inspect at least one completed task owned by another agent",
            "Choose the artifact that appears most relevant",
            "Examine its result and supporting evidence",
            "Decide independently whether it changes, strengthens, contradicts, or is irrelevant",
            "Do not incorporate foreign evidence unless you understand what it supports",
        ):
            self.assertIn(phrase, inspected)
        lowered = inspected.lower()
        self.assertNotIn("must reuse", lowered)
        self.assertNotIn("must cite", lowered)
        self.assertNotIn("must modify finding", lowered)
        baseline_tools = {item["function"]["name"] for item in tools_for_mode("structured_team", "repository_v1")}
        inspection_tools = {item["function"]["name"] for item in tools_for_mode("structured_team", "repository_v1")}
        self.assertEqual(baseline_tools, inspection_tools)


if __name__ == "__main__":
    unittest.main()
