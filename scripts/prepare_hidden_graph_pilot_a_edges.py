"""为 Pilot A 的 30 个有向对生成不含边结论的私有盲标包。"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path
from typing import Any

from scripts.hidden_opportunity_graph import (
    CASE_ID,
    GRAPH_VERSION,
    PRIVATE_GRAPH_DIR,
    GraphValidationError,
    _read_json,
    _read_jsonl,
    _require,
    validate_graph,
)
from scripts.prepare_hidden_graph_pilot_a import PILOT_DIR, verify as verify_nodes_packet


EDGE_DIR = PILOT_DIR / "edges"
EDGE_PACKET_VERSION = "pilot-a-directed-edge-packet-v1"


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _jsonl_bytes(records: list[dict[str, Any]]) -> bytes:
    return b"".join((json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8") for item in records)


def render(directory: Path = EDGE_DIR) -> dict[str, bytes]:
    _require(not directory.is_symlink(), "Pilot A edge directory must not be a symlink")
    _require(directory.resolve() == EDGE_DIR.resolve(), "Pilot A edge packet must use the locked private directory")
    _require(validate_graph(PRIVATE_GRAPH_DIR)["status"] == "valid_draft", "graph must still be a draft")
    verify_nodes_packet(PILOT_DIR)
    qc_path = PILOT_DIR / "node_boundary_qc.json"
    nodes_path = PILOT_DIR / "nodes_frozen.jsonl"
    packet_path = PILOT_DIR / "candidate_packets.jsonl"
    qc = _read_json(qc_path)
    nodes = _read_jsonl(nodes_path)
    packets = _read_jsonl(packet_path)
    _require(qc["status"] == "ready_to_freeze_six_nodes" and qc["node_pair_gate_passed"] is True,
             "Pilot A node boundary QC has not passed")
    _require(qc["nodes_frozen_sha256"] == _digest(nodes_path.read_bytes()), "frozen nodes digest mismatch")
    _require([node["node_id"] for node in nodes] == [f"F{i:03d}" for i in range(1, 7)],
             "Pilot A frozen node IDs changed")
    _require(len(packets) == 6, "Pilot A candidate packet count changed")
    annotated_nodes = [
        {
            **node,
            "candidate_packet": {
                key: packet[key]
                for key in (
                    "candidate_id", "decision_to_reach", "source", "affected_object", "positive_outcome",
                    "negative_outcome", "scope_limits", "open_questions", "safe_sibling_contrasts"
                )
            },
        }
        for node, packet in zip(nodes, packets)
    ]
    _require(all(node["gt_root_ids"] == [packet["candidate_id"]] if node["gt_root_ids"]
                 else node.get("near_miss_ids") == [packet["candidate_id"]]
                 for node, packet in zip(nodes, packets)), "candidate/node mapping changed")
    directed_pairs = []
    for source, target in itertools.permutations(nodes, 2):
        source_paths = set(source["code_scope"])
        target_paths = set(target["code_scope"])
        source_symbols = {ref["symbol"] for ref in source["evidence_refs"]}
        target_symbols = {ref["symbol"] for ref in target["evidence_refs"]}
        shared_paths = sorted(source_paths & target_paths)
        shared_symbols = sorted(source_symbols & target_symbols)
        check = (
            "对照共同源码位置/符号的 guard、查询谓词与调用链；判断 A 的正负结果是否会改变 B 的具体 claim。"
            if shared_paths or shared_symbols else
            "追踪 A 的最小证据能否触及 B 的具体 guard、source/sink 或归属判断；若无具体连接，记录排除依据。"
        )
        directed_pairs.append({
            "source_node": source["node_id"],
            "target_node": target["node_id"],
            "source_artifact_candidate": source["potential_artifact"],
            "target_claim_candidate": target["security_question"],
            "bounded_check_candidate": check,
            "shared_code_paths": shared_paths,
            "shared_symbols": shared_symbols,
            "candidate_status": "ungraded_complete_universe",
        })
    _require(len(directed_pairs) == 30 and len({(p["source_node"], p["target_node"]) for p in directed_pairs}) == 30,
             "incomplete Pilot A directed pair universe")
    bundle = {
        "packet_version": EDGE_PACKET_VERSION,
        "case_id": CASE_ID,
        "graph_version": GRAPH_VERSION,
        "input_lock_sha256": _digest((PRIVATE_GRAPH_DIR / "input_lock.json").read_bytes()),
        "nodes_frozen_sha256": _digest(nodes_path.read_bytes()),
        "review_instructions": (
            "只凭冻结源码、v1 GT、safe siblings、validation metadata、静态威胁模型和此包独立判定全部 30 个方向。"
            "先判 actionable/non-actionable，再判五级 taxonomy；A→B 与 B→A 分别给出最小信息价值。"
            "所有共享路径/符号与 bounded_check 均只是机器候选，不是边结论。"
            "不要阅读节点初判、其他边标注、历史 T4 行为或 condition 表现。"
        ),
        "nodes": annotated_nodes,
        "directed_pairs": directed_pairs,
    }
    template = [
        {
            "reviewer_id": "",
            "source_node": pair["source_node"],
            "target_node": pair["target_node"],
            "opportunity_type": "",
            "mechanisms": [],
            "source_artifact": "",
            "target_claim": "",
            "expected_effect": [],
            "bounded_check": "",
            "evidence": [],
            "rationale": "",
            "confidence": "",
            "uncertainty_note": None,
        }
        for pair in directed_pairs
    ]
    payloads = {
        "edge_reviewer_bundle.json": _json_bytes(bundle),
        "edge_review_form_template.jsonl": _jsonl_bytes(template),
    }
    payloads["edge_packet_manifest.json"] = _json_bytes({
        "packet_version": EDGE_PACKET_VERSION,
        "case_id": CASE_ID,
        "graph_version": GRAPH_VERSION,
        "input_lock_sha256": bundle["input_lock_sha256"],
        "node_boundary_qc_sha256": _digest(qc_path.read_bytes()),
        "nodes_frozen_sha256": bundle["nodes_frozen_sha256"],
        "candidate_packets_sha256": _digest(packet_path.read_bytes()),
        "builder_sha256": _digest(Path(__file__).read_bytes()),
        "edge_reviewer_bundle_sha256": _digest(payloads["edge_reviewer_bundle.json"]),
        "edge_review_form_template_sha256": _digest(payloads["edge_review_form_template.jsonl"]),
        "directed_pair_count": 30,
        "annotation_status": "ungraded_blind_packet",
    })
    return payloads


def build(directory: Path = EDGE_DIR) -> dict[str, Any]:
    _require(not directory.is_symlink(), "Pilot A edge directory must not be a symlink")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    payloads = render(directory)
    for name, data in payloads.items():
        path = directory / name
        _require(not path.is_symlink() and (not path.exists() or path.read_bytes() == data),
                 f"Pilot A edge packet changed; create a new version: {name}")
        path.write_bytes(data)
        path.chmod(0o600)
    return verify(directory)


def verify(directory: Path = EDGE_DIR) -> dict[str, Any]:
    payloads = render(directory)
    for name, expected in payloads.items():
        path = directory / name
        _require(path.is_file() and not path.is_symlink() and path.read_bytes() == expected,
                 f"Pilot A edge packet changed or missing: {name}")
    return {
        "status": "verified_ungraded_edge_packet",
        "node_count": 6,
        "directed_pair_count": 30,
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
        parser.exit(1, f"Pilot A edge packet error: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
