from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from experiments.emergent_coordination.evaluator import repository_v1_1_score as v2
from experiments.emergent_coordination.evaluator.repository_v1_score import evaluate_findings as v1_evaluate
from experiments.emergent_coordination.evaluator.repository_v1_score import load_ground_truth as v1_load
from experiments.emergent_coordination.harness.cases import load_case
from experiments.emergent_coordination.harness.block_runner import BlockRunner
from experiments.emergent_coordination.harness.contract import ContractViolation, load_block_config
from experiments.emergent_coordination.harness.runner import _evaluate_for_case, _load_ground_truth_for_case


PRIVATE = Path("experiments/emergent_coordination/evaluator_private")
GT = PRIVATE / "flowise_3_1_3_repository_v1_1/ground_truth.json"


def finding(root: dict, anchor: dict | None = None) -> dict:
    anchor = anchor or root["anchors"][0]
    place = {"file": anchor["file"], "function": anchor["function"], "anchor": anchor["excerpt"]}
    return {
        "title": "test " + root["id"],
        "category": root["categories"][0],
        "source": dict(place),
        "sink": dict(place),
        "guard": {"kind": root["guard_kinds"][0], "anchor": dict(place)},
        "affected_object": root["affected_object_terms"][0],
        "trust_boundary": root["reasoning_terms"][0] + " boundary",
        "reasoning_summary": "missing " + root["reasoning_terms"][0] + " check",
        "variant_coverage": [],
    }


