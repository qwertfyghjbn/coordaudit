"""修正盲化边界后，为 Pilot B 全部新增方向生成第二轮独立边标注包。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from scripts.hidden_opportunity_graph import CASE_ID, GraphValidationError, _read_json, _require
from scripts.prepare_hidden_graph_pilot_b_edges import EDGE_DIR, verify as verify_base


ROUND2_DIR = EDGE_DIR.parent / "edges_round2"
PACKET_VERSION = "pilot-b-complete-new-directed-edge-packet-v2-reblind"
RULES = [
    "只依据冻结源码、v1 GT、safe siblings、validation metadata、规划 §3 和本包固定节点判结构边；不得查看 Pilot A 已标边、首轮 Pilot B 标注或任何历史 run。",
    "先判断 A→B 的最小信息能否改变 B 的具体判断、最小验证路径或必要搜索工作，再判断五级类别；B→A 单独裁决。",
    "共享漏洞类别、文件、目录、helper 名称或被保护对象的宽泛主题不自动产生 actionable；需写出 A 的具体信息、B 的 claim 和可区分正负结果。",
    "非 none 记录至少给 A 与 B 各一处 target-relative 源码引用及准确摘录哈希；none 和 thematic-only 写出不能升档的具体理由。",
    "actionable 已成立但 strong 的必要性不足时归 actionable cross-check；仅在 actionable 边界本身证据不足时保留 uncertainty_note。",
    "完整审查本包列出的 210 个新增有向对，不从 Pilot A 已冻结 30 对推断新边类别。",
]


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def render() -> dict[str, bytes]:
    base = verify_base()
    qc_path = EDGE_DIR / "edge_round1_manual_qc.json"
    _require(qc_path.is_file() and not qc_path.is_symlink(), "missing Pilot B first-round blindness QC")
    qc = _read_json(qc_path)
    _require(qc["status"] == "blindness_protocol_revision_reblind_required"
             and qc["first_round_denominator"] == 210
             and qc["base_edge_packet_manifest_sha256"] == base["edge_packet_manifest_sha256"]
             and qc["base_reviewer_bundle_sha256"] == base["edge_reviewer_bundle_sha256"],
             "Pilot B first-round blindness QC does not match the base packet")
    for role, digest in qc["first_round_review_file_sha256"].items():
        path = EDGE_DIR / "reviews" / f"{role}.jsonl"
        _require(role in {"reviewer_a", "reviewer_b"} and path.is_file() and not path.is_symlink()
                 and _digest(path.read_bytes()) == digest, f"first-round Pilot B review changed: {role}")
    bundle = _read_json(EDGE_DIR / "edge_reviewer_bundle.json")
    _require(len(bundle["directed_pairs_to_review"]) == 210, "Pilot B edge universe changed")
    bundle["packet_version"] = PACKET_VERSION
    bundle["review_instructions"] = (
        "新隔离上下文重新独立审查全部 210 个新增方向；只读本包、冻结 target/v1 GT/safe siblings/validation metadata、"
        "规划 §3 与批准威胁模型。不要读取含 Pilot A 或 Pilot B 边标注结果的文档、首轮 review、"
        "其他标注者文件、历史 run 或 condition 表现。"
    )
    bundle["calibration_rules"] = RULES
    payloads = {
        "edge_reviewer_bundle.json": _json_bytes(bundle),
        "edge_review_form_template.jsonl": (EDGE_DIR / "edge_review_form_template.jsonl").read_bytes(),
        "calibration_rules.json": _json_bytes({"protocol_version": PACKET_VERSION, "rules": RULES}),
    }
    payloads["edge_packet_manifest.json"] = _json_bytes({
        "packet_version": PACKET_VERSION,
        "case_id": CASE_ID,
        "graph_version": bundle["graph_version"],
        "base_edge_packet_manifest_sha256": base["edge_packet_manifest_sha256"],
        "round1_manual_qc_sha256": _digest(qc_path.read_bytes()),
        "builder_sha256": _digest(Path(__file__).read_bytes()),
        "edge_reviewer_bundle_sha256": _digest(payloads["edge_reviewer_bundle.json"]),
        "edge_review_form_template_sha256": _digest(payloads["edge_review_form_template.jsonl"]),
        "calibration_rules_sha256": _digest(payloads["calibration_rules.json"]),
        "new_directed_pair_count": 210,
        "total_directed_pair_count": 240,
        "annotation_status": "ungraded_reblind_new_directed_pairs",
    })
    return payloads


def build() -> dict[str, Any]:
    _require(not ROUND2_DIR.is_symlink(), "unsafe Pilot B edge round 2 directory")
    ROUND2_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    ROUND2_DIR.chmod(0o700)
    payloads = render()
    for name, data in payloads.items():
        path = ROUND2_DIR / name
        _require(not path.is_symlink() and (not path.exists() or path.read_bytes() == data),
                 f"Pilot B round 2 edge packet changed; create a new packet version: {name}")
        path.write_bytes(data)
        path.chmod(0o600)
    return verify()


def verify() -> dict[str, Any]:
    payloads = render()
    for name, data in payloads.items():
        path = ROUND2_DIR / name
        _require(path.is_file() and not path.is_symlink() and path.read_bytes() == data,
                 f"Pilot B round 2 edge packet missing or changed: {name}")
    return {
        "status": "verified_ungraded_reblind_edge_packet",
        "new_directed_pair_count": 210,
        "total_directed_pair_count": 240,
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
        parser.exit(1, f"Pilot B round 2 edge packet error: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
