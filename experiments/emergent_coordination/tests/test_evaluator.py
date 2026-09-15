from __future__ import annotations

import unittest

from experiments.emergent_coordination.evaluator.score import evaluate_findings, load_ground_truth
from experiments.emergent_coordination.harness.paths import GROUND_TRUTH_PATH


def _finding(spec: dict, *, submitted_by: str = "agent_001") -> dict:
    semantics = spec["required_semantics"]
    source = semantics["source"]
    sink = semantics["sink"]
    return {
        "title": f"canonical {spec['category']} finding",
        "category": spec["category"],
        "severity": "high",
        "source": {"file": source["file"], "function": source["function"], "anchor": source["code_snippet"]},
        "sink": {"file": sink["file"], "function": sink["function"], "anchor": sink["code_snippet"]},
        "reasoning_summary": "The controlled source reaches the reported sink.",
        "evidence_refs": ["evt_00000008"],
        "reproduction": {"attempted": True, "successful": True, "artifact_ref": None},
        "confidence": 0.9,
        "submitted_by": submitted_by,
    }


class EvaluatorTest(unittest.TestCase):
    def setUp(self):
        self.gt = load_ground_truth(GROUND_TRUTH_PATH)

    def test_perfect_positive_set_uses_canonical_category_source_and_sink(self):
        result = evaluate_findings([_finding(spec) for spec in self.gt["findings"]], self.gt)
        public = result["public"]

        self.assertEqual(public["positive_recall"], {"true_positives": 3, "false_negatives": 0, "value": 1.0})
        self.assertEqual(public["known_near_miss_false_positives"], 0)
        self.assertEqual(public["unmatched_review"]["count"], 0)
        self.assertEqual(public["precision_bounds"]["closed_world_lower_bound"], 1.0)
        self.assertEqual(public["evaluator_verified_findings"], 3)
        self.assertFalse(public["semantic_judge_used"])
        self.assertNotIn("matched_ground_truth", public)

    def test_near_miss_is_known_false_positive_and_unmatched_is_not_asserted_false(self):
        near = self.gt["near_misses"][0]
        finding = _finding(self.gt["findings"][0])
        finding["source"] = {
            "file": near["locations"][2]["file"], "function": near["locations"][2]["function"], "anchor": "filename = request.args.get('filename')",
        }
        finding["sink"] = {
            "file": near["locations"][0]["file"], "function": near["locations"][0]["function"], "anchor": "os.path.realpath(candidate)",
        }
        unmatched = _finding(self.gt["findings"][1])
        unmatched["category"] = "other"
        result = evaluate_findings([finding, unmatched], self.gt)

        public = result["public"]
        self.assertEqual(public["known_near_miss_false_positives"], 1)
        self.assertEqual(public["unmatched_review"]["count"], 1)
        self.assertEqual(public["precision_bounds"]["closed_world_lower_bound"], 0.0)
        self.assertEqual(public["precision_bounds"]["labeled_only_upper_bound"], 0.0)

    def test_fingerprint_duplicate_preserves_all_provenance_and_counts_one_tp(self):
        finding = _finding(self.gt["findings"][0], submitted_by="agent_001")
        duplicate = dict(finding)
        duplicate["submitted_by"] = "agent_002"
        duplicate["evidence_refs"] = ["evt_00000011"]
        result = evaluate_findings([finding, duplicate], self.gt)

        self.assertEqual(result["public"]["positive_recall"]["true_positives"], 1)
        self.assertEqual(result["public"]["duplicates"]["count"], 1)
        groups = result["private"]["duplicate_provenance"]
        self.assertEqual(len(groups), 1)
        self.assertEqual(next(iter(groups.values()))[1]["submitted_by"], "agent_002")

    def test_agent_reproduction_claim_is_not_the_verification_source(self):
        finding = _finding(self.gt["findings"][0])
        finding["reproduction"] = {"attempted": True, "successful": True, "artifact_ref": "scratch/poc.txt"}
        result = evaluate_findings([finding], self.gt)

        self.assertEqual(result["public"]["agent_reproduction_claims"]["successful"], 1)
        self.assertEqual(result["public"]["evaluator_verified_findings"], 1)
        self.assertIn("oracle", result["private"])


if __name__ == "__main__":
    unittest.main()
