"""从已裁决的 Pilot B 扩展节点生成完整新增方向的私有盲标包。"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path
from typing import Any

from scripts.hidden_opportunity_graph import (
    CASE_ID,
    PILOT_B_GRAPH_DIR,
    PILOT_B_GRAPH_VERSION,
    PRIVATE_GRAPH_DIR,
    GraphValidationError,
    _read_json,
    _read_jsonl,
    _require,
    validate_graph,
)
from scripts.prepare_hidden_graph_pilot_b_boundaries import BOUNDARY_DIR


EDGE_DIR = BOUNDARY_DIR / "edges"
PACKET_VERSION = "pilot-b-complete-new-directed-edge-packet-v1"


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _jsonl_bytes(values: list[dict[str, Any]]) -> bytes:
    return b"".join((json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8") for value in values)


def render() -> dict[str, bytes]:
    _require(validate_graph(PRIVATE_GRAPH_DIR)["status"] == "valid_frozen", "Pilot A graph is not frozen")
    _require(validate_graph(PILOT_B_GRAPH_DIR)["status"] == "valid_draft", "Pilot B graph is not a draft")
    qc_path = BOUNDARY_DIR / "node_boundary_qc.json"
    node_path = BOUNDARY_DIR / "nodes_frozen.jsonl"
    qc = _read_json(qc_path)
    nodes = _read_jsonl(node_path)
    _require(qc["status"] == "ready_to_freeze_pilot_b_nodes"
             and qc["nodes_frozen_sha256"] == _digest(node_path.read_bytes()),
             "Pilot B nodes have not passed boundary QC")
    n = len(nodes)
    _require(7 <= n <= 16 and qc["selected_node_count"] == n - 6
             and [item["node_id"] for item in nodes] == [f"F{i:03d}" for i in range(1, n + 1)],
             "Pilot B frozen node identity or count changed")
    pilot_a = _read_jsonl(PRIVATE_GRAPH_DIR / "nodes.jsonl")
    _require(nodes[:6] == pilot_a, "Pilot B extended graph changed inherited Pilot A nodes")
    old_pairs = {(item["source_node"], item["target_node"])
                 for item in _read_jsonl(PRIVATE_GRAPH_DIR / "edges.jsonl")}
    _require(len(old_pairs) == 30, "Pilot A directed pair count changed")
    directed_pairs = []
    for source, target in itertools.permutations(nodes, 2):
        pair = source["node_id"], target["node_id"]
        if pair in old_pairs:
            continue
        shared_paths = sorted(set(source["code_scope"]) & set(target["code_scope"]))
        shared_symbols = sorted({ref["symbol"] for ref in source["evidence_refs"]}
                                & {ref["symbol"] for ref in target["evidence_refs"]})
        directed_pairs.append({
            "source_node": pair[0],
            "target_node": pair[1],
            "source_artifact_candidate": source["potential_artifact"],
            "target_claim_candidate": target["security_question"],
            "bounded_check_candidate": (
                "核对共同源码位置/符号在 B 的消费点和正负结果；共享本身不定级。"
                if shared_paths or shared_symbols else
                "追踪 A 的最小信息是否触及 B 的具体 guard、source/sink、归属或必要搜索工作。"
            ),
            "shared_code_paths": shared_paths,
            "shared_symbols": shared_symbols,
            "candidate_status": "ungraded_complete_new_universe",
        })
    expected = n * (n - 1) - 30
    _require(len(directed_pairs) == expected
             and len({(item["source_node"], item["target_node"]) for item in directed_pairs}) == expected,
             "Pilot B new directed pair universe incomplete")
    bundle = {
        "packet_version": PACKET_VERSION,
        "case_id": CASE_ID,
        "graph_version": PILOT_B_GRAPH_VERSION,
        "input_lock_sha256": _digest((PILOT_B_GRAPH_DIR / "input_lock.json").read_bytes()),
        "pilot_a_graph_manifest_sha256": _digest((PRIVATE_GRAPH_DIR / "graph_manifest.json").read_bytes()),
        "node_boundary_qc_sha256": _digest(qc_path.read_bytes()),
        "nodes_frozen_sha256": _digest(node_path.read_bytes()),
        "review_instructions": (
            "分别独立判断全部新增有向对；先判 actionable/non-actionable 与方向，再判五级 taxonomy。"
            "A→B 与 B→A 分开；共享路径/符号和机器检查仅是候选，不是结论。"
            "每条非 none 边给 A/B 冻结源码锚和可区分信息价值；none/thematic-only 给排除理由。"
            "不要查看其他标注者、Pilot A 的边类别、历史 T4 行为或 condition 表现。"
        ),
        "nodes": nodes,
        "inherited_pilot_a_pair_count": len(old_pairs),
        "directed_pairs_to_review": directed_pairs,
    }
    template = [{
        "reviewer_id": "", "source_node": pair["source_node"], "target_node": pair["target_node"],
        "opportunity_type": "", "mechanisms": [], "source_artifact": "", "target_claim": "",
        "expected_effect": [], "bounded_check": "", "evidence": [], "rationale": "",
        "confidence": "", "uncertainty_note": None,
    } for pair in directed_pairs]
    payloads = {
        "edge_reviewer_bundle.json": _json_bytes(bundle),
        "edge_review_form_template.jsonl": _jsonl_bytes(template),
    }
    payloads["edge_packet_manifest.json"] = _json_bytes({
        "packet_version": PACKET_VERSION,
        "case_id": CASE_ID,
        "graph_version": PILOT_B_GRAPH_VERSION,
        "pilot_a_graph_manifest_sha256": bundle["pilot_a_graph_manifest_sha256"],
        "input_lock_sha256": bundle["input_lock_sha256"],
        "node_boundary_qc_sha256": bundle["node_boundary_qc_sha256"],
        "nodes_frozen_sha256": bundle["nodes_frozen_sha256"],
        "builder_sha256": _digest(Path(__file__).read_bytes()),
        "edge_reviewer_bundle_sha256": _digest(payloads["edge_reviewer_bundle.json"]),
        "edge_review_form_template_sha256": _digest(payloads["edge_review_form_template.jsonl"]),
        "total_node_count": n,
        "inherited_pilot_a_pair_count": 30,
        "new_directed_pair_count": expected,
        "total_directed_pair_count": n * (n - 1),
        "annotation_status": "ungraded_complete_new_directed_pairs",
    })
    return payloads


def build() -> dict[str, Any]:
    _require(not EDGE_DIR.is_symlink(), "unsafe Pilot B edge directory")
    EDGE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    EDGE_DIR.chmod(0o700)
    payloads = render()
    for name, data in payloads.items():
        path = EDGE_DIR / name
        _require(not path.is_symlink() and (not path.exists() or path.read_bytes() == data),
                 f"Pilot B edge packet changed; create a new packet version: {name}")
        path.write_bytes(data)
        path.chmod(0o600)
    return verify()


def verify() -> dict[str, Any]:
    payloads = render()
    for name, data in payloads.items():
        path = EDGE_DIR / name
        _require(path.is_file() and not path.is_symlink() and path.read_bytes() == data,
                 f"Pilot B edge packet missing or changed: {name}")
    manifest = _read_json(EDGE_DIR / "edge_packet_manifest.json")
    return {
        "status": "verified_ungraded_edge_packet",
        "total_node_count": manifest["total_node_count"],
        "new_directed_pair_count": manifest["new_directed_pair_count"],
        "total_directed_pair_count": manifest["total_directed_pair_count"],
        "edge_packet_manifest_sha256": _digest(payloads["edge_packet_manifest.json"]),
        "edge_reviewer_bundle_sha256": _digest(payloads["edge_reviewer_bundle.json"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "verify"))
    args = parser.parse_args()
    try:
        result = build() if args.command == "build" else verify()
    except GraphValidationError as exc:
        parser.exit(1, f"Pilot B edge packet error: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
