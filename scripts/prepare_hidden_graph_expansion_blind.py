#!/usr/bin/env python3
"""Build a de-labelled structural-expansion packet for independent reviewers.

The evaluator-private candidate inventory is used only by the coordinator to
select the remaining bounded source anchors.  The reviewer packet contains no
ground-truth IDs, source-case labels, provenance, historical runs, or edge
labels.  Opaque Cxx identifiers are mapped back only by coordinator-side QC.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CASE_DIR = ROOT / "artifacts/hidden_opportunity_graph/flowise_3_1_3_repository_v1"
GRAPH_DIR = CASE_DIR / "graph-v2"
SOURCE_POOL = CASE_DIR / "pilot-b-prep-v1/round2/candidate_pool.jsonl"
GT_PATH = ROOT / "experiments/emergent_coordination/evaluator_private/flowise_3_1_3_repository_v1/ground_truth.json"
BLIND_DIR = CASE_DIR / "expansion-prep-v4-blind"
PACKET_VERSION = "repository-v1-structural-expansion-v4-blind-ungraded"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def jsonl_bytes(values: list[dict[str, Any]]) -> bytes:
    return b"".join((json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n").encode() for value in values)


def render() -> dict[str, bytes]:
    graph_manifest = read_json(GRAPH_DIR / "graph_manifest.json")
    if graph_manifest.get("adjudication_status") != "frozen":
        raise ValueError("base graph-v2 must be frozen")
    gt = read_json(GT_PATH)
    existing = read_jsonl(GRAPH_DIR / "nodes.jsonl")
    source_rows = read_jsonl(SOURCE_POOL)
    represented = {
        item for node in existing
        for item in node.get("gt_root_ids", []) + node.get("near_miss_ids", [])
    }
    universe = {item["id"] for item in gt["roots"] + gt["near_misses"]}
    remaining = [row for row in source_rows if row["candidate_id"] in universe - represented]
    if len(remaining) != 11:
        raise ValueError(f"expected 11 remaining candidates, got {len(remaining)}")
    # The deterministic order is coordinator-only.  Do not expose its source
    # stratum or evaluator identity in the reviewer packet.
    remaining.sort(key=lambda row: (row["stratum"], row["candidate_id"]))
    aliases = {row["candidate_id"]: f"C{index:02d}" for index, row in enumerate(remaining, 1)}
    candidates: list[dict[str, Any]] = []
    for row in remaining:
        candidates.append({
            "candidate_id": aliases[row["candidate_id"]],
            "anchor": row["anchor"],
            "question_prompt": "依据给定源码锚点与冻结源码，写出可独立裁决的 bounded security question 及必要 source→sink/guard 链。",
            "scope_limit": "只判断该源码入口/链条的局部安全不变量；不得把一个锚点推断为全仓库性质。",
        })
    existing_nodes = []
    for node in existing:
        existing_nodes.append({
            "node_id": node["node_id"],
            "security_question": node["security_question"],
            "code_scope": node["code_scope"],
            "invariant": node["invariant"],
        })
    rules = [
        "只依据冻结 target 源码、safe-sibling/validation metadata、批准威胁模型和本包的既有节点边界摘要。",
        "本包不含 ground truth、source-case 标签、provenance、历史运行、task/finding、event/transcript 或既有 edge labels。",
        "每个候选先判断是否是可独立裁决的 bounded security question，再判断与既有节点及同批候选的 split/merge。",
        "逐项给出 source→sink/guard/ownership/reachability 链、正负结论反事实和 target-relative excerpt hash。",
        "审定者不得通过 Cxx 以外的外部身份、历史记录或标签推断候选类别。",
        "两名独立 reviewer 完成后才能产生第三人裁决（如有分歧）和新 graph version。",
    ]
    bundle = {
        "packet_version": PACKET_VERSION,
        "case_id": "flowise_3_1_3_repository_v1",
        "base_graph_version": "graph-v2",
        "base_graph_manifest_sha256": digest((GRAPH_DIR / "graph_manifest.json").read_bytes()),
        "review_instructions": "独立审查本批 11 个去标签候选；不可读取历史运行、evaluator-private 文件或既有边标签。",
        "reviewer_input_roots": {
            "target_source_root": "experiments/emergent_coordination/repositories/flowise_3_1_3_repository_v1",
            "allowed_metadata": "本包列明的 safe-sibling、validation metadata 与批准威胁模型（如需）",
        },
        "calibration_rules": rules,
        "existing_node_boundaries": existing_nodes,
        "candidates": candidates,
    }
    # Fixed batches use opaque IDs only; no source stratum is exposed.
    ids = [item["candidate_id"] for item in candidates]
    batches = [ids[:4], ids[4:8], ids[8:]]
    batch_plan = {
        "packet_version": PACKET_VERSION,
        "case_id": "flowise_3_1_3_repository_v1",
        "base_graph_version": "graph-v2",
        "base_graph_manifest_sha256": bundle["base_graph_manifest_sha256"],
        "status": "ungraded_blind_node_batch_plan",
        "candidate_count": len(ids),
        "candidate_ids": ids,
        "review_batches": [{"batch_id": f"batch-{i:02d}", "candidate_ids": batch} for i, batch in enumerate(batches, 1)],
        "batch_selection_rule": "coordinator-fixed opaque order; sizes 4/4/3",
        "additional_unscored_fronts": "not included and excluded from all denominators",
        "forbidden_inputs": ["ground truth", "source-case labels", "historical runs", "events", "transcripts", "tasks/findings", "existing edge labels"],
        "next_gate": "two independent node reviews, then adjudication of every disagreement before any new graph version",
    }
    form = [
        {"admission_decision": "", "candidate_id": candidate_id, "evidence_refs": [], "independent_chain": "", "invariant": "", "pilot_a_boundary": "", "rationale": "", "reviewer_id": "", "security_question": "", "uncertainty_note": None}
        for candidate_id in ids
    ]
    rules_value = {"packet_version": PACKET_VERSION, "rules": rules}
    payloads = {
        "candidate_pool.jsonl": jsonl_bytes(candidates),
        "reviewer_bundle.json": json_bytes(bundle),
        "node_review_form_template.jsonl": jsonl_bytes(form),
        "calibration_rules.json": json_bytes(rules_value),
        "batch_plan.json": json_bytes(batch_plan),
    }
    manifest = {
        "packet_version": PACKET_VERSION,
        "case_id": "flowise_3_1_3_repository_v1",
        "base_graph_version": "graph-v2",
        "base_graph_manifest_sha256": bundle["base_graph_manifest_sha256"],
        "builder_sha256": digest(Path(__file__).read_bytes()),
        "candidate_count": len(ids),
        "review_form_row_count": len(form),
        "candidate_pool_sha256": digest(payloads["candidate_pool.jsonl"]),
        "reviewer_bundle_sha256": digest(payloads["reviewer_bundle.json"]),
        "review_form_sha256": digest(payloads["node_review_form_template.jsonl"]),
        "calibration_rules_sha256": digest(payloads["calibration_rules.json"]),
        "batch_plan_sha256": digest(payloads["batch_plan.json"]),
        "annotation_status": "ungraded_blind_node_batch_plan",
    }
    payloads["packet_manifest.json"] = json_bytes(manifest)
    return payloads


def build() -> dict[str, Any]:
    BLIND_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    BLIND_DIR.chmod(0o700)
    for name, payload in render().items():
        path = BLIND_DIR / name
        if path.exists() and path.read_bytes() != payload:
            raise ValueError(f"blind packet changed; create a new packet version: {name}")
        path.write_bytes(payload)
        path.chmod(0o600)
    return verify()


def verify() -> dict[str, Any]:
    payloads = render()
    for name, payload in payloads.items():
        path = BLIND_DIR / name
        if not path.is_file() or path.is_symlink() or path.read_bytes() != payload:
            raise ValueError(f"blind packet missing or changed: {name}")
    bundle = json.loads(payloads["reviewer_bundle.json"])
    plan = json.loads(payloads["batch_plan.json"])
    manifest = json.loads(payloads["packet_manifest.json"])
    ids = {item["candidate_id"] for item in bundle["candidates"]}
    if ids != set(plan["candidate_ids"]) or len(ids) != 11:
        raise ValueError("blind packet candidate universe mismatch")
    if any(any(token in json.dumps(payload, ensure_ascii=False).lower() for token in ("ground_truth", "source_kind", "truth_status", "gt_root_ids", "near_miss_ids")) for payload in [bundle, plan]):
        raise ValueError("blind packet leaks evaluator or source-case labels")
    return {
        "status": "verified_ungraded_blind_node_batch_plan",
        "candidate_count": len(ids),
        "packet_manifest_sha256": digest(payloads["packet_manifest.json"]),
        "base_graph_version": plan["base_graph_version"],
        "base_graph_manifest_sha256": plan["base_graph_manifest_sha256"],
        "candidate_ids": sorted(ids),
        "annotation_status": manifest["annotation_status"],
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("build", "verify"))
    args = parser.parse_args()
    print(json.dumps(build() if args.command == "build" else verify(), ensure_ascii=False, sort_keys=True))
