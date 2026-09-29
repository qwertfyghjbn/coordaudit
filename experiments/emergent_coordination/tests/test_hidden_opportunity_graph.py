from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.hidden_opportunity_graph import (
    CASE_ID,
    GRAPH_VERSION,
    PILOT_B_GRAPH_VERSION,
    PILOT_B_PREP_DIR,
    GraphValidationError,
    initialize_graph,
    stamp_draft,
    validate_graph,
)
from experiments.emergent_coordination.harness.cases import load_case


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in records), encoding="utf-8")


class HiddenOpportunityGraphTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.case = load_case(CASE_ID)
        cls.gt = json.loads(cls.case.ground_truth_path.read_text(encoding="utf-8"))

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name) / "private_graph"
        initialize_graph(self.directory)

    def _evidence(self, root_id: str, role: str | None = None) -> dict:
        root = next(item for item in self.gt["roots"] if item["id"] == root_id)
        anchor = root["anchors"][0]
        source = (self.case.target_root / anchor["file"]).read_text(encoding="utf-8")
        excerpt = anchor["excerpt"]
        offset = source.index(excerpt)
        item = {
            "path": anchor["file"],
            "line": source.count("\n", 0, offset) + 1,
            "symbol": anchor["function"],
            "excerpt": excerpt,
            "excerpt_sha256": hashlib.sha256(excerpt.encode()).hexdigest(),
        }
        if role:
            item["role"] = role
        return item

    def _node(self, node_id: str, root_id: str) -> dict:
        evidence = self._evidence(root_id)
        return {
            "node_id": node_id,
            "security_question": f"Is the object scoped in {root_id}?",
            "code_scope": [evidence["path"]],
            "invariant": "Credential access must respect the workspace boundary.",
            "boundary_rationale": "Candidate has an independently decidable source-to-query chain.",
            "potential_artifact": "A bounded conclusion about workspace scoping.",
            "evidence_refs": [evidence],
            "truth_status": "scored_positive",
            "gt_root_ids": [root_id],
            "adjudication_status": "proposed",
        }

    @staticmethod
    def _none_edge(source: str, target: str) -> dict:
        return {
            "edge_id": f"{GRAPH_VERSION}:{source}:{target}",
            "source_node": source,
            "target_node": target,
            "direction": "source_to_target",
            "opportunity_type": "none",
            "mechanisms": [],
            "source_artifact": "",
            "target_claim": "",
            "expected_effect": [],
            "bounded_check": "",
            "evidence": [],
            "rationale": "Temporary schema fixture; no relation adjudicated.",
            "confidence": "low",
            "adjudication_status": "proposed",
            "reviewer_ids": [],
            "uncertainty_note": None,
        }

    def _write_pair(self, edges: list[dict] | None = None) -> None:
        nodes = [
            self._node("F001", "R04_generic_credential_lookup_scope"),
            self._node("F002", "R05_openai_assistant_credential_lookup_scope"),
        ]
        _write_jsonl(self.directory / "nodes.jsonl", nodes)
        _write_jsonl(self.directory / "edges.jsonl", edges if edges is not None else [
            self._none_edge("F001", "F002"), self._none_edge("F002", "F001")
        ])

    def test_init_locks_real_inputs_and_creates_valid_private_draft(self) -> None:
        result = validate_graph(self.directory)
        lock = json.loads((self.directory / "input_lock.json").read_text(encoding="utf-8"))
        self.assertEqual(result["status"], "valid_draft")
        self.assertEqual(result["node_count"], 0)
        self.assertEqual(lock["target_sha256"], self.case.manifest["digests"]["target_tree_sha256"])
        self.assertEqual(lock["gt_generation"], self.gt["version"])
        self.assertEqual(self.directory.stat().st_mode & 0o777, 0o700)

    def test_complete_directed_matrix_is_accepted(self) -> None:
        self._write_pair()
        result = stamp_draft(self.directory)
        self.assertEqual(result["directed_pair_count"], 2)
        self.assertEqual(result["expected_directed_pair_count"], 2)

    def test_missing_reverse_and_duplicate_pair_are_rejected(self) -> None:
        edge = self._none_edge("F001", "F002")
        self._write_pair([edge])
        with self.assertRaisesRegex(GraphValidationError, "directed pair matrix"):
            stamp_draft(self.directory)
        self._write_pair([edge, copy.deepcopy(edge)])
        with self.assertRaisesRegex(GraphValidationError, "directed pair matrix"):
            stamp_draft(self.directory)

    def test_bad_evidence_line_and_runtime_field_are_rejected(self) -> None:
        self._write_pair()
        nodes = [json.loads(line) for line in (self.directory / "nodes.jsonl").read_text().splitlines()]
        nodes[0]["evidence_refs"][0]["line"] += 1
        _write_jsonl(self.directory / "nodes.jsonl", nodes)
        with self.assertRaisesRegex(GraphValidationError, "excerpt not found"):
            stamp_draft(self.directory)
        nodes[0]["evidence_refs"][0]["line"] -= 1
        nodes[0]["runtime_tool"] = "read_file"
        _write_jsonl(self.directory / "nodes.jsonl", nodes)
        with self.assertRaisesRegex(GraphValidationError, "unexpected fields"):
            stamp_draft(self.directory)

    def test_actionable_edge_requires_both_code_evidence_roles(self) -> None:
        edge = self._none_edge("F001", "F002")
        edge.update({
            "opportunity_type": "actionable cross-check",
            "source_artifact": "A minimal conclusion about a lookup predicate.",
            "target_claim": "B's workspace-scoping claim.",
            "expected_effect": ["narrow"],
            "bounded_check": "Compare the two query guards and interpret both outcomes.",
            "evidence": [self._evidence("R04_generic_credential_lookup_scope", "source")],
        })
        self._write_pair([edge, self._none_edge("F002", "F001")])
        with self.assertRaisesRegex(GraphValidationError, "missing A/B evidence"):
            stamp_draft(self.directory)
        edge["evidence"].append(self._evidence("R05_openai_assistant_credential_lookup_scope", "target"))
        self._write_pair([edge, self._none_edge("F002", "F001")])
        self.assertEqual(stamp_draft(self.directory)["directed_pair_count"], 2)

    def test_changed_input_lock_and_manifest_hash_are_rejected(self) -> None:
        self._write_pair()
        stamp_draft(self.directory)
        (self.directory / "edges.jsonl").write_text("", encoding="utf-8")
        with self.assertRaisesRegex(GraphValidationError, "edges_sha256 mismatch"):
            validate_graph(self.directory)
        lock_path = self.directory / "input_lock.json"
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        lock["target_sha256"] = "0" * 64
        lock_path.write_text(json.dumps(lock), encoding="utf-8")
        with self.assertRaisesRegex(GraphValidationError, "input lock no longer matches"):
            validate_graph(self.directory)

    def test_pilot_b_version_locks_candidate_packet_and_preserves_pilot_a(self) -> None:
        second = Path(self.temporary.name) / PILOT_B_GRAPH_VERSION
        initialize_graph(second)
        self.assertEqual(validate_graph(second)["status"], "valid_draft")
        lock_path = second / "input_lock.json"
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        self.assertEqual(lock["graph_version"], PILOT_B_GRAPH_VERSION)
        self.assertEqual(lock["pilot_scope"]["pilot_b_candidate_packet_sha256"],
                         hashlib.sha256((PILOT_B_PREP_DIR / "packet_manifest.json").read_bytes()).hexdigest())
        lock["pilot_scope"]["pilot_b_candidate_packet_sha256"] = "0" * 64
        lock_path.write_text(json.dumps(lock), encoding="utf-8")
        with self.assertRaisesRegex(GraphValidationError, "input lock no longer matches"):
            validate_graph(second)
        self.assertEqual(validate_graph(self.directory)["status"], "valid_draft")


if __name__ == "__main__":
    unittest.main()
