#!/usr/bin/env python3
"""Prepare a de-labelled split/merge boundary packet for expansion nodes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CASE_DIR = ROOT / "artifacts/hidden_opportunity_graph/flowise_3_1_3_repository_v1"
GRAPH_DIR = CASE_DIR / "graph-v2"
SOURCE_DIR = CASE_DIR / "expansion-prep-v4-blind"
BOUNDARY_DIR = CASE_DIR / "expansion-boundary-prep-v4-blind"
PACKET_VERSION = "repository-v1-expansion-boundary-v4-blind-ungraded"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def jbytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def jlbytes(values: list[dict[str, Any]]) -> bytes:
    return b"".join((json.dumps(v, ensure_ascii=False, sort_keys=True) + "\n").encode() for v in values)


def render() -> dict[str, bytes]:
    base = read_json(GRAPH_DIR / "graph_manifest.json")
    if base.get("adjudication_status") != "frozen":
        raise ValueError("graph-v2 must be frozen")
    source_bundle = read_json(SOURCE_DIR / "reviewer_bundle.json")
    candidates = source_bundle["candidates"]
    if len(candidates) != 11 or {c["candidate_id"] for c in candidates} != {f"C{i:02d}" for i in range(1, 12)}:
        raise ValueError("unexpected v4 blind candidate universe")
    nodes = read_jsonl(GRAPH_DIR / "nodes.jsonl")
    existing = [{
        "node_id": node["node_id"],
        "security_question": node["security_question"],
        "code_scope": node["code_scope"],
        "invariant": node["invariant"],
    } for node in nodes]
    rules = [
        "只读 target 源码、v4 去标签 candidate anchors、既有节点边界摘要和批准的安全模型。",
        "本包不含 ground truth、source-case 标签、provenance、历史运行、reviewer 判断或 edge labels。",
        "对每个 Cxx 判断它是否是独立 bounded investigation unit；若是 root-cause variant 或同一安全不变量的入口，列出应 merge 的既有 node 或同批 Cxx。",
        "split/merge 必须基于安全问题、受保护对象、不变量及 source→sink/guard/ownership/reachability 推理，不得以文件名或主题相似度单独决定。",
        "若边界证据不足，使用 uncertain 并写出缺失事实；第三人只裁决两份审查的边界分歧。",
    ]
    bundle = {
        "packet_version": PACKET_VERSION,
        "case_id": "flowise_3_1_3_repository_v1",
        "base_graph_version": "graph-v2",
        "base_graph_manifest_sha256": digest((GRAPH_DIR / "graph_manifest.json").read_bytes()),
        "review_instructions": "独立复核 11 个 opaque candidate 的 split/merge 边界；不得查看任何上一轮 reviewer 或 evaluator-private 文件。",
        "candidates": candidates,
        "existing_node_boundaries": existing,
        "calibration_rules": rules,
        "forbidden_inputs": ["ground truth", "source-case labels", "historical runs", "reviewer outputs", "edge labels"],
    }
    form = [{
        "reviewer_id": "",
        "candidate_id": c["candidate_id"],
        "boundary_decision": "",
        "merged_existing_node_ids": [],
        "merged_candidate_ids": [],
        "security_question": "",
        "invariant": "",
        "code_scope": [],
        "evidence_refs": [],
        "rationale": "",
        "uncertainty_note": None,
    } for c in candidates]
    rules_value = {"packet_version": PACKET_VERSION, "rules": rules}
    payloads = {
        "reviewer_bundle.json": jbytes(bundle),
        "boundary_review_form_template.jsonl": jlbytes(form),
        "calibration_rules.json": jbytes(rules_value),
    }
    manifest = {
        "packet_version": PACKET_VERSION,
        "case_id": "flowise_3_1_3_repository_v1",
        "base_graph_version": "graph-v2",
        "base_graph_manifest_sha256": bundle["base_graph_manifest_sha256"],
        "builder_sha256": digest(Path(__file__).read_bytes()),
        "candidate_count": len(candidates),
        "review_form_row_count": len(form),
        "reviewer_bundle_sha256": digest(payloads["reviewer_bundle.json"]),
        "review_form_sha256": digest(payloads["boundary_review_form_template.jsonl"]),
        "calibration_rules_sha256": digest(payloads["calibration_rules.json"]),
        "annotation_status": "ungraded_blind_boundary_batch_plan",
    }
    payloads["packet_manifest.json"] = jbytes(manifest)
    return payloads


def verify() -> dict[str, Any]:
    payloads = render()
    for name, data in payloads.items():
        path = BOUNDARY_DIR / name
        if not path.is_file() or path.is_symlink() or path.read_bytes() != data:
            raise ValueError(f"boundary packet missing or changed: {name}")
    bundle = json.loads(payloads["reviewer_bundle.json"])
    if any(token in json.dumps(bundle, ensure_ascii=False).lower() for token in ("truth_status", "gt_root_ids", "near_miss_ids", "source_kind")):
        raise ValueError("boundary packet leaks evaluator labels")
    return {
        "status": "verified_ungraded_blind_boundary_batch_plan",
        "candidate_count": len(bundle["candidates"]),
        "packet_manifest_sha256": digest(payloads["packet_manifest.json"]),
        "base_graph_version": bundle["base_graph_version"],
        "base_graph_manifest_sha256": bundle["base_graph_manifest_sha256"],
    }


def build() -> dict[str, Any]:
    BOUNDARY_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    BOUNDARY_DIR.chmod(0o700)
    for name, data in render().items():
        path = BOUNDARY_DIR / name
        if path.exists() and path.read_bytes() != data:
            raise ValueError(f"boundary packet changed; create a new version: {name}")
        path.write_bytes(data)
        path.chmod(0o600)
    return verify()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("build", "verify"))
    args = parser.parse_args()
    print(json.dumps(build() if args.command == "build" else verify(), ensure_ascii=False, sort_keys=True))
