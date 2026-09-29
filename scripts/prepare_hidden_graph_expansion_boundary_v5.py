#!/usr/bin/env python3
"""Build an explicit all-pair split/merge review packet for expansion nodes."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from scripts.prepare_hidden_graph_expansion_boundary_blind import BOUNDARY_DIR as V4_DIR, render as render_v4

ROOT = Path(__file__).resolve().parents[1]
BOUNDARY_DIR = ROOT / "artifacts/hidden_opportunity_graph/flowise_3_1_3_repository_v1/expansion-boundary-prep-v5-blind"
PACKET_VERSION = "repository-v1-expansion-boundary-v5-all-pairs-blind-ungraded"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def jbytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def jlbytes(values: list[dict[str, Any]]) -> bytes:
    return b"".join((json.dumps(v, ensure_ascii=False, sort_keys=True) + "\n").encode() for v in values)


def render() -> dict[str, bytes]:
    source = render_v4()
    bundle = json.loads(source["reviewer_bundle.json"])
    old_manifest = json.loads(source["packet_manifest.json"])
    candidates = bundle["candidates"]
    cids = sorted(c["candidate_id"] for c in candidates)
    fids = sorted(n["node_id"] for n in bundle["existing_node_boundaries"])
    if len(cids) != 11 or len(fids) != 16:
        raise ValueError("expected 11 candidates and 16 frozen nodes")
    bundle["packet_version"] = PACKET_VERSION
    bundle["review_instructions"] = (
        "对每个 Cxx 显式核对其与全部 16 个 Fxx 和另外 10 个 Cxx 的 split/merge；"
        "逐行列出完整 reviewed_existing_node_ids/reviewed_candidate_ids，"
        "任何 merge 需列出目标。两份审查相互隔离且只读本包与冻结 target。"
    )
    bundle["all_pair_denominator"] = len(fids) * len(cids) + len(cids) * (len(cids) - 1) // 2
    bundle["calibration_rules"] = list(bundle["calibration_rules"]) + [
        "完整边界 universe 为 16×11+11×10/2=231 个无序对；既有 F-F 120 对沿用 graph-v2，不在本轮重审。",
        "每个 C-F 对在 C 行声明；每个 C-C 对在两端 C 行均声明且判断必须对称。",
        "reviewed_* 列表只证明逐一考虑目标；merge 需明确列目标和源码理由，未列 merge 的已审对为 split。",
    ]
    form = []
    for cid in cids:
        form.append({
            "reviewer_id": "", "candidate_id": cid, "boundary_decision": "",
            "reviewed_existing_node_ids": fids,
            "reviewed_candidate_ids": [x for x in cids if x != cid],
            "merged_existing_node_ids": [], "merged_candidate_ids": [],
            "security_question": "", "invariant": "", "code_scope": [],
            "evidence_refs": [], "rationale": "", "uncertainty_note": None,
        })
    rules = {"packet_version": PACKET_VERSION, "rules": bundle["calibration_rules"]}
    payloads = {
        "reviewer_bundle.json": jbytes(bundle),
        "boundary_review_form_template.jsonl": jlbytes(form),
        "calibration_rules.json": jbytes(rules),
    }
    manifest = {
        "packet_version": PACKET_VERSION,
        "case_id": bundle["case_id"],
        "base_graph_version": bundle["base_graph_version"],
        "base_graph_manifest_sha256": bundle["base_graph_manifest_sha256"],
        "source_v4_packet_manifest_sha256": digest(source["packet_manifest.json"]),
        "builder_sha256": digest(Path(__file__).read_bytes()),
        "candidate_count": len(cids),
        "existing_node_count": len(fids),
        "all_pair_denominator": bundle["all_pair_denominator"],
        "review_form_row_count": len(form),
        "reviewer_bundle_sha256": digest(payloads["reviewer_bundle.json"]),
        "review_form_sha256": digest(payloads["boundary_review_form_template.jsonl"]),
        "calibration_rules_sha256": digest(payloads["calibration_rules.json"]),
        "annotation_status": "ungraded_blind_boundary_all_pairs",
    }
    if old_manifest["base_graph_manifest_sha256"] != manifest["base_graph_manifest_sha256"]:
        raise ValueError("v4/v5 base graph mismatch")
    payloads["packet_manifest.json"] = jbytes(manifest)
    return payloads


def verify() -> dict[str, Any]:
    payloads = render()
    for name, content in payloads.items():
        path = BOUNDARY_DIR / name
        if not path.is_file() or path.is_symlink() or path.read_bytes() != content:
            raise ValueError(f"missing or modified v5 boundary packet: {name}")
    bundle = json.loads(payloads["reviewer_bundle.json"])
    if bundle["all_pair_denominator"] != 231:
        raise ValueError("unexpected pair denominator")
    if any(key in json.dumps(bundle, ensure_ascii=False).lower() for key in ("truth_status", "gt_root_ids", "near_miss_ids", "source_kind")):
        raise ValueError("v5 boundary packet leaks evaluator labels")
    return {
        "status": "verified_ungraded_blind_boundary_all_pairs",
        "candidate_count": 11,
        "existing_node_count": 16,
        "all_pair_denominator": 231,
        "packet_manifest_sha256": digest(payloads["packet_manifest.json"]),
        "base_graph_manifest_sha256": bundle["base_graph_manifest_sha256"],
    }


def build() -> dict[str, Any]:
    BOUNDARY_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    BOUNDARY_DIR.chmod(0o700)
    for name, content in render().items():
        path = BOUNDARY_DIR / name
        if path.exists() and path.read_bytes() != content:
            raise ValueError(f"v5 packet changed; create a new version: {name}")
        path.write_bytes(content)
        path.chmod(0o600)
    return verify()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("build", "verify"))
    args = parser.parse_args()
    print(json.dumps(build() if args.command == "build" else verify(), ensure_ascii=False, sort_keys=True))
