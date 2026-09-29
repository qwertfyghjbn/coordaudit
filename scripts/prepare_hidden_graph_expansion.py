#!/usr/bin/env python3
"""Prepare an ungraded, independent structural-expansion candidate packet.

The packet is deliberately separate from frozen graph-v2.  It contains the
remaining prequalified v1 root/near-miss candidates and boundary summaries of
existing nodes, but no edge labels, runtime traces, findings, or historical
behavior.  It does not create or mutate a graph version.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CASE_DIR = ROOT / "artifacts/hidden_opportunity_graph/flowise_3_1_3_repository_v1"
GRAPH_DIR = CASE_DIR / "graph-v2"
PREP_DIR = CASE_DIR / "expansion-prep-v3"
SOURCE_POOL = CASE_DIR / "pilot-b-prep-v1/round2/candidate_pool.jsonl"
SOURCE_TEMPLATE = CASE_DIR / "pilot-b-prep-v1/round2/node_review_form_template.jsonl"
GT_PATH = ROOT / "experiments/emergent_coordination/evaluator_private/flowise_3_1_3_repository_v1/ground_truth.json"
PACKET_VERSION = "repository-v1-structural-expansion-v3-ungraded"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def jsonl_bytes(values: list[dict[str, Any]]) -> bytes:
    return b"".join((json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8") for value in values)


def render() -> dict[str, bytes]:
    graph_manifest = read_json(GRAPH_DIR / "graph_manifest.json")
    if graph_manifest["adjudication_status"] != "frozen":
        raise ValueError("base graph-v2 must be frozen")
    gt = read_json(GT_PATH)
    existing = read_jsonl(GRAPH_DIR / "nodes.jsonl")
    candidates = read_jsonl(SOURCE_POOL)
    represented_ids = {
        identifier for node in existing
        for identifier in node.get("gt_root_ids", []) + node.get("near_miss_ids", [])
    }
    gt_ids = {item["id"] for item in gt["roots"] + gt["near_misses"]}
    remaining_ids = gt_ids - represented_ids
    remaining = [row for row in candidates if row["candidate_id"] in remaining_ids]
    if {row["candidate_id"] for row in remaining} != remaining_ids:
        raise ValueError("remaining v1 GT IDs are not present in the locked candidate pool")
    remaining.sort(key=lambda row: (row["stratum"], row["candidate_id"]))

    # Source-stratified fixed order; independent of historical behavior.
    strata = sorted({row["stratum"] for row in remaining})
    queues = {stratum: [row["candidate_id"] for row in remaining if row["stratum"] == stratum]
              for stratum in strata}
    ordered_ids: list[str] = []
    while any(queues.values()):
        for stratum in strata:
            if queues[stratum]:
                ordered_ids.append(queues[stratum].pop(0))
    batch_sizes = (4, 4, 3)
    if len(ordered_ids) != sum(batch_sizes):
        raise ValueError("the three-batch plan requires exactly 11 remaining candidates")
    batches = []
    offset = 0
    for index, size in enumerate(batch_sizes, 1):
        batches.append({"batch_id": f"batch-{index:02d}", "candidate_ids": ordered_ids[offset:offset + size]})
        offset += size

    # Existing node summaries are needed to detect duplicate security
    # questions, but edge labels and runtime/history are intentionally absent.
    existing_nodes = []
    for node in existing:
        existing_nodes.append({
            "node_id": node["node_id"],
            "security_question": node["security_question"],
            "code_scope": node["code_scope"],
            "invariant": node["invariant"],
        })

    rules = [
        "只依据冻结 target、v1 GT、safe siblings、validation metadata、批准威胁模型和本包的既有节点边界摘要。",
        "不得读取历史 T4 run、task/finding、event/transcript、既有 edge labels 或 operational reports。",
        "每个候选先独立判断是否为可独立裁决的 bounded security question，再判断与既有节点及同批候选的 split/merge。",
        "逐项给出 source→sink/guard/ownership/reachability 链、正负结论反事实和 target-relative excerpt hash。",
        "GT root/near-miss 身份不自动授予节点资格；新增 unscored front 必须另行独立资格审查。",
        "本包是 ungraded；两名独立 reviewer 完成后才能产生第三人裁决（如有分歧）和新 graph version。",
    ]
    bundle = {
        "packet_version": PACKET_VERSION,
        "case_id": "flowise_3_1_3_repository_v1",
        "base_graph_version": "graph-v2",
        "base_graph_manifest_sha256": digest((GRAPH_DIR / "graph_manifest.json").read_bytes()),
        "review_instructions": "独立审查本批 11 个剩余 v1 root/near-miss 候选；不可读取历史运行或既有边标签。",
        "calibration_rules": rules,
        "existing_node_boundaries": existing_nodes,
        "candidates": remaining,
        "unscored_front_policy": "additional_unscored_fronts_not_included; qualify separately from active fronts",
    }
    batch_plan = {
        "packet_version": PACKET_VERSION,
        "case_id": "flowise_3_1_3_repository_v1",
        "base_graph_version": "graph-v2",
        "base_graph_manifest_sha256": digest((GRAPH_DIR / "graph_manifest.json").read_bytes()),
        "status": "ungraded_independent_node_batch_plan",
        "candidate_count": len(remaining),
        "candidate_ids": [row["candidate_id"] for row in remaining],
        "review_batches": batches,
        "batch_selection_rule": "sort candidate IDs within each source stratum, interleave strata lexicographically, then split 4/4/3",
        "by_stratum": {
            stratum: [row["candidate_id"] for row in remaining if row["stratum"] == stratum]
            for stratum in sorted({row["stratum"] for row in remaining})
        },
        "additional_unscored_fronts": "not enumerated and excluded from all denominators",
        "forbidden_inputs": ["T4 events", "T4 transcripts", "T4 tasks/findings", "existing graph edge labels", "operational summaries"],
        "next_gate": "two independent node reviews, then adjudication of every disagreement before any new graph version",
    }
    source_forms = {row["candidate_id"]: row for row in read_jsonl(SOURCE_TEMPLATE)}
    if not set(ordered_ids) <= set(source_forms):
        raise ValueError("source review template lacks a remaining candidate")
    reviewer_form = jsonl_bytes([source_forms[candidate_id] for candidate_id in ordered_ids])
    candidate_bytes = jsonl_bytes(remaining)
    bundle_bytes = json_bytes(bundle)
    plan_bytes = json_bytes(batch_plan)
    rules_bytes = json_bytes({"packet_version": PACKET_VERSION, "rules": rules})
    manifest_bytes = json_bytes({
        "packet_version": PACKET_VERSION,
        "case_id": "flowise_3_1_3_repository_v1",
        "base_graph_version": "graph-v2",
        "base_graph_manifest_sha256": digest((GRAPH_DIR / "graph_manifest.json").read_bytes()),
        "builder_sha256": digest(Path(__file__).read_bytes()),
        "candidate_count": len(remaining),
        "review_form_row_count": len(ordered_ids),
        "candidate_pool_sha256": digest(candidate_bytes),
        "reviewer_bundle_sha256": digest(bundle_bytes),
        "review_form_sha256": digest(reviewer_form),
        "calibration_rules_sha256": digest(rules_bytes),
        "batch_plan_sha256": digest(plan_bytes),
        "annotation_status": "ungraded_independent_node_batch_plan",
    })
    return {
        "candidate_pool.jsonl": candidate_bytes,
        "reviewer_bundle.json": bundle_bytes,
        "node_review_form_template.jsonl": reviewer_form,
        "calibration_rules.json": rules_bytes,
        "batch_plan.json": plan_bytes,
        "packet_manifest.json": manifest_bytes,
    }


def build() -> dict[str, Any]:
    PREP_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    PREP_DIR.chmod(0o700)
    payloads = render()
    for name, payload in payloads.items():
        path = PREP_DIR / name
        if path.exists() and path.read_bytes() != payload:
            raise ValueError(f"expansion packet changed; create a new packet version: {name}")
        path.write_bytes(payload)
        path.chmod(0o600)
    return verify()


def verify() -> dict[str, Any]:
    payloads = render()
    for name, payload in payloads.items():
        path = PREP_DIR / name
        if not path.is_file() or path.is_symlink() or path.read_bytes() != payload:
            raise ValueError(f"expansion packet missing or changed: {name}")
    plan = json.loads(payloads["batch_plan.json"])
    manifest = json.loads(payloads["packet_manifest.json"])
    if plan["status"] != "ungraded_independent_node_batch_plan":
        raise ValueError("expansion packet is not explicitly ungraded")
    if manifest["annotation_status"] != "ungraded_independent_node_batch_plan":
        raise ValueError("expansion packet manifest is not explicitly ungraded")
    if len(plan["candidate_ids"]) != 11:
        raise ValueError("expected 11 remaining prequalified v1 candidates")
    return {
        "status": "verified_ungraded_independent_node_batch_plan",
        "candidate_count": len(plan["candidate_ids"]),
        "packet_manifest_sha256": digest(payloads["packet_manifest.json"]),
        "base_graph_version": plan["base_graph_version"],
        "base_graph_manifest_sha256": plan["base_graph_manifest_sha256"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "verify"))
    args = parser.parse_args()
    result = build() if args.command == "build" else verify()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
