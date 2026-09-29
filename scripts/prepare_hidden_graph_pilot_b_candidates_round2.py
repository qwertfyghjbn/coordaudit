"""在候选资格规则澄清后，生成无首轮标签的 Pilot B 整批重盲标包。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from scripts.hidden_opportunity_graph import CASE_ID, GraphValidationError, _read_json, _require
from scripts.prepare_hidden_graph_pilot_b_candidates import PREP_DIR, verify as verify_base


ROUND2_DIR = PREP_DIR / "round2"
PACKET_VERSION = "pilot-b-source-stratified-candidates-v2-reblind"
RULES = [
    "调查单元是可独立推进、可得出正或负结论的有界安全问题；路径在冻结源码中被证明安全，本身不构成排除理由。",
    "对 scored root、qualified near miss 和 bounded unscored question 使用同一节点资格标准：明确被保护对象与不变量、入口到 sink/guard/归属点的必要链、独立可裁决的正负结论。GT 身份和单个锚点都不自动授予资格。",
    "安全 sibling 只在完整窄范围链成立、且与现有节点可独立得出不同真值时可成为节点；仅作另一路径的局部 guard 或无独立结论的问题只作 contrast evidence。",
    "共享文件、helper、漏洞类别或相同安全词汇不决定合并；也不能因两个路径结论都安全或都不安全就合并。写清一方结论为真/假而另一方仍可相反的反事实。",
    "文件/存储候选是未预断真值的有界问题；临时上传、持久写入与读取对象分别审，不把一个入口的安全检查外推到所有入口。",
    "逐条核对 target-relative path、实际函数/symbol、源码 excerpt 与 SHA-256；GT 的 symbol 仅是定位提示，若与冻结源码不一致，以源码为准并记录修正。",
    "先判断 21 项资格，再按每层至多两项抽样；抽样额度或历史 T4 行为都不得决定纳入资格。",
]
CORRECTED_SYMBOLS = {
    "R02_org_user_password_serialization": "OrganizationUserService.readOrganizationUserByUserId",
}


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _jsonl_bytes(values: list[dict[str, Any]]) -> bytes:
    return b"".join((json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8") for value in values)


def render() -> dict[str, bytes]:
    base = verify_base()
    qc_path = PREP_DIR / "node_round1_manual_qc.json"
    _require(qc_path.is_file() and not qc_path.is_symlink(), "missing first-round semantic QC record")
    qc = _read_json(qc_path)
    _require(qc["status"] == "calibration_revision_reblind_required"
             and qc["candidate_count"] == 21
             and qc["reviewer_bundle_sha256"] == base["reviewer_bundle_sha256"],
             "first-round semantic QC did not require a reblind")
    bundle = _read_json(PREP_DIR / "reviewer_bundle.json")
    pool = [json.loads(line) for line in (PREP_DIR / "candidate_pool.jsonl").read_text(encoding="utf-8").splitlines()]
    _require([item["candidate_id"] for item in bundle["candidates"]]
             == [item["candidate_id"] for item in pool], "base Pilot B candidate order changed")
    for item in pool:
        if item["candidate_id"] in CORRECTED_SYMBOLS:
            _require(item["anchor"]["symbol"] == "OrganizationUserService.getAllOrganizationUsers",
                     "R02 source hint changed before correction")
            item["anchor"]["symbol"] = CORRECTED_SYMBOLS[item["candidate_id"]]
    bundle["candidates"] = pool
    bundle["packet_version"] = PACKET_VERSION
    bundle["review_instructions"] = (
        "重新独立审查全部 21 项。只读此更新包与冻结 target、v1 GT、safe siblings、validation metadata 和批准威胁模型；"
        "不读第一轮记录、裁决、QC、历史 run 或其他标注者文件。"
    )
    bundle["calibration_rules"] = RULES
    payloads = {
        "candidate_pool.jsonl": _jsonl_bytes(pool),
        "reviewer_bundle.json": _json_bytes(bundle),
        "node_review_form_template.jsonl": (PREP_DIR / "node_review_form_template.jsonl").read_bytes(),
        "calibration_rules.json": _json_bytes({"protocol_version": PACKET_VERSION, "rules": RULES}),
    }
    payloads["packet_manifest.json"] = _json_bytes({
        "packet_version": PACKET_VERSION,
        "case_id": CASE_ID,
        "base_packet_manifest_sha256": base["packet_manifest_sha256"],
        "round1_manual_qc_sha256": _digest(qc_path.read_bytes()),
        "source_symbol_corrections": CORRECTED_SYMBOLS,
        "builder_sha256": _digest(Path(__file__).read_bytes()),
        "candidate_pool_sha256": _digest(payloads["candidate_pool.jsonl"]),
        "reviewer_bundle_sha256": _digest(payloads["reviewer_bundle.json"]),
        "node_review_form_template_sha256": _digest(payloads["node_review_form_template.jsonl"]),
        "calibration_rules_sha256": _digest(payloads["calibration_rules.json"]),
        "candidate_count": len(pool),
        "annotation_status": "ungraded_reblind_candidate_pool",
    })
    return payloads


def build() -> dict[str, Any]:
    _require(not ROUND2_DIR.is_symlink(), "unsafe Pilot B round 2 directory")
    ROUND2_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    ROUND2_DIR.chmod(0o700)
    payloads = render()
    for name, data in payloads.items():
        path = ROUND2_DIR / name
        _require(not path.is_symlink() and (not path.exists() or path.read_bytes() == data),
                 f"Pilot B round 2 packet changed; create a new version: {name}")
        path.write_bytes(data)
        path.chmod(0o600)
    return verify()


def verify() -> dict[str, Any]:
    payloads = render()
    for name, data in payloads.items():
        path = ROUND2_DIR / name
        _require(path.is_file() and not path.is_symlink() and path.read_bytes() == data,
                 f"Pilot B round 2 packet missing or changed: {name}")
    return {
        "status": "verified_ungraded_reblind_candidate_pool",
        "candidate_count": 21,
        "packet_manifest_sha256": _digest(payloads["packet_manifest.json"]),
        "reviewer_bundle_sha256": _digest(payloads["reviewer_bundle.json"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "verify"))
    args = parser.parse_args()
    try:
        result = build() if args.command == "build" else verify()
    except GraphValidationError as exc:
        parser.exit(1, f"Pilot B reblind packet error: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
