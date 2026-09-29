"""在首轮 QC 未过后，生成版本化且无首轮标签的 Pilot A 重盲标包。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from scripts.hidden_opportunity_graph import CASE_ID, GRAPH_VERSION, GraphValidationError, _require
from scripts.prepare_hidden_graph_pilot_a import PILOT_DIR
from scripts.prepare_hidden_graph_pilot_a_edges import EDGE_DIR, render as render_round1


ROUND2_DIR = PILOT_DIR / "edges_round2"
ROUND2_VERSION = "pilot-a-directed-edge-packet-v2-calibrated"
CALIBRATION_RULES = [
    "先说明 A 在自身调查范围内能够产出的最小字段、谓词、返回值或 guard 结论，再指出 B 尚待判断的具体 claim；两个节点使用相似词汇本身不构成信息价值。",
    "actionable 的 bounded_check 必须定位 B 的入口或消费点、具体待比对字段/谓词/顺序，并分别解释 A 证据为正和为负时 B 的判断或必要搜索工作如何改变；泛称‘再读 B 代码’不足够。",
    "若 A 只提供类比，而 B 的结论仍完全由另一条无交集的源码路径独立决定，不判 actionable；根据具体连接证据落到 direct relation 或 thematic-only。",
    "direct relation 要求共同的具体实体字段、调用符号、数据交接、相同安全不变量上的精确谓词对照或同一控制点；只有供应商、子系统、文件或风险类别相同属于 thematic-only。",
    "两个方向分别判。安全路径的 guard 只证明该窄路径；传到其他路径时仍须核对目标入口和谓词，另一条路径缺 guard 也不自动推翻已限定的安全结论。",
    "源码能证明返回值或字段可形成候选信息通道时，单列条件与缺失事实；外部对象形状、ID 获知、持久化约束和运行中命中条件不由结构边自动证明。证据不足以确定 actionable 边界时填写 uncertainty_note。",
    "strong dependency 还须锁定 B 的精确子命题并证明 A 的具体子命题是其关键结论所需的前提；只加速或提供对照时归 actionable cross-check。",
    "每条非 none 边保留 A/B 双侧冻结源码位置与 excerpt SHA-256；机器提出的共享路径、符号和检查不是已裁定关系。",
]


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def render(directory: Path = ROUND2_DIR) -> dict[str, bytes]:
    _require(not directory.is_symlink() and directory.resolve() == ROUND2_DIR.resolve(),
             "Pilot A round 2 must use its locked private directory")
    base = render_round1(EDGE_DIR)
    previous_qc_path = EDGE_DIR / "edge_round1_qc.json"
    _require(previous_qc_path.is_file() and not previous_qc_path.is_symlink(), "missing first-round QC record")
    previous_qc = json.loads(previous_qc_path.read_text(encoding="utf-8"))
    _require(previous_qc["status"] == "qc_failed_reblind_required"
             and previous_qc["binary_agreement_count"] < 27, "first-round QC did not require reblind")
    bundle = json.loads(base["edge_reviewer_bundle.json"])
    _require(len(bundle["directed_pairs"]) == 30, "round 2 must cover all 30 directions")
    bundle["packet_version"] = ROUND2_VERSION
    bundle["review_instructions"] = (
        "对完整 30 个方向重新独立盲标；先按以下中性规则判 actionable/non-actionable，再判五类 subtype。"
        "不要查看第一轮记录、裁决、QC、历史 T4 或 condition 表现。"
    )
    bundle["calibration_rules"] = CALIBRATION_RULES
    rules = {"protocol_version": ROUND2_VERSION, "rules": CALIBRATION_RULES}
    payloads = {
        "edge_reviewer_bundle.json": _json_bytes(bundle),
        "edge_review_form_template.jsonl": base["edge_review_form_template.jsonl"],
        "calibration_rules.json": _json_bytes(rules),
    }
    payloads["edge_packet_manifest.json"] = _json_bytes({
        "packet_version": ROUND2_VERSION,
        "case_id": CASE_ID,
        "graph_version": GRAPH_VERSION,
        "input_lock_sha256": bundle["input_lock_sha256"],
        "nodes_frozen_sha256": bundle["nodes_frozen_sha256"],
        "round1_failed_qc_sha256": _digest(previous_qc_path.read_bytes()),
        "base_ungraded_packet_sha256": _digest(base["edge_reviewer_bundle.json"]),
        "calibration_rules_sha256": _digest(payloads["calibration_rules.json"]),
        "builder_sha256": _digest(Path(__file__).read_bytes()),
        "edge_reviewer_bundle_sha256": _digest(payloads["edge_reviewer_bundle.json"]),
        "edge_review_form_template_sha256": _digest(payloads["edge_review_form_template.jsonl"]),
        "directed_pair_count": 30,
        "annotation_status": "ungraded_reblind_packet",
    })
    return payloads


def build(directory: Path = ROUND2_DIR) -> dict[str, Any]:
    _require(not directory.is_symlink(), "Pilot A round 2 directory must not be a symlink")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    payloads = render(directory)
    for name, data in payloads.items():
        path = directory / name
        _require(not path.is_symlink() and (not path.exists() or path.read_bytes() == data),
                 f"round 2 packet changed; create a new version: {name}")
        path.write_bytes(data)
        path.chmod(0o600)
    return verify(directory)


def verify(directory: Path = ROUND2_DIR) -> dict[str, Any]:
    payloads = render(directory)
    for name, expected in payloads.items():
        path = directory / name
        _require(path.is_file() and not path.is_symlink() and path.read_bytes() == expected,
                 f"Pilot A round 2 packet changed or missing: {name}")
    return {
        "status": "verified_ungraded_reblind_packet",
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
        parser.exit(1, f"Pilot A round 2 edge packet error: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
