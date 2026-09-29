from __future__ import annotations

import copy
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.check_hidden_graph_pilot_a_edges as edge_qc
from scripts.hidden_opportunity_graph import PRIVATE_GRAPH_DIR, GraphValidationError, stamp_draft, validate_graph


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in records), encoding="utf-8")


class PilotAEdgeQCTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.graph = Path(self.temporary.name) / "graph-v1"
        shutil.copytree(PRIVATE_GRAPH_DIR, self.graph, ignore=shutil.ignore_patterns("reviews", "edge_qc.json"))
        for name in ("nodes.jsonl", "edges.jsonl", "edge_reviews.jsonl", "adjudications.jsonl"):
            (self.graph / name).write_bytes(b"")
        manifest_path = self.graph / "graph_manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["adjudication_status"] = "draft"
        manifest["adjudication_date"] = None
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
        stamp_draft(self.graph)
        self.edge_dir = self.graph / "pilot_a" / "edges"
        self.reviews = self.edge_dir / "reviews"
        self.reviews.mkdir()
        self.template = [json.loads(line) for line in (self.edge_dir / "edge_review_form_template.jsonl").read_text().splitlines()]
        self.bundle = json.loads((self.edge_dir / "edge_reviewer_bundle.json").read_text())
        self.nodes = {node["node_id"]: node for node in self.bundle["nodes"]}
        self.patch_root = patch.object(edge_qc, "PRIVATE_GRAPH_DIR", self.graph)
        self.patch_root.start()
        self.addCleanup(self.patch_root.stop)
        packet = {
            "edge_packet_manifest_sha256": hashlib.sha256((self.edge_dir / "edge_packet_manifest.json").read_bytes()).hexdigest(),
            "edge_reviewer_bundle_sha256": hashlib.sha256((self.edge_dir / "edge_reviewer_bundle.json").read_bytes()).hexdigest(),
        }
        self.patch_verify = patch.object(edge_qc, "verify_edge_packet", return_value=packet)
        self.patch_verify.start()
        self.addCleanup(self.patch_verify.stop)

    def _review(self, reviewer_id: str, actionable_indices: set[int] | None = None) -> list[dict]:
        rows = copy.deepcopy(self.template)
        for index, row in enumerate(rows):
            row["reviewer_id"] = reviewer_id
            row["opportunity_type"] = "none"
            row["rationale"] = "No concrete shared control or information value was established in this synthetic fixture."
            row["confidence"] = "high"
            if actionable_indices and index in actionable_indices:
                source = self.nodes[row["source_node"]]["evidence_refs"][0]
                target = self.nodes[row["target_node"]]["evidence_refs"][0]
                row.update({
                    "opportunity_type": "actionable cross-check",
                    "mechanisms": ["synthetic differential"],
                    "source_artifact": "Source evidence about the guard",
                    "target_claim": "Target guard applies",
                    "expected_effect": ["validate"],
                    "bounded_check": "Compare source and target guards",
                    "evidence": [
                        {**{key: source[key] for key in ("path", "line", "symbol", "excerpt", "excerpt_sha256")}, "role": "source"},
                        {**{key: target[key] for key in ("path", "line", "symbol", "excerpt", "excerpt_sha256")}, "role": "target"},
                    ],
                    "rationale": "Synthetic positive and negative outcomes distinguish the target claim.",
                })
        return rows

    def test_full_matrix_can_be_frozen_after_unanimous_qc(self) -> None:
        _write_jsonl(self.reviews / "reviewer_a.jsonl", self._review("edge_a"))
        _write_jsonl(self.reviews / "reviewer_b.jsonl", self._review("edge_b"))
        report, _ = edge_qc.assess(self.edge_dir)
        self.assertEqual(report["binary_agreement_count"], 30)
        self.assertEqual(report["status"], "ready_to_freeze_pilot_a_edges")
        frozen = edge_qc.freeze_edges(self.edge_dir)
        self.assertEqual(frozen["status"], "frozen")
        self.assertEqual(validate_graph(self.graph)["node_count"], 6)
        self.assertEqual(validate_graph(self.graph)["directed_pair_count"], 30)
        self.assertEqual(len((self.graph / "edge_reviews.jsonl").read_text().splitlines()), 60)

    def test_below_ninety_percent_requires_reblind_even_after_third_review(self) -> None:
        _write_jsonl(self.reviews / "reviewer_a.jsonl", self._review("edge_a"))
        b = self._review("edge_b", {0, 1, 2, 3})
        _write_jsonl(self.reviews / "reviewer_b.jsonl", b)
        pending, _ = edge_qc.assess(self.edge_dir)
        self.assertEqual(pending["status"], "pending_third_edge_adjudication")
        third = [
            {**{key: value for key, value in self._review("third")[index].items() if key != "reviewer_id"},
             "adjudicator_id": "third"}
            for index in range(4)
        ]
        _write_jsonl(self.reviews / "adjudicator.jsonl", third)
        report, _ = edge_qc.assess(self.edge_dir)
        self.assertEqual(report["binary_agreement_count"], 26)
        self.assertEqual(report["status"], "qc_failed_reblind_required")
        with self.assertRaises(GraphValidationError):
            edge_qc.freeze_edges(self.edge_dir)

    def test_three_positive_disagreements_can_pass_after_third_review(self) -> None:
        _write_jsonl(self.reviews / "reviewer_a.jsonl", self._review("edge_a"))
        _write_jsonl(self.reviews / "reviewer_b.jsonl", self._review("edge_b", {0, 1, 2}))
        third_rows = self._review("third")
        _write_jsonl(self.reviews / "adjudicator.jsonl", [
            {**{key: value for key, value in third_rows[index].items() if key != "reviewer_id"},
             "adjudicator_id": "third"}
            for index in range(3)
        ])
        report, _ = edge_qc.assess(self.edge_dir)
        self.assertEqual(report["binary_agreement_count"], 27)
        self.assertEqual(report["adjudicated_disagreement_count"], 3)
        self.assertEqual(report["status"], "ready_to_freeze_pilot_a_edges")


if __name__ == "__main__":
    unittest.main()