class RepositoryV11EvaluatorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.gt = v2.load_ground_truth(GT)
        cls.roots = {root["id"].split("_")[0]: root for root in cls.gt["roots"]}

    def score(self, *findings: dict, adjudications=None):
        return v2.evaluate_findings(list(findings), self.gt, adjudications=adjudications)

    def test_canonical_anchor_and_fixed_denominator(self):
        result = self.score(finding(self.roots["R01"]))
        score = result["public"]["canonical_score"]
        self.assertEqual((score["root_denominator"], score["true_positives"], score["false_negatives"]), (30, 1, 29))
        self.assertEqual(result["private"]["per_finding"][0]["classification"], "canonical_tp")

    def test_approved_equivalent_anchor_with_invariant(self):
        root = self.roots["R01"]
        report = finding(root, root["equivalent_anchors_v1_1"][0])
        report["reasoning_summary"] = "organization object read without active tenant access check"
        result = self.score(report)
        self.assertEqual(result["private"]["per_finding"][0]["classification"], "equivalent_tp")
        self.assertEqual(result["private"]["per_finding"][0]["anchor_id"], "EA_R01_org_read")

    def test_wrong_or_unapproved_equivalent_anchor_cannot_match(self):
        root = self.roots["R01"]
        report = finding(root, {**root["equivalent_anchors_v1_1"][0], "function": "wrong.method"})
        report["reasoning_summary"] = "organization read without tenant access check"
        self.assertEqual(self.score(report)["private"]["per_finding"][0]["classification"], "unmatched_unreviewed")
        corrupted = copy.deepcopy(self.gt)
        corrupted["roots"][0]["accepted_equivalent_realizations_v1_1"] = []
        with self.assertRaises(ValueError):
            v2.evaluate_findings([report], corrupted)

    def test_r07_r08_historical_function_drift_repairs(self):
        r07 = self.roots["R07"]
        a = finding(r07, r07["equivalent_anchors_v1_1"][0])
        a["reasoning_summary"] = "invited account activation lacks invitation token proof"
        r08 = self.roots["R08"]
        b = finding(r08, r08["equivalent_anchors_v1_1"][0])
        b["reasoning_summary"] = "email match without issuer and subject identity proof"
        result = self.score(a, b)
        self.assertEqual([item["classification"] for item in result["private"]["per_finding"]], ["equivalent_tp", "equivalent_tp"])
        legacy_a = finding(r07)
        legacy_a["reasoning_summary"] = a["reasoning_summary"]
        self.assertEqual(self.score(legacy_a)["private"]["per_finding"][0]["classification"], "unmatched_unreviewed")

    def test_bounded_historical_function_spelling_aliases(self):
        r01 = self.roots["R01"]
        report = finding(r01, r01["equivalent_anchors_v1_1"][0])
        report["reasoning_summary"] = "organization read without tenant access check"
        for role in ("source", "sink"):
            report[role]["function"] = "read"
        report["guard"]["anchor"]["function"] = "read"
        self.assertEqual(self.score(report)["private"]["per_finding"][0]["classification"], "equivalent_tp")
        report["source"]["function"] = "OtherController.read"
        report["sink"]["function"] = "OtherController.read"
        report["guard"]["anchor"]["function"] = "OtherController.read"
        self.assertEqual(self.score(report)["private"]["per_finding"][0]["classification"], "unmatched_unreviewed")

    def test_category_guard_and_reasoning_invariant_mismatches(self):
        root = self.roots["R07"]
        base = finding(root, root["equivalent_anchors_v1_1"][0])
        base["reasoning_summary"] = "invitation token proof bypass"
        for mutation in ({"category": "information_disclosure"}, {"guard": {"kind": "present", "anchor": base["guard"]["anchor"]}}, {"reasoning_summary": "missing token check", "affected_object": "account"}):
            report = {**base, **mutation}
            if "reasoning_summary" in mutation:
                report["trust_boundary"] = "token boundary"
            self.assertEqual(self.score(report)["private"]["per_finding"][0]["classification"], "unmatched_unreviewed")

    def test_variant_coverage_only_does_not_create_formal_tp(self):
        root = self.roots["R01"]
        report = finding(root)
        report["variant_coverage"] = [report["source"]]
        report["source"] = report["sink"] = report["guard"]["anchor"] = {"file": "x", "function": "y", "anchor": "z"}
        self.assertEqual(self.score(report)["private"]["per_finding"][0]["classification"], "unmatched_unreviewed")

    def test_duplicate_fingerprint_and_duplicate_root(self):
        root = self.roots["R01"]
        a = finding(root)
        b = copy.deepcopy(a)
        c = finding(root, root["equivalent_anchors_v1_1"][0])
        c["reasoning_summary"] = "organization read without tenant access check"
        result = self.score(a, b, c)
        self.assertEqual([item["classification"] for item in result["private"]["per_finding"]], ["canonical_tp", "duplicate", "duplicate_root"])
        self.assertEqual(result["public"]["canonical_score"]["duplicates"], 2)

    def test_novel_adjudication_does_not_change_denominator(self):
        report = finding(self.roots["R01"])
        report["source"]["file"] = "unrelated.ts"
        report["sink"]["file"] = "unrelated.ts"
        report["guard"]["anchor"]["file"] = "unrelated.ts"
        fp = v2._fingerprint(report)
        decisions = {fp: {"classification": "validated_novel_tp", "reviewer": "condition-blind panel", "provenance": "independent review", "condition_blind": True, "independent_code_validation": "static trace", "source_sink_guard_evidence": "source to sink; guard absent"}}
        result = self.score(report, adjudications=decisions)
        self.assertEqual(result["public"]["novel_finding_view"]["validated_novel_tp"], 1)
        self.assertEqual(result["public"]["canonical_score"]["root_denominator"], 30)
        self.assertEqual(result["public"]["canonical_score"]["true_positives"], 0)
        with self.assertRaises(ValueError):
            self.score(report, adjudications={fp: {"classification": "validated_novel_tp", "reviewer": "x", "provenance": "y"}})

    def test_known_gt_overlap_without_formal_anchor_is_not_novel(self):
        root = self.roots["R01"]
        report = finding(root)
        for role in ("source", "sink"):
            report[role]["file"] = "unapproved.ts"
        report["guard"]["anchor"]["file"] = "unapproved.ts"
        fingerprint = v2._fingerprint(report)
        decision = {fingerprint: {"classification": "gt_overlap_uncredited", "root_ids": [root["id"]], "reviewer": "panel", "provenance": "historical adjudication"}}
        result = self.score(report, adjudications=decision)
        self.assertEqual(result["private"]["per_finding"][0]["classification"], "gt_overlap_uncredited")
        self.assertEqual(result["public"]["canonical_score"]["known_gt_overlap_uncredited"], 1)
        self.assertEqual(result["public"]["novel_finding_view"]["unmatched_unreviewed"], 0)

    def test_fp_inconclusive_and_unmatched_routing(self):
        near = self.gt["near_misses"][0]
        base = finding(self.roots["R01"], near["anchor"])
        base["category"] = near["categories"][0]
        base["title"] = near["claim_terms"][0]
        base["affected_object"] = near["claim_terms"][0]
        other = finding(self.roots["R01"])
        for role in ("source", "sink"):
            other[role]["file"] = "unknown.ts"
        other["guard"]["anchor"]["file"] = "unknown.ts"
        third = copy.deepcopy(other)
        third["source"]["function"] = "different"
        decision = {v2._fingerprint(other): {"classification": "inconclusive", "reviewer": "panel", "provenance": "review ledger"}}
        result = self.score(base, other, third, adjudications=decision)
        view = result["public"]["novel_finding_view"]
        self.assertEqual((view["false_positive"], view["inconclusive"], view["unmatched_unreviewed"]), (1, 1, 1))

    def test_v1_regression_and_v2_case_dispatch(self):
        old = v1_load(PRIVATE / "flowise_3_1_3_repository_v1/ground_truth.json")
        old_report = finding(old["roots"][0])
        self.assertEqual(v1_evaluate([old_report], old)["public"]["positive_recall"]["true_positives"], 1)
        case = load_case(v2.CASE_ID)
        self.assertEqual(_load_ground_truth_for_case(case, Path("/nonexistent"))["case_id"], v2.CASE_ID)
        self.assertEqual(_evaluate_for_case(case, [old_report], self.gt, 0)["public"]["evaluator_generation"], v2.EVALUATOR_GENERATION)
        with self.assertRaises(ValueError):
            v2.evaluate_findings([old_report], old)

    def test_deterministic_output_and_pinned_gt_hash(self):
        report = finding(self.roots["R01"])
        a = self.score(report)
        self.assertEqual(a, self.score(copy.deepcopy(report)))
        self.assertFalse(a["public"]["semantic_judge_used"])
        self.assertEqual(hashlib.sha256(GT.read_bytes()).hexdigest(), v2.GT_SHA256)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gt.json"
            path.write_text(json.dumps(self.gt), encoding="utf-8")
            with self.assertRaises(ValueError):
                v2.load_ground_truth(path)

    def test_formal_block_has_one_evaluator_generation(self):
        manifests = Path("experiments/emergent_coordination/manifests")
        config = load_block_config(manifests / "n4m_flowise_calibration_v1.json")
        runtime = copy.deepcopy(config.condition_runtime)
        assert runtime is not None
        runtime["S1"]["evaluator_generation"] = v2.EVALUATOR_GENERATION
        mixed = replace(config, condition_runtime=runtime)
        with self.assertRaises(ContractViolation):
            mixed.validate()
        with self.assertRaises(ContractViolation):
            replace(config, repository_id=v2.CASE_ID).validate()
        with tempfile.TemporaryDirectory() as directory:
            old_config = load_block_config(manifests / "n4_pilot_v0.json")
            manifest = BlockRunner(old_config, Path(directory))._build_manifest("v1-block")
            self.assertEqual(manifest["evaluator_generation"], "repository_pilot_v0")


if __name__ == "__main__":
    unittest.main()
