from __future__ import annotations

import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.check_hidden_graph_pilot_a_nodes import assess, freeze_nodes
from scripts.hidden_opportunity_graph import PRIVATE_GRAPH_DIR, stamp_draft, validate_graph
from scripts.prepare_hidden_graph_pilot_a import verify as verify_packets


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in records), encoding="utf-8")


class PilotANodeBoundaryQCTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.graph = Path(self.temporary.name) / "graph-v1"
        shutil.copytree(
            PRIVATE_GRAPH_DIR,
            self.graph,
            ignore=shutil.ignore_patterns("reviews", "nodes_frozen.jsonl", "node_boundary_qc.json"),
        )
        for name in ("nodes.jsonl", "edges.jsonl", "node_reviews.jsonl", "edge_reviews.jsonl", "adjudications.jsonl"):
            (self.graph / name).write_bytes(b"")
        manifest_path = self.graph / "graph_manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["adjudication_status"] = "draft"
        manifest["adjudication_date"] = None
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
        stamp_draft(self.graph)
        self.pilot = self.graph / "pilot_a"
        self.reviews = self.pilot / "reviews"
        self.reviews.mkdir()
        self.template = [json.loads(line) for line in (self.pilot / "review_form_template.jsonl").read_text().splitlines()]

    def _review(self, reviewer_id: str, decisions: list[str] | None = None) -> list[dict]:
        rows = copy.deepcopy(self.template)
        for index, row in enumerate(rows):
            row["reviewer_id"] = reviewer_id
            row["decision"] = decisions[index] if decisions else "split"
            row["counterfactual"] = "The two security claims may have different truth values."
            row["rationale"] = "The two source chains need independent ownership or guard reasoning."
        return rows

    def _write_two_reviews(self, b_decisions: list[str] | None = None) -> None:
        _write_jsonl(self.reviews / "reviewer_a.jsonl", self._review("reviewer_a"))
        _write_jsonl(self.reviews / "reviewer_b.jsonl", self._review("reviewer_b", b_decisions))

    def test_packets_verify_and_missing_reviews_are_pending(self) -> None:
        self.assertEqual(verify_packets(self.pilot)["candidate_count"], 6)
        packets = [json.loads(line) for line in (self.pilot / "candidate_packets.jsonl").read_text().splitlines()]
        near_miss = next(item for item in packets if item["candidate_id"] == "NM04_scoped_credential_read")
        self.assertEqual(near_miss["evidence"][0]["line"], 132)
        self.assertEqual(next(ref["line"] for ref in near_miss["evidence"] if ref["role"] == "narrow_safe_contrast"), 132)
        r06 = next(item for item in packets if item["candidate_id"] == "R06_assistant_delete_credential_lookup_scope")
        import_refs = [ref for ref in r06["evidence"] if ref["path"].startswith("packages/server/src/services/export-import/")]
        self.assertEqual({ref["line"] for ref in import_refs}, {609, 696, 697, 775})
        report, _ = assess(self.pilot)
        self.assertEqual(report["status"], "pending_independent_reviews")

    def test_two_review_gate_can_freeze_six_nodes_without_edges(self) -> None:
        self._write_two_reviews()
        report, _ = assess(self.pilot)
        self.assertEqual(report["status"], "ready_to_freeze_six_nodes")
        self.assertEqual(report["node_pair_agreement_count"], 15)
        frozen = freeze_nodes(self.pilot)
        self.assertEqual(frozen["directed_pair_denominator"], 30)
        self.assertEqual(len((self.pilot / "nodes_frozen.jsonl").read_text().splitlines()), 6)
        self.assertEqual(validate_graph(self.graph)["node_count"], 0)

    def test_disagreement_requires_third_review_and_subthreshold_gate_fails(self) -> None:
        decisions = ["merge", "merge"] + ["split"] * 13
        self._write_two_reviews(decisions)
        report, _ = assess(self.pilot)
        self.assertEqual(report["status"], "pending_third_adjudication")
        third = []
        for row in self.template[:2]:
            third.append({
                "adjudicator_id": "third_reviewer",
                "candidate_a": row["candidate_a"],
                "candidate_b": row["candidate_b"],
                "decision": "split",
                "counterfactual": "Each claim can change independently.",
                "rationale": "The source chains have distinct security questions.",
                "evidence_refs": row["evidence_refs"],
            })
        _write_jsonl(self.reviews / "adjudicator.jsonl", third)
        report, _ = assess(self.pilot)
        self.assertEqual(report["status"], "qc_failed_reblind_required")
        self.assertEqual(report["node_pair_agreement_count"], 13)
        self.assertFalse((self.pilot / "nodes_frozen.jsonl").exists())

    def test_one_adjudicated_disagreement_meets_gate(self) -> None:
        self._write_two_reviews(["merge"] + ["split"] * 14)
        row = self.template[0]
        _write_jsonl(self.reviews / "adjudicator.jsonl", [{
            "adjudicator_id": "third_reviewer",
            "candidate_a": row["candidate_a"],
            "candidate_b": row["candidate_b"],
            "decision": "split",
            "counterfactual": "Either claim can change without deciding the other.",
            "rationale": "Distinct source chains support distinct conclusions.",
            "evidence_refs": row["evidence_refs"],
        }])
        report, _ = assess(self.pilot)
        self.assertEqual(report["status"], "ready_to_freeze_six_nodes")
        self.assertEqual(report["node_pair_agreement_count"], 14)
        self.assertEqual(report["adjudicated_pair_count"], 1)

    def test_agreed_merge_requires_versioned_pilot_revision(self) -> None:
        decisions = ["merge"] + ["split"] * 14
        _write_jsonl(self.reviews / "reviewer_a.jsonl", self._review("reviewer_a", decisions))
        _write_jsonl(self.reviews / "reviewer_b.jsonl", self._review("reviewer_b", decisions))
        report, _ = assess(self.pilot)
        self.assertEqual(report["status"], "pilot_revision_required")
        self.assertIsNone(report["directed_pair_denominator"])


if __name__ == "__main__":
    unittest.main()
