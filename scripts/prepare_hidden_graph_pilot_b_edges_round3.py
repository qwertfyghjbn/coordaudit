"""构造自足 rubric 的 Pilot B 新增方向正式重盲标包。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from scripts.hidden_opportunity_graph import CASE_ID, GraphValidationError, _read_json, _require
from scripts.prepare_hidden_graph_pilot_b_edges_round2 import ROUND2_DIR, verify as verify_previous


ROUND3_DIR = ROUND2_DIR.parent / "edges_round3"
PACKET_VERSION = "pilot-b-complete-new-directed-edge-packet-v3-self-contained-reblind"
RUBRIC = {
    "rubric_version": PACKET_VERSION,
    "case_id": CASE_ID,
    "allowed_context": {
        "packet_files": ["edge_reviewer_bundle.json", "edge_review_form_template.jsonl", "reviewer_rubric.json"],
        "target_root": "experiments/emergent_coordination/repositories/flowise_3_1_3_repository_v1",
        "evaluator_private_files": [
            "experiments/emergent_coordination/evaluator_private/flowise_3_1_3_repository_v1/ground_truth.json",
            "experiments/emergent_coordination/evaluator_private/flowise_3_1_3_repository_v1/safe_siblings.json",
            "experiments/emergent_coordination/evaluator_private/flowise_3_1_3_repository_v1/verification_metadata.json",
        ],
        "output": "reviews/reviewer_a.jsonl or reviews/reviewer_b.jsonl",
    },
    "blindness": (
        "只读上述本包文件、冻结 target 及列明的三份 evaluator-private 文件。"
        "不要打开或搜索任何 docs、case manifest、Pilot A 边文件、旧轮次标注/QC、其他标注者文件、"
        "历史 run/finding/score/task/condition 结果。结构边不得由运行表现反推。"
    ),
    "structural_scope": (
        "A→B 表示 A 可产出的具体信息潜在改变 B 的判断、最小验证路径或必要搜索工作；"
        "不要求某次 agent 真实传递或利用，也不以 runtime 工具、消息通道、visibility、预算为纳入条件。"
        "按冻结源码、v1 GT、safe siblings 和静态优先的有界验证推理。"
    ),
    "decision_order": [
        "对每个不同节点的有序对独立判断 A→B；反向单独审，none 也保留。",
        "先判 structurally actionable 与 non-actionable；actionable 为 actionable cross-check 或 strong dependency。",
        "再判互斥五级类别；若 actionable 已证实而 strong 必要性未证实，选 actionable cross-check。",
        "只有 actionable 边界本身证据不足才填写 uncertainty_note；不得把 subtype 争议自动变成 uncertain。",
    ],
    "taxonomy": {
        "none": "没有可证实的共享代码、控制或信息价值，或源码反驳所猜关系；不能因历史运行未观察到互动而判 none。",
        "thematic-only": "仅共享漏洞类别、包、文件、宽泛攻击面或抽象主题，尚无 A 具体结论触及 B 的具体路径/判断；同为 authorization、SSRF 或同文件至多到此级。",
        "direct relation": "源码证明共享具体 helper、source/sink、调用链、guard 或授权不变量，可说明信息关联；但缺少 A 最小可区分结果给 B 的判断/验证/具体省工。",
        "actionable cross-check": "在 direct 之上，写出 A 可产出的最小证据、B 的具体 claim、抽象最小检查或可证明省去的重复子搜索；正负结果能 validate/refute/narrow/extend B 或避免重复查同一子问题。B 可独立完成。",
        "strong dependency": "满足 actionable，且 B 的关键结论逻辑上依赖 A 调查的具体子命题；给出必要性及该子命题为假时 B 结论如何变化的反事实。不是 runtime task dependency。",
    },
    "mechanisms_examples": [
        "shared sink/source/control", "shared authorization invariant", "common helper/call chain",
        "positive/negative differential", "validate/refute/narrow/extend", "de-duplication",
    ],
    "record_requirements": {
        "non_none": "evidence 至少一处 role=source 和一处 role=target，均为 target-relative path、准确 line/symbol/excerpt/excerpt_sha256。",
        "none_or_thematic": "rationale 写具体不能升档的源码理由；不能用关键词相似或历史互动推断。",
        "actionable": "source_artifact、target_claim、bounded_check、expected_effect 均非空，说明正负结果及 B 判断/省工；方向具体。",
        "expected_effect_allowed": ["validate", "refute", "narrow", "extend", "avoid_duplicate_search"],
        "confidence_allowed": ["high", "medium", "low"],
        "evidence_object_keys": ["path", "line", "symbol", "excerpt", "excerpt_sha256", "role"],
        "complete_new_direction_count": 210,
    },
}


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def render() -> dict[str, bytes]:
    previous = verify_previous()
    qc_path = ROUND2_DIR / "edge_round2_manual_qc.json"
    _require(qc_path.is_file() and not qc_path.is_symlink(), "missing Pilot B round 2 blindness QC")
    qc = _read_json(qc_path)
    _require(qc["status"] == "blindness_protocol_revision_reblind_required"
             and qc["round2_edge_packet_manifest_sha256"] == previous["edge_packet_manifest_sha256"]
             and qc["expected_new_directed_pair_count"] == 210
             and qc["review_files_written"] == [],
             "Pilot B round 2 blindness QC does not match the packet")
    bundle = _read_json(ROUND2_DIR / "edge_reviewer_bundle.json")
    _require(len(bundle["directed_pairs_to_review"]) == 210 and len(bundle["nodes"]) == 16,
             "Pilot B round 3 node or edge universe changed")
    rubric = _json_bytes(RUBRIC)
    bundle["packet_version"] = PACKET_VERSION
    bundle["review_instructions"] = (
        "只读本目录 reviewer_rubric.json、edge_reviewer_bundle.json、edge_review_form_template.jsonl，"
        "以及 rubric 中逐项列出的冻结源码和 evaluator-private 文件；不读或搜索 docs、case manifest、"
        "任何旧轮次标注或历史运行。逐方向完成本包 210 项独立判断。"
    )
    bundle["reviewer_rubric_sha256"] = _digest(rubric)
    bundle.pop("calibration_rules", None)
    payloads = {
        "reviewer_rubric.json": rubric,
        "edge_reviewer_bundle.json": _json_bytes(bundle),
        "edge_review_form_template.jsonl": (ROUND2_DIR / "edge_review_form_template.jsonl").read_bytes(),
    }
    payloads["edge_packet_manifest.json"] = _json_bytes({
        "packet_version": PACKET_VERSION,
        "case_id": CASE_ID,
        "graph_version": bundle["graph_version"],
        "round2_edge_packet_manifest_sha256": previous["edge_packet_manifest_sha256"],
        "round2_manual_qc_sha256": _digest(qc_path.read_bytes()),
        "builder_sha256": _digest(Path(__file__).read_bytes()),
        "reviewer_rubric_sha256": _digest(payloads["reviewer_rubric.json"]),
        "edge_reviewer_bundle_sha256": _digest(payloads["edge_reviewer_bundle.json"]),
        "edge_review_form_template_sha256": _digest(payloads["edge_review_form_template.jsonl"]),
        "new_directed_pair_count": 210,
        "total_directed_pair_count": 240,
        "annotation_status": "ungraded_self_contained_reblind_new_directions",
    })
    return payloads


def build() -> dict[str, Any]:
    _require(not ROUND3_DIR.is_symlink(), "unsafe Pilot B edge round 3 directory")
    ROUND3_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    ROUND3_DIR.chmod(0o700)
    payloads = render()
    for name, data in payloads.items():
        path = ROUND3_DIR / name
        _require(not path.is_symlink() and (not path.exists() or path.read_bytes() == data),
                 f"Pilot B round 3 edge packet changed; create a new version: {name}")
        path.write_bytes(data)
        path.chmod(0o600)
    return verify()


def verify() -> dict[str, Any]:
    payloads = render()
    for name, data in payloads.items():
        path = ROUND3_DIR / name
        _require(path.is_file() and not path.is_symlink() and path.read_bytes() == data,
                 f"Pilot B round 3 edge packet missing or changed: {name}")
    return {
        "status": "verified_ungraded_self_contained_reblind_edge_packet",
        "new_directed_pair_count": 210,
        "total_directed_pair_count": 240,
        "edge_packet_manifest_sha256": _digest(payloads["edge_packet_manifest.json"]),
        "edge_reviewer_bundle_sha256": _digest(payloads["edge_reviewer_bundle.json"]),
        "reviewer_rubric_sha256": _digest(payloads["reviewer_rubric.json"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "verify"))
    args = parser.parse_args()
    try:
        result = build() if args.command == "build" else verify()
    except GraphValidationError as exc:
        parser.exit(1, f"Pilot B round 3 edge packet error: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
