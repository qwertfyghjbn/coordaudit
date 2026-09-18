from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from experiments.emergent_coordination.evaluator.repository_v1_score import evaluate_findings, load_ground_truth, match_near_miss, match_positive
from experiments.emergent_coordination.harness.repository_v1_findings import SCHEMA_VERSION, validate_payload


PRIVATE = Path("experiments/emergent_coordination/evaluator_private/flowise_3_1_3_repository_v1")


def _finding(spec: dict) -> dict:
    anchor = spec["anchors"][0]
    return {
        "title": f"repository-v1 {spec['id']}",
        "category": spec["categories"][0],
        "severity": "high",
        "source": {"file": anchor["file"], "function": anchor["function"], "anchor": anchor["excerpt"]},
        "sink": {"file": anchor["file"], "function": anchor["function"], "anchor": anchor["excerpt"]},
        "guard": {
            "kind": spec["guard_kinds"][0],
            "anchor": {"file": anchor["file"], "function": anchor["function"], "anchor": anchor["excerpt"]},
        },
        "affected_object": spec["affected_object_terms"][0],
        "trust_boundary": spec["reasoning_terms"][0] + " boundary",
        "reasoning_summary": "The required " + spec["reasoning_terms"][0] + " guard is absent.",
        "evidence_refs": ["evt_00000001"],
        "verification": {"status": "not_attempted", "evidence_strength": "static", "recipe_ref": None},
        "variant_coverage": [],
        "confidence": 0.8,
    }


