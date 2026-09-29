from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.check_hidden_graph_pilot_b_boundaries as boundary_qc
import scripts.check_hidden_graph_pilot_b_edges as edge_qc
import scripts.prepare_hidden_graph_pilot_b_boundaries as boundaries
import scripts.prepare_hidden_graph_pilot_b_edges as edges
from scripts.hidden_opportunity_graph import GraphValidationError, PRIVATE_GRAPH_DIR, PILOT_B_GRAPH_DIR, stamp_draft, validate_graph
from scripts.prepare_hidden_graph_pilot_b_candidates import PREP_DIR, STRATA


class PilotBBoundaryPacketTest(unittest.TestCase):
    @staticmethod
    def _draft_validation(path: Path, **_: object) -> dict[str, str]:
        return {"status": "valid_frozen" if path == PRIVATE_GRAPH_DIR else "valid_draft"}

    def test_selection_uses_earliest_candidate_for_each_distinct_mechanism(self) -> None:
        bundle = json.loads((PREP_DIR / "reviewer_bundle.json").read_text(encoding="utf-8"))
        ids = ["NM01_scoped_role_read", "R01_enterprise_active_org_binding", "R07_sso_invited_token_proof"]
        candidates = {item["candidate_id"]: item for item in bundle["candidates"] if item["candidate_id"] in ids}
        final = {identifier: {"invariant": identifier} for identifier in ids}
        role = {"candidate_id": ids[0], "distinct_mechanism": "organization_object_guard",
                "selection_rationale": "A bounded organization object guard.", "potential_artifact": "The scoped Role guard."}
        workspace = {**role, "candidate_id": ids[1], "potential_artifact": "The Workspace guard."}
        sso = {"candidate_id": ids[2], "distinct_mechanism": "sso_identity_proof",
               "selection_rationale": "A distinct SSO identity check.", "potential_artifact": "The invited-token check."}
        report = {"admitted_candidate_ids": ids}
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            path = directory / "selection_spec.json"
            spec = {"selection_version": "pilot-b-selection-v1", "selected": [workspace, sso],
                    "excluded_admitted": [{"candidate_id": ids[0], "distinct_mechanism": "organization_object_guard",
                                           "reason": "Same guard mechanism."}],
                    "empty_strata": [stratum for stratum in STRATA if stratum != "enterprise_identity_route_guard"]}
            with patch.object(boundaries, "QUALIFICATION_DIR", directory):
                path.write_text(json.dumps(spec), encoding="utf-8")
                with self.assertRaises(GraphValidationError):
                    boundaries._selection(report, candidates, final)
                spec["selected"] = [role, sso]
                spec["excluded_admitted"][0]["candidate_id"] = ids[1]
                path.write_text(json.dumps(spec), encoding="utf-8")
                self.assertEqual([item["candidate_id"] for item in boundaries._selection(report, candidates, final)],
                                 [ids[0], ids[2]])

    def test_one_qualified_file_front_adds_all_six_cross_boundaries(self) -> None:
        bundle = json.loads((PREP_DIR / "reviewer_bundle.json").read_text(encoding="utf-8"))
        candidate = next(item for item in bundle["candidates"]
                         if item["candidate_id"] == "U_FILE_01_stream_uploaded_file_object_scope")
        identifier = candidate["candidate_id"]
        final_review = {
            "security_question": candidate["question_prompt"],
            "invariant": "File read must be scoped to the entitled chatflow and stored object.",
            "evidence_refs": candidate["chain_hints"],
        }
        report = {
            "status": "ready_for_boundary_and_selection_qc",
            "admitted_candidate_ids": [identifier],
            "packet_manifest_sha256": "candidate-packet-fixture",
            "review_file_sha256": {"reviewer_a": "review-a-fixture", "reviewer_b": "review-b-fixture"},
            "adjudication_file_sha256": None,
        }
        with tempfile.TemporaryDirectory() as temporary:
            prep = Path(temporary)
            selection = {
                "selection_version": "pilot-b-selection-v1",
                "selected": [{
                    "candidate_id": identifier,
                    "distinct_mechanism": "uploaded_file_object_scope",
                    "selection_rationale": "An independently bounded read and object guard question.",
                    "potential_artifact": "The exact read lookup and caller scope for one uploaded object.",
                }],
                "excluded_admitted": [],
                "empty_strata": [stratum for stratum in STRATA if stratum != "file_storage_boundary"],
            }
            (prep / "selection_spec.json").write_text(json.dumps(selection), encoding="utf-8")
            with patch.object(boundaries, "QUALIFICATION_DIR", prep), patch.object(
                boundaries, "assess_candidates", return_value=(
                    report, {"candidates": {identifier: candidate}, "final": {identifier: final_review}}
                )
            ), patch.object(boundaries, "validate_graph", side_effect=self._draft_validation):
                payloads = boundaries.render()
        rows = [json.loads(line) for line in payloads["selected_nodes_proposed.jsonl"].splitlines()]
        packet = json.loads(payloads["boundary_reviewer_bundle.json"])
        self.assertEqual([row["node_id"] for row in rows], ["F007"])
        self.assertEqual({(row["candidate_a"], row["candidate_b"]) for row in packet["unordered_pairs"]},
                         {(f"F{i:03d}", "F007") for i in range(1, 7)})
        self.assertEqual(len(payloads["boundary_review_form_template.jsonl"].splitlines()), 6)

    def test_six_cross_boundary_reviews_require_complete_independent_agreement(self) -> None:
        pilot_a = [json.loads(line) for line in (PRIVATE_GRAPH_DIR / "nodes.jsonl").read_text().splitlines()]
        source = json.loads((PREP_DIR / "reviewer_bundle.json").read_text())
        candidate = next(item for item in source["candidates"]
                         if item["candidate_id"] == "U_FILE_01_stream_uploaded_file_object_scope")
        new = {"node_id": "F007", "security_question": candidate["question_prompt"],
               "evidence_refs": candidate["chain_hints"]}
        pairs = [{"candidate_a": node["node_id"], "candidate_b": "F007",
                  "security_question_a": node["security_question"],
                  "security_question_b": new["security_question"]} for node in pilot_a]
        bundle = {"selected_pilot_b_nodes_proposed": [new], "pilot_a_nodes": pilot_a,
                  "unordered_pairs": pairs, "pilot_a_graph_manifest_sha256": "pilot-a-fixture",
                  "selection_spec_sha256": "selection-fixture"}

        def review(reviewer_id: str) -> list[dict]:
            rows = []
            for node, pair in zip(pilot_a, pairs):
                refs = []
                for role, anchor in (("candidate_a", node["evidence_refs"][0]),
                                     ("candidate_b", new["evidence_refs"][0])):
                    refs.append({**{key: anchor[key] for key in
                                     ("path", "line", "symbol", "excerpt", "excerpt_sha256")}, "role": role})
                rows.append({"reviewer_id": reviewer_id, **pair, "decision": "split",
                             "counterfactual": "The two security questions may have different truth values.",
                             "rationale": "The file object read and the existing node need distinct source chains.",
                             "evidence_refs": refs})
            return rows

        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "boundary_reviewer_bundle.json").write_text(json.dumps(bundle), encoding="utf-8")
            reviews = directory / "boundary_reviews"
            reviews.mkdir()
            for name, rows in (("reviewer_a", review("reviewer_a")),
                               ("reviewer_b", review("reviewer_b"))):
                (reviews / f"{name}.jsonl").write_text(
                    "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            with patch.object(boundary_qc, "verify_packet", return_value={"boundary_packet_manifest_sha256": "packet-fixture"}):
                report, _ = boundary_qc.assess(directory)
                self.assertEqual(report["status"], "ready_to_freeze_pilot_b_nodes")
                self.assertEqual(report["total_directed_pair_denominator"], 42)
                rows_b = review("reviewer_b")
                rows_b[0]["decision"] = "merge"
                (reviews / "reviewer_b.jsonl").write_text(
                    "".join(json.dumps(row) + "\n" for row in rows_b), encoding="utf-8")
                pending, _ = boundary_qc.assess(directory)
                self.assertEqual(pending["status"], "pending_third_boundary_adjudication")
                self.assertEqual(pending["needs_adjudication"], [["F001", "F007"]])

    def test_new_edge_universe_includes_both_cross_directions(self) -> None:
        pilot_a = [json.loads(line) for line in (PRIVATE_GRAPH_DIR / "nodes.jsonl").read_text().splitlines()]
        source = json.loads((PREP_DIR / "reviewer_bundle.json").read_text())
        candidate = next(item for item in source["candidates"]
                         if item["candidate_id"] == "U_FILE_01_stream_uploaded_file_object_scope")
        new = {"node_id": "F007", "security_question": candidate["question_prompt"],
               "code_scope": list(dict.fromkeys(ref["path"] for ref in candidate["chain_hints"])),
               "evidence_refs": candidate["chain_hints"],
               "potential_artifact": "Bounded result about an uploaded file object read."}
        nodes_bytes = b"".join((json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode()
                               for row in [*pilot_a, new])
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "nodes_frozen.jsonl").write_bytes(nodes_bytes)
            (directory / "node_boundary_qc.json").write_text(json.dumps({
                "status": "ready_to_freeze_pilot_b_nodes", "selected_node_count": 1,
                "nodes_frozen_sha256": hashlib.sha256(nodes_bytes).hexdigest(),
            }), encoding="utf-8")
            with patch.object(edges, "BOUNDARY_DIR", directory), patch.object(
                edges, "validate_graph", side_effect=self._draft_validation
            ):
                payloads = edges.render()
        packet = json.loads(payloads["edge_reviewer_bundle.json"])
        pairs = {(row["source_node"], row["target_node"])
                 for row in packet["directed_pairs_to_review"]}
        self.assertEqual(len(pairs), 12)
        self.assertEqual(pairs, {(f"F{i:03d}", "F007") for i in range(1, 7)}
                         | {("F007", f"F{i:03d}") for i in range(1, 7)})
        self.assertEqual(len(payloads["edge_review_form_template.jsonl"].splitlines()), 12)

    def test_new_edge_binary_gate_rejects_two_disagreements_in_twelve(self) -> None:
        pilot_a = [json.loads(line) for line in (PRIVATE_GRAPH_DIR / "nodes.jsonl").read_text().splitlines()]
        new = {"node_id": "F007"}
        pairs = [(old["node_id"], "F007") for old in pilot_a]
        pairs += [("F007", old["node_id"]) for old in pilot_a]
        bundle = {"nodes": [*pilot_a, new],
                  "directed_pairs_to_review": [{"source_node": a, "target_node": b} for a, b in pairs],
                  "input_lock_sha256": "input-fixture", "pilot_a_graph_manifest_sha256": "pilot-a-fixture",
                  "node_boundary_qc_sha256": "node-fixture"}

        def review(identity: str) -> list[dict]:
            return [{"reviewer_id": identity, "source_node": a, "target_node": b,
                     "opportunity_type": "none", "mechanisms": [], "source_artifact": "",
                     "target_claim": "", "expected_effect": [], "bounded_check": "", "evidence": [],
                     "rationale": "Synthetic fixture: no concrete information path has been established.",
                     "confidence": "high", "uncertainty_note": None} for a, b in pairs]

        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "edge_reviewer_bundle.json").write_text(json.dumps(bundle), encoding="utf-8")
            reviews = directory / "reviews"
            reviews.mkdir()
            rows_a, rows_b = review("edge_a"), review("edge_b")
            for name, rows in (("reviewer_a", rows_a), ("reviewer_b", rows_b)):
                (reviews / f"{name}.jsonl").write_text(
                    "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            with patch.object(edge_qc, "EDGE_DIR", directory), patch.object(
                edge_qc, "verify_packet", return_value={
                    "edge_packet_manifest_sha256": "packet-fixture",
                    "edge_reviewer_bundle_sha256": "bundle-fixture",
                }
            ), patch.object(edge_qc, "validate_graph", return_value={"status": "valid_draft"}):
                ready, _ = edge_qc.assess()
                self.assertEqual(ready["status"], "ready_to_freeze_pilot_b_edges")
                self.assertEqual(ready["binary_agreement_count"], 12)
                for index in (0, 1):
                    row = rows_b[index]
                    a = pilot_a[index]["evidence_refs"][0]
                    source = {key: a[key] for key in ("path", "line", "symbol", "excerpt", "excerpt_sha256")}
                    target = json.loads((PREP_DIR / "reviewer_bundle.json").read_text())["candidates"]
                    file_anchor = next(item["anchor"] for item in target
                                       if item["candidate_id"] == "U_FILE_01_stream_uploaded_file_object_scope")
                    row.update({"opportunity_type": "actionable cross-check",
                                "mechanisms": ["synthetic comparison"],
                                "source_artifact": "A specific source guard result.",
                                "target_claim": "The file object guard applies.",
                                "expected_effect": ["narrow"],
                                "bounded_check": "Compare both guards and interpret positive and negative outcomes.",
                                "evidence": [{**source, "role": "source"},
                                             {**file_anchor, "role": "target"}]})
                (reviews / "reviewer_b.jsonl").write_text(
                    "".join(json.dumps(row) + "\n" for row in rows_b), encoding="utf-8")
                pending, _ = edge_qc.assess()
                self.assertEqual(pending["status"], "pending_third_edge_adjudication")
                third = [{**{key: value for key, value in rows_a[index].items() if key != "reviewer_id"},
                          "adjudicator_id": "edge_third"} for index in (0, 1)]
                (reviews / "adjudicator.jsonl").write_text(
                    "".join(json.dumps(row) + "\n" for row in third), encoding="utf-8")
                failed, _ = edge_qc.assess()
                self.assertEqual(failed["status"], "qc_failed_reblind_required")
                self.assertEqual(failed["binary_agreement_count"], 10)

    def test_isolated_seven_node_extension_freezes_full_matrix(self) -> None:
        pilot_a = [json.loads(line) for line in (PRIVATE_GRAPH_DIR / "nodes.jsonl").read_text().splitlines()]
        source = json.loads((PREP_DIR / "reviewer_bundle.json").read_text())
        candidate = next(item for item in source["candidates"]
                         if item["candidate_id"] == "U_FILE_01_stream_uploaded_file_object_scope")
        refs = candidate["chain_hints"]
        new = {
            "node_id": "F007", "security_question": candidate["question_prompt"],
            "code_scope": list(dict.fromkeys(ref["path"] for ref in refs)),
            "invariant": "File object reads must be scoped to the entitled caller.",
            "boundary_rationale": "The file object read has a distinct source chain and security question.",
            "potential_artifact": "The exact object lookup and storage path for this read.",
            "evidence_refs": refs, "truth_status": "admitted_unscored", "gt_root_ids": [],
            "near_miss_ids": [], "adjudication_status": "adjudicated",
        }
        nodes_bytes = b"".join((json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode()
                               for row in [*pilot_a, new])
        pairs = [(a["node_id"], "F007") for a in pilot_a]
        pairs += [("F007", a["node_id"]) for a in pilot_a]
        bundle = {
            "nodes": [*pilot_a, new],
            "directed_pairs_to_review": [{"source_node": a, "target_node": b} for a, b in pairs],
            "input_lock_sha256": "input-fixture",
            "pilot_a_graph_manifest_sha256": hashlib.sha256(
                (PRIVATE_GRAPH_DIR / "graph_manifest.json").read_bytes()).hexdigest(),
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            graph = root / "graph-v2"
            shutil.copytree(PILOT_B_GRAPH_DIR, graph)
            for name in ("nodes.jsonl", "edges.jsonl", "edge_reviews.jsonl", "adjudications.jsonl"):
                (graph / name).write_bytes(b"")
            (graph / "node_reviews.jsonl").write_bytes((PRIVATE_GRAPH_DIR / "node_reviews.jsonl").read_bytes())
            graph_manifest = json.loads((graph / "graph_manifest.json").read_text())
            graph_manifest["adjudication_status"] = "draft"
            graph_manifest["adjudication_date"] = None
            (graph / "graph_manifest.json").write_text(
                json.dumps(graph_manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
            )
            stamp_draft(graph)
            node_dir = root / "boundary"
            node_dir.mkdir()
            (node_dir / "nodes_frozen.jsonl").write_bytes(nodes_bytes)
            (node_dir / "node_boundary_qc.json").write_text("{}\n", encoding="utf-8")
            bundle["node_boundary_qc_sha256"] = hashlib.sha256(
                (node_dir / "node_boundary_qc.json").read_bytes()).hexdigest()
            review_dir = root / "edge_reviews"
            review_dir.mkdir()
            bundle_bytes = (json.dumps(bundle) + "\n").encode()
            (review_dir / "edge_reviewer_bundle.json").write_bytes(bundle_bytes)
            (review_dir / "edge_packet_manifest.json").write_text("{}\n", encoding="utf-8")
            reviewer_rows = []
            for identity in ("extension_a", "extension_b"):
                reviewer_rows.append([{
                    "reviewer_id": identity, "source_node": a, "target_node": b,
                    "opportunity_type": "none", "mechanisms": [], "source_artifact": "",
                    "target_claim": "", "expected_effect": [], "bounded_check": "", "evidence": [],
                    "rationale": "Synthetic freeze fixture has no established information path.",
                    "confidence": "high", "uncertainty_note": None,
                } for a, b in pairs])
            reviews = review_dir / "reviews"
            reviews.mkdir()
            for name, rows in zip(("reviewer_a", "reviewer_b"), reviewer_rows):
                (reviews / f"{name}.jsonl").write_text(
                    "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            packet = {
                "edge_packet_manifest_sha256": hashlib.sha256(
                    (review_dir / "edge_packet_manifest.json").read_bytes()).hexdigest(),
                "edge_reviewer_bundle_sha256": hashlib.sha256(bundle_bytes).hexdigest(),
            }
            with patch.object(edge_qc, "PILOT_B_GRAPH_DIR", graph), patch.object(
                edge_qc, "BOUNDARY_DIR", node_dir
            ), patch.object(edge_qc, "EDGE_DIR", review_dir), patch.object(
                edge_qc, "verify_packet", return_value=packet
            ):
                result = edge_qc.freeze_edges()
                self.assertEqual(result["status"], "frozen")
                self.assertEqual(result["total_directed_pair_count"], 42)
                self.assertEqual(validate_graph(graph)["status"], "valid_frozen")
                old = {(row["source_node"], row["target_node"]): row
                       for row in [json.loads(line) for line in (PRIVATE_GRAPH_DIR / "edges.jsonl").read_text().splitlines()]}
                final = {(row["source_node"], row["target_node"]): row
                         for row in [json.loads(line) for line in (graph / "edges.jsonl").read_text().splitlines()]}
                self.assertEqual(len(final), 42)
                self.assertTrue(all(final[p]["opportunity_type"] == old[p]["opportunity_type"] for p in old))


if __name__ == "__main__":
    unittest.main()
