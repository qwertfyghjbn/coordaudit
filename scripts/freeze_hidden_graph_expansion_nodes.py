#!/usr/bin/env python3
"""Freeze the independently reviewed expansion node set without creating edges."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

from experiments.emergent_coordination.harness.cases import load_case
from scripts.check_hidden_graph_expansion_boundary import assess as assess_boundary, load_review
from scripts.check_hidden_graph_expansion_nodes import assess as assess_qualification
from scripts.hidden_opportunity_graph import CASE_ID, GraphValidationError, _read_json, _read_jsonl, _require, _validate_node
from scripts.prepare_hidden_graph_expansion_blind import SOURCE_POOL
from scripts.prepare_hidden_graph_expansion_boundary_v5 import BOUNDARY_DIR

ROOT = Path(__file__).resolve().parents[1]
CASE_DIR = ROOT / "artifacts/hidden_opportunity_graph/flowise_3_1_3_repository_v1"
GRAPH_DIR = CASE_DIR / "graph-v2"
QC_DIR = CASE_DIR / "expansion-qc-v4"
QUAL_DIR = QC_DIR / "reviews"
BOUNDARY_REVIEW_DIR = QC_DIR / "boundary_reviews"
OUT_DIR = CASE_DIR / "expansion-node-set-v1"
CURRENT_POINTER = CASE_DIR / "expansion-node-set-current.json"
QUAL_FILES = [QUAL_DIR / name for name in ("reviewer_a.jsonl", "reviewer_b.jsonl", "adjudicator.jsonl")]
BOUNDARY_FILES = [BOUNDARY_REVIEW_DIR / name for name in ("reviewer_a.jsonl", "reviewer_b.jsonl", "adjudicator.jsonl")]


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def jbytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def jlbytes(values: list[dict[str, Any]]) -> bytes:
    return b"".join((json.dumps(v, ensure_ascii=False, sort_keys=True) + "\n").encode() for v in values)


def source_id_map(candidates: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    rows = _read_jsonl(SOURCE_POOL)
    gt = _read_json(load_case(CASE_ID).ground_truth_path)
    represented = {identifier for node in _read_jsonl(GRAPH_DIR / "nodes.jsonl")
                   for identifier in node.get("gt_root_ids", []) + node.get("near_miss_ids", [])}
    gt_ids = {item["id"] for item in gt["roots"] + gt["near_misses"]}
    remaining = sorted((row for row in rows if row["candidate_id"] in gt_ids - represented),
                       key=lambda row: (row["stratum"], row["candidate_id"]))
    _require(len(remaining) == 11, "remaining private GT candidate mapping changed")
    mapping = {f"C{i:02d}": row for i, row in enumerate(remaining, 1)}
    for cid, row in mapping.items():
        _require(cid in candidates and row["anchor"] == candidates[cid]["anchor"],
                 f"opaque candidate mapping changed: {cid}")
    return mapping


def render(
    freeze_date: str,
    *,
    boundary_files: list[Path] = BOUNDARY_FILES,
    node_set_version: str = "expansion-node-set-v1",
    identity_packet_sha256: str | None = None,
) -> tuple[dict[str, bytes], dict[str, Any]]:
    _require(all(path.is_file() and not path.is_symlink() for path in QUAL_FILES + boundary_files[:2]),
             "preserved qualification/boundary records missing")
    qualification = assess_qualification(*QUAL_FILES)
    _require(qualification["status"] == "ready_for_boundary_and_selection_qc"
             and not qualification["unresolved_candidate_ids"]
             and len(qualification["admitted_candidate_ids"]) == 11,
             "qualification/adjudication gate not satisfied")
    boundary = assess_boundary(*boundary_files)
    _require(boundary["status"] == "ready_to_freeze_expansion_nodes"
             and boundary["pair_denominator"] == 231
             and not boundary["unresolved_candidate_ids"]
             and boundary["final_pair_counts"]["uncertain"] == 0,
             "full split/merge gate not satisfied")
    preservation_sha256 = None
    if node_set_version == "expansion-node-set-v2":
        preservation_path = QC_DIR / "boundary_reviews_v6/record_preservation.json"
        _require(preservation_path.is_file() and not preservation_path.is_symlink(),
                 "v2 boundary record preservation missing")
        preservation = _read_json(preservation_path)
        _require(preservation.get("status") == "preserved_independent_boundary_records_and_disagreement_only_adjudication"
                 and preservation.get("v5_packet_manifest_sha256") == boundary["packet_manifest_sha256"]
                 and preservation.get("v6_identity_packet_manifest_sha256") == identity_packet_sha256,
                 "v2 boundary record provenance mismatch")
        expected_names = {
            "identity_review_a_v6.jsonl", "identity_review_b_v6.jsonl",
            "identity_review_a_c09_v7.jsonl", "identity_review_b_c09_v6.jsonl",
            "adjudication_c04_c09_v6.jsonl", "reviewer_a.jsonl",
            "reviewer_b.jsonl", "adjudicator.jsonl",
        }
        _require(set(preservation.get("files", {})) == expected_names,
                 "v2 boundary preservation file set mismatch")
        for name, record in preservation["files"].items():
            path = preservation_path.parent / name
            _require(path.is_file() and not path.is_symlink()
                     and digest(path.read_bytes()) == record["sha256"]
                     and len(_read_jsonl(path)) == record["rows"],
                     f"v2 boundary source record changed: {name}")
        for name, recorded_hash in preservation["original_v5_review_sha256"].items():
            path = BOUNDARY_REVIEW_DIR / name
            _require(path.is_file() and not path.is_symlink()
                     and digest(path.read_bytes()) == recorded_hash,
                     f"original v5 boundary record changed: {name}")
        preservation_sha256 = digest(preservation_path.read_bytes())
    qualification["qc_date"] = freeze_date
    boundary["qc_date"] = freeze_date
    bundle = _read_json(BOUNDARY_DIR / "reviewer_bundle.json")
    candidates = {row["candidate_id"]: row for row in bundle["candidates"]}
    existing = _read_jsonl(GRAPH_DIR / "nodes.jsonl")
    existing_ids = {node["node_id"] for node in existing}
    _require(len(existing) == 16 and len(candidates) == 11, "node universe changed")
    _, review_a = load_review(boundary_files[0], candidates, existing_ids, complete=True)
    disputed = set(boundary["disputed_candidates"])
    third = {}
    if disputed:
        _, third = load_review(boundary_files[2], candidates, existing_ids, complete=False)
    final_boundary = {cid: third.get(cid, review_a[cid]) for cid in candidates}
    source_rows = source_id_map(candidates)
    q_a = {row["candidate_id"]: row for row in _read_jsonl(QUAL_FILES[0])}
    q_third = {row["candidate_id"]: row for row in _read_jsonl(QUAL_FILES[2])}
    final_qualification = {cid: q_third.get(cid, q_a[cid]) for cid in candidates}

    parent = {cid: cid for cid in list(existing_ids) + list(candidates)}
    def find(key: str) -> str:
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key
    def union(left: str, right: str) -> None:
        parent[find(right)] = find(left)
    for cid, row in final_boundary.items():
        for other in row["merged_existing_node_ids"] + row["merged_candidate_ids"]:
            union(cid, other)
    groups: dict[str, list[str]] = defaultdict(list)
    for identifier in parent:
        groups[find(identifier)].append(identifier)
    for members in groups.values():
        _require(len([x for x in members if x in existing_ids]) <= 1,
                 "expansion merge would collapse two frozen graph-v2 nodes")
    nodes = [dict(node) for node in existing]
    by_id = {node["node_id"]: node for node in nodes}
    new_groups = sorted((sorted(members) for members in groups.values() if not any(x in existing_ids for x in members)),
                        key=lambda members: min(members))
    candidate_to_node: dict[str, str] = {}
    for ordinal, members in enumerate(new_groups, len(existing) + 1):
        _require(all(cid in candidates for cid in members), "new node group contains unknown ID")
        node_id = f"F{ordinal:03d}"
        representative = min(members)
        br = final_boundary[representative]
        qr = final_qualification[representative]
        refs = []
        seen_refs = set()
        for cid in members:
            for ref in final_boundary[cid]["evidence_refs"] + final_qualification[cid]["evidence_refs"]:
                key = (ref["path"], ref["line"], ref["excerpt_sha256"])
                if key not in seen_refs:
                    refs.append(ref)
                    seen_refs.add(key)
        root_ids = sorted(source_rows[cid]["candidate_id"] for cid in members if source_rows[cid]["source_kind"] == "scored_root")
        near_ids = sorted(source_rows[cid]["candidate_id"] for cid in members if source_rows[cid]["source_kind"] == "qualified_near_miss")
        node = {
            "node_id": node_id,
            "security_question": br["security_question"],
            "code_scope": sorted({path for cid in members for path in final_boundary[cid]["code_scope"]}),
            "invariant": br["invariant"],
            "boundary_rationale": "；".join(final_boundary[cid]["rationale"] for cid in members),
            "potential_artifact": "；".join(final_qualification[cid]["independent_chain"] for cid in members),
            "evidence_refs": refs,
            "truth_status": "scored_positive" if root_ids else "qualified_near_miss",
            "gt_root_ids": root_ids,
            "near_miss_ids": near_ids,
            "adjudication_status": "adjudicated",
        }
        nodes.append(node)
        by_id[node_id] = node
        candidate_to_node.update({cid: node_id for cid in members})
    for members in groups.values():
        frozen = [x for x in members if x in existing_ids]
        if not frozen:
            continue
        node = by_id[frozen[0]]
        additions = [cid for cid in members if cid in candidates]
        for cid in additions:
            candidate_to_node[cid] = node["node_id"]
            sid = source_rows[cid]["candidate_id"]
            field = "gt_root_ids" if source_rows[cid]["source_kind"] == "scored_root" else "near_miss_ids"
            node[field] = sorted(set(node.get(field, [])) | {sid})
            node["code_scope"] = sorted(set(node["code_scope"]) | set(final_boundary[cid]["code_scope"]))
            node["evidence_refs"] += [r for r in final_boundary[cid]["evidence_refs"] if r not in node["evidence_refs"]]
            node["boundary_rationale"] += "；合并 " + cid + "：" + final_boundary[cid]["rationale"]
        if node["gt_root_ids"]:
            node["truth_status"] = "scored_positive"
    _require(set(candidate_to_node) == set(candidates), "some candidates lack a final node mapping")
    _require(len({node["node_id"] for node in nodes}) == len(nodes), "duplicate final node IDs")
    gt = _read_json(load_case(CASE_ID).ground_truth_path)
    root_ids = {row["id"] for row in gt["roots"]}
    near_ids = {row["id"] for row in gt["near_misses"]}
    for index, node in enumerate(nodes):
        _validate_node(node, f"frozen expansion node {index}", load_case(CASE_ID).target_root, root_ids, near_ids)
    _require({x for node in nodes for x in node["gt_root_ids"]} == root_ids, "not all 20 roots covered")
    _require({x for node in nodes for x in node.get("near_miss_ids", [])} == near_ids, "not all 5 near misses covered")
    _require(sum(len(node["gt_root_ids"]) for node in nodes) == 20, "duplicate root mapping")
    _require(sum(len(node.get("near_miss_ids", [])) for node in nodes) == 5, "duplicate near-miss mapping")

    node_data = jlbytes(nodes)
    mapping_data = jbytes({"candidate_to_node": candidate_to_node, "final_new_node_count": len(nodes) - len(existing)})
    boundary_qc_data = jbytes(boundary)
    qual_qc_data = jbytes(qualification)
    base_manifest = _read_json(GRAPH_DIR / "graph_manifest.json")
    manifest = {
        "schema_version": 1,
        "case_id": CASE_ID,
        "node_set_version": node_set_version,
        "status": "frozen_nodes_only",
        "freeze_date": freeze_date,
        "base_graph_version": "graph-v2",
        "base_graph_manifest_sha256": digest((GRAPH_DIR / "graph_manifest.json").read_bytes()),
        "target_sha256": base_manifest["target_sha256"],
        "gt_generation": base_manifest["gt_generation"],
        "gt_sha256": base_manifest["gt_sha256"],
        "qualification_packet_manifest_sha256": qualification["packet_manifest_sha256"],
        "boundary_packet_manifest_sha256": boundary["packet_manifest_sha256"],
        "qualification_review_sha256": {path.name: digest(path.read_bytes()) for path in QUAL_FILES},
        "boundary_review_sha256": {path.name: digest(path.read_bytes()) for path in boundary_files if path.is_file()},
        "qualification_qc_sha256": digest(qual_qc_data),
        "boundary_qc_sha256": digest(boundary_qc_data),
        "nodes_sha256": digest(node_data),
        "candidate_mapping_sha256": digest(mapping_data),
        "base_node_count": len(existing),
        "final_node_count": len(nodes),
        "new_node_count": len(nodes) - len(existing),
        "gt_root_count": 20,
        "qualified_near_miss_count": 5,
        "boundary_pair_denominator": 231,
        "edge_status": "not_started",
    }
    if identity_packet_sha256 is not None:
        manifest["identity_recheck_packet_manifest_sha256"] = identity_packet_sha256
        manifest["boundary_record_preservation_sha256"] = preservation_sha256
    outputs = {
        "nodes_frozen.jsonl": node_data,
        "candidate_to_node.json": mapping_data,
        "qualification_qc.json": qual_qc_data,
        "boundary_qc.json": boundary_qc_data,
        "node_set_manifest.json": jbytes(manifest),
    }
    return outputs, manifest


def _version_inputs(version: str) -> tuple[Path, list[Path], str, str | None]:
    if version == "v1":
        return OUT_DIR, BOUNDARY_FILES, "expansion-node-set-v1", None
    if version == "v2":
        from scripts.prepare_hidden_graph_expansion_boundary_v6 import verify as verify_v6
        identity_packet_sha = verify_v6()["packet_manifest_sha256"]
        directory = QC_DIR / "boundary_reviews_v6"
        files = [directory / name for name in ("reviewer_a.jsonl", "reviewer_b.jsonl", "adjudicator.jsonl")]
        return CASE_DIR / "expansion-node-set-v2", files, "expansion-node-set-v2", identity_packet_sha
    raise ValueError(f"unsupported node-set version: {version}")


def current_pointer(node_set_manifest_sha256: str) -> bytes:
    previous = OUT_DIR / "node_set_manifest.json"
    _require(previous.is_file() and not previous.is_symlink(), "superseded v1 manifest missing")
    return jbytes({
        "status": "current_frozen_nodes_only",
        "current_node_set_version": "expansion-node-set-v2",
        "current_node_set_manifest_sha256": node_set_manifest_sha256,
        "superseded_node_sets": [{
            "version": "expansion-node-set-v1",
            "node_set_manifest_sha256": digest(previous.read_bytes()),
            "reason": "C01/C04/C11 question identity required targeted blind recheck before final freeze",
        }],
        "edge_status": "not_started",
    })


def freeze(version: str = "v1") -> dict[str, Any]:
    out_dir, boundary_files, node_set_version, identity_packet_sha = _version_inputs(version)
    outputs, manifest = render(date.today().isoformat(), boundary_files=boundary_files,
                               node_set_version=node_set_version, identity_packet_sha256=identity_packet_sha)
    out_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    out_dir.chmod(0o700)
    for name, content in outputs.items():
        path = out_dir / name
        _require(not path.is_symlink() and (not path.exists() or path.read_bytes() == content),
                 f"frozen node-set artifact changed: {name}")
    for name, content in outputs.items():
        path = out_dir / name
        if not path.exists():
            path.write_bytes(content)
        path.chmod(0o600)
    if version == "v2":
        pointer = current_pointer(digest(outputs["node_set_manifest.json"]))
        _require(not CURRENT_POINTER.is_symlink()
                 and (not CURRENT_POINTER.exists() or CURRENT_POINTER.read_bytes() == pointer),
                 "current node-set pointer changed")
        if not CURRENT_POINTER.exists():
            CURRENT_POINTER.write_bytes(pointer)
        CURRENT_POINTER.chmod(0o600)
    return {"status": "frozen_nodes_only", "node_set_manifest_sha256": digest(outputs["node_set_manifest.json"]),
            "final_node_count": manifest["final_node_count"], "new_node_count": manifest["new_node_count"]}


def verify(version: str = "v1") -> dict[str, Any]:
    out_dir, boundary_files, node_set_version, identity_packet_sha = _version_inputs(version)
    manifest_path = out_dir / "node_set_manifest.json"
    _require(manifest_path.is_file() and not manifest_path.is_symlink(), "node-set manifest missing")
    recorded = _read_json(manifest_path)
    outputs, manifest = render(recorded["freeze_date"], boundary_files=boundary_files,
                               node_set_version=node_set_version, identity_packet_sha256=identity_packet_sha)
    for name, content in outputs.items():
        path = out_dir / name
        _require(path.is_file() and not path.is_symlink() and path.read_bytes() == content,
                 f"frozen node-set artifact mismatch: {name}")
    _require(recorded == manifest and manifest["status"] == "frozen_nodes_only", "node-set manifest mismatch")
    if version == "v2":
        _require(CURRENT_POINTER.is_file() and not CURRENT_POINTER.is_symlink()
                 and CURRENT_POINTER.read_bytes() == current_pointer(digest(outputs["node_set_manifest.json"])),
                 "current node-set pointer mismatch")
    return {"status": "verified_frozen_nodes_only", "node_set_manifest_sha256": digest(outputs["node_set_manifest.json"]),
            "final_node_count": manifest["final_node_count"], "new_node_count": manifest["new_node_count"],
            "boundary_pair_denominator": manifest["boundary_pair_denominator"], "edge_status": manifest["edge_status"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("freeze", "verify"))
    parser.add_argument("--version", choices=("v1", "v2"), default="v1")
    args = parser.parse_args()
    try:
        print(json.dumps(freeze(args.version) if args.command == "freeze" else verify(args.version), ensure_ascii=False, sort_keys=True))
    except GraphValidationError as exc:
        parser.exit(1, f"expansion node-set freeze failed: {exc}\n")