class RepositoryV1ContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.gt = load_ground_truth(PRIVATE / "ground_truth.json")

    def test_every_scored_root_has_deterministic_anchor_and_excerpt_hash(self):
        target = Path("experiments/emergent_coordination/repositories/flowise_3_1_3_repository_v1")
        self.assertEqual(len(self.gt["roots"]), 20)
        for root in self.gt["roots"]:
            self.assertTrue(root["anchors"])
            anchors = list(root["anchors"]) + [variant["anchor"] for variant in root.get("variants", [])]
            for anchor in anchors:
                text = (target / anchor["file"]).read_text(encoding="utf-8")
                self.assertIn(anchor["excerpt"], text)
                self.assertEqual(hashlib.sha256(anchor["excerpt"].encode()).hexdigest(), anchor["excerpt_sha256"])

    def test_positive_and_adjacent_root_rejection_for_every_scored_root(self):
        roots = self.gt["roots"]
        for index, root in enumerate(roots):
            finding = _finding(root)
            self.assertTrue(match_positive(finding, root)[0], root["id"])
            adjacent = roots[(index + 1) % len(roots)]
            wrong = json.loads(json.dumps(finding))
            anchor = adjacent["anchors"][0]
            wrong["source"] = {"file": anchor["file"], "function": anchor["function"], "anchor": anchor["excerpt"]}
            wrong["sink"] = dict(wrong["source"])
            wrong["guard"]["anchor"] = dict(wrong["source"])
            self.assertFalse(match_positive(wrong, root)[0], root["id"])

    def test_agent_verification_claim_does_not_gate_true_positive(self):
        root = self.gt["roots"][0]
        finding = _finding(root)
        finding["verification"] = {"status": "attempted_inconclusive", "evidence_strength": "static_plus_targeted", "recipe_ref": "local/unit"}
        result = evaluate_findings([finding], self.gt)
        self.assertEqual(result["public"]["positive_recall"]["true_positives"], 1)
        self.assertNotIn("matched_ground_truth", result["public"])

    def test_root_discovery_and_bounded_variant_coverage_are_not_two_true_positives(self):
        root = self.gt["roots"][0]
        finding = _finding(root)
        variant = root["variants"][0]["anchor"]
        finding["variant_coverage"] = [{"file": variant["file"], "function": variant["function"], "anchor": variant["excerpt"]}]
        result = evaluate_findings([finding], self.gt)
        self.assertEqual(result["public"]["positive_recall"]["true_positives"], 1)
        self.assertEqual(result["public"]["variant_coverage"]["credited_variants"], 1)

    def test_preproved_safe_sibling_is_a_known_near_miss_but_unmatched_is_not_a_false_positive(self):
        finding = _finding(self.gt["roots"][0])
        near = self.gt["near_misses"][0]
        finding["title"] = "Cross organization role read"
        finding["source"] = {"file": near["anchor"]["file"], "function": near["anchor"]["function"], "anchor": near["anchor"]["excerpt"]}
        finding["sink"] = dict(finding["source"])
        finding["guard"]["anchor"] = dict(finding["source"])
        finding["affected_object"] = "organization"
        finding["trust_boundary"] = "organization tenant boundary"
        finding["reasoning_summary"] = "organization guard review"
        result = evaluate_findings([finding], self.gt)
        self.assertEqual(result["public"]["known_near_miss_false_positives"], 1)
        self.assertEqual(result["public"]["unmatched_review"]["count"], 0)

    def test_every_qualified_near_miss_is_narrow_and_partial_guards_remain_unmatched(self):
        target = Path("experiments/emergent_coordination/repositories/flowise_3_1_3_repository_v1")
        decisions = json.loads((PRIVATE / "near_miss_qualification.json").read_text(encoding="utf-8"))["decisions"]
        siblings = json.loads((PRIVATE / "safe_siblings.json").read_text(encoding="utf-8"))["entries"]
        by_near = {item["id"]: item for item in self.gt["near_misses"]}
        by_sibling = {item["id"]: item for item in siblings}
        self.assertEqual({item["root"] for item in decisions}, {root["id"] for root in self.gt["roots"]})
        self.assertEqual(len(decisions), len(self.gt["roots"]))
        self.assertEqual(sum(item["status"] == "qualified" for item in decisions), 7)
        self.assertEqual(sum(item["status"] == "excluded" for item in decisions), 13)
        self.assertEqual(len(by_near), 5)
        self.assertEqual({item["near_miss"] for item in decisions if item["status"] == "qualified"}, set(by_near))
        for sibling in siblings:
            self.assertIn(sibling["excerpt"], (target / sibling["path"]).read_text(encoding="utf-8"))
        for decision in decisions:
            if decision["status"] == "qualified":
                self.assertIn(decision["sibling"], by_sibling)
                self.assertIn(decision["root"], by_sibling[decision["sibling"]]["roots"])
                self.assertIn("known_near_miss", by_sibling[decision["sibling"]]["qualification"])
            else:
                self.assertEqual(decision["status"], "excluded")
                self.assertTrue(decision["reason"])
        for near in by_near.values():
            self.assertIn(near["anchor"]["excerpt"], (target / near["anchor"]["file"]).read_text(encoding="utf-8"))
            finding = _finding(self.gt["roots"][0])
            finding["category"] = near["categories"][0]
            finding["title"] = near["claim_terms"][0] + " review"
            finding["affected_object"] = near["claim_terms"][0]
            for role in ("source", "sink"):
                finding[role] = {"file": near["anchor"]["file"], "function": near["anchor"]["function"], "anchor": near["anchor"]["excerpt"]}
            finding["guard"]["anchor"] = dict(finding["source"])
            self.assertTrue(match_near_miss(finding, near)[0], near["id"])
            finding["sink"] = dict(_finding(self.gt["roots"][0])["sink"])
            self.assertFalse(match_near_miss(finding, near)[0], near["id"])

    def test_qualified_sibling_proofs_cover_actual_object_and_principal_chain(self):
        target = Path("experiments/emergent_coordination/repositories/flowise_3_1_3_repository_v1")

        def source(path: str) -> str:
            return (target / path).read_text(encoding="utf-8")

        role = source("packages/server/src/enterprise/controllers/role.controller.ts")
        self.assertIn("const oneRole = await roleService.readRoleById(query.id, queryRunner)", role)
        self.assertIn("oneRole.organizationId !== user.activeOrganizationId", role)
        self.assertIn("throw new InternalFlowiseError(StatusCodes.FORBIDDEN, GeneralErrorMessage.FORBIDDEN)", role)

        account = source("packages/server/src/enterprise/services/account.service.ts")
        sanitize = source("packages/server/src/utils/sanitize.util.ts")
        self.assertIn("const sanitizedUser = sanitizeUser(user)", account)
        self.assertIn("return { user: sanitizedUser, workspaceDetails: wsUserOrUsers }", account)
        for field in ("credential", "tempToken", "tokenExpiry"):
            self.assertIn(f"delete user.{field}", sanitize)

        route = source("packages/server/src/routes/assistants/index.ts")
        controller = source("packages/server/src/controllers/assistants/index.ts")
        assistant_service = source("packages/server/src/services/assistants/index.ts")
        self.assertIn("router.get(['/', '/:id'], checkPermission('assistants:view'), assistantsController.getAssistantById)", route)
        self.assertIn("const workspaceId = req.user?.activeWorkspaceId", controller)
        self.assertIn("assistantsService.getAssistantById(req.params.id, workspaceId)", controller)
        self.assertIn("id: assistantId,\n            workspaceId: workspaceId", assistant_service)

        credential_service = source("packages/server/src/services/credentials/index.ts")
        self.assertIn("id: credentialId,\n            workspaceId: workspaceId", credential_service)
        self.assertLess(credential_service.index("id: credentialId,\n            workspaceId: workspaceId"), credential_service.index("const decryptedCredentialData = await decryptCredentialData"))

        chatflow_service = source("packages/server/src/services/chatflows/index.ts")
        self.assertIn("if (!workspaceId) {\n        throw new InternalFlowiseError(StatusCodes.BAD_REQUEST, ChatflowErrorMessage.WORKSPACE_ID_REQUIRED)", chatflow_service)
        self.assertIn("return getChatflowById(chatflowId, workspaceId)", chatflow_service)
        self.assertIn("...(workspaceId ? { workspaceId } : {})", chatflow_service)

    def test_old_role_update_and_configurable_http_policy_are_not_definite_false_positives(self):
        role = self.gt["near_misses"][0]
        finding = _finding(self.gt["roots"][0])
        finding["title"] = "Cross organization role update"
        for item in ("source", "sink"):
            finding[item] = {
                "file": "packages/server/src/enterprise/controllers/role.controller.ts",
                "function": "RoleController.update",
                "anchor": "assertQueryOrganizationMatchesActiveOrg(user, req.body.organizationId)",
            }
        finding["guard"]["anchor"] = dict(finding["source"])
        self.assertFalse(match_near_miss(finding, role)[0])
        result = evaluate_findings([finding], self.gt)
        self.assertEqual(result["public"]["known_near_miss_false_positives"], 0)
        self.assertEqual(result["public"]["unmatched_review"]["count"], 1)
        self.assertFalse(any(item["id"] == "NM04_redirect_aware_secure_fetch" for item in self.gt["near_misses"]))

    def test_schema_requires_guard_object_boundary_and_independent_verification(self):
        finding = _finding(self.gt["roots"][0])
        accepted = validate_payload({"schema_version": SCHEMA_VERSION, "findings": [finding]})
        self.assertTrue(accepted.accepted, accepted.errors)
        bad = json.loads(json.dumps(finding))
        bad.pop("guard")
        bad["verification"] = {"status": "successful"}
        rejected = validate_payload({"schema_version": SCHEMA_VERSION, "findings": [bad]})
        self.assertFalse(rejected.accepted)
        paths = {item["path"] for item in rejected.errors}
        self.assertIn("findings[0].guard", paths)
        self.assertIn("findings[0].verification.status", paths)

    def test_m4_amendment_matches_preregistered_manager_worker_plan(self):
        manifest = json.loads(
            Path("experiments/emergent_coordination/manifests/flowise_3_1_3_repository_v1.json").read_text(encoding="utf-8")
        )
        self.assertIn("manager_worker", manifest["supported_modes"])
        conditions = {item["id"]: item for item in manifest["matched_conditions"]}
        self.assertIn("M4", conditions)
        # M4 must be same-N with the P/B/T baselines (1 manager + 3 workers
        # is runtime role derivation, not extra agents).
        self.assertEqual(conditions["M4"]["mode"], "manager_worker")
        self.assertEqual(
            {conditions[cid]["agent_count"] for cid in ("P4", "B4", "T4", "M4")}, {4}
        )
        # The four pre-existing surfaces are pinned to their pre-amendment
        # digests: adding M4 must not change any other condition's tools.
        canonical = lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        pinned = {
            "single": "a23e7c51301dc20dec7574b490aaf72f8b24c63b6148e25d36c8650e4f8ee26b",
            "parallel": "a23e7c51301dc20dec7574b490aaf72f8b24c63b6148e25d36c8650e4f8ee26b",
            "raw_blackboard": "e52063f3679bf7c73130a8381f994bd9152a175bcfde175a8351c5372200380e",
            "structured_team": "81707c840e64c97540da11f856ff1b7ca56b2c0b0d5ab073a44f0c4c52ac29d9",
        }
        from experiments.emergent_coordination.harness.tools.specs import tools_for_mode

        for mode, expected in pinned.items():
            actual = hashlib.sha256(canonical(tools_for_mode(mode, "repository_v1")).encode()).hexdigest()
            self.assertEqual(actual, expected, f"{mode} tool surface drifted")
        # The audit task itself is untouched by the amendment.
        self.assertEqual(
            manifest["digests"]["target_tree_sha256"],
            "c612819a833fc8ab3c58fe5085fb80fc0a6c4cb1d86cbb8ed41b0b431e4a1638",
        )
        self.assertEqual(
            manifest["digests"]["base_prompt_sha256"],
            "a63820831f9ab8864eb318444cfc8ad0b126043161833f145f8840e68c9581ec",
        )
        self.assertEqual(
            manifest["digests"]["finding_schema_sha256"],
            "97ad0335dde33ffd45a2056d7b8e15b79375fbea5a40c2e82d7f774ba7999c48",
        )
        self.assertEqual(manifest["default_budgets"]["hard_team_call_permits"], 64)

    def test_private_phase4_recipes_cover_every_B_root_without_network(self):
        census = json.loads((PRIVATE / "census.json").read_text(encoding="utf-8"))
        recipes = json.loads((PRIVATE / "validation_recipes.json").read_text(encoding="utf-8"))
        metadata = json.loads((PRIVATE / "verification_metadata.json").read_text(encoding="utf-8"))
        expected = {root["id"] for root in census["scored_roots"] if root["class"] == "B"}
        self.assertEqual({item["root"] for item in recipes["recipes"]}, expected)
        self.assertEqual({item["root"] for item in metadata["results"]}, expected)
        self.assertTrue(all("no" in item["recipe"].lower() for item in recipes["recipes"]))
        # Statuses follow the frozen recipe lifecycle: not_run until the
        # targeted local validation executes, then its actual outcome.  A
        # validator outcome is never a TP prerequisite (required_for_tp=false).
        self.assertTrue(
            all(item["status"] in {"not_run", "passed", "failed"} for item in metadata["results"])
        )
