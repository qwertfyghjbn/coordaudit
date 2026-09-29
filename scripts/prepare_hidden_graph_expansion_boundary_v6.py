#!/usr/bin/env python3
"""Blind, targeted node-identity recheck after coordinator GT-alignment audit."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from scripts.prepare_hidden_graph_expansion_boundary_v5 import render as render_v5

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "artifacts/hidden_opportunity_graph/flowise_3_1_3_repository_v1/expansion-boundary-prep-v6-identity-recheck"
VERSION = "repository-v1-expansion-boundary-v6-identity-recheck-blind"
AFFECTED = ("C01", "C04", "C11")
QUESTIONS = {
    "C01": "变量导出链除了 workspace 过滤以外，是否把受保护的 Variable 值以明文放进 export 响应？独立裁决值遮盖/导出不变量。",
    "C04": "chat-messages 的 GET/DELETE 路由是否有动作权限中间件？区分路由权限与下游 chatflow workspace/object guard。",
    "C11": "外部 overrideConfig.sessionId/chatId 是否先被限制为标量字符串再流入 memory/query key？区分类型约束与会话归属问题。",
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def jbytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def jlbytes(values: list[dict[str, Any]]) -> bytes:
    return b"".join((json.dumps(v, ensure_ascii=False, sort_keys=True) + "\n").encode() for v in values)


def render() -> dict[str, bytes]:
    v5 = render_v5()
    bundle = json.loads(v5["reviewer_bundle.json"])
    forms = [json.loads(line) for line in v5["boundary_review_form_template.jsonl"].decode().splitlines()]
    bundle["packet_version"] = VERSION
    bundle["review_instructions"] = (
        "仅对 C01/C04/C11 作源码身份再核对：审查本包提出的另一安全不变量是否是该锚点的独立 bounded question，"
        "然后重新审其与全部 F/C 的 split/merge。保留其他八项先前独立审查；不得读取旧标注。"
    )
    bundle["identity_recheck_questions"] = QUESTIONS
    bundle["candidates"] = [c for c in bundle["candidates"] if c["candidate_id"] in AFFECTED]
    bundle["comparison_target_candidate_ids"] = [f"C{i:02d}" for i in range(1, 12)]
    bundle["calibration_rules"] = list(bundle["calibration_rules"]) + [
        "本包只重审三个候选的安全问题身份及其 26 个比较目标；其余八项不得改写。",
        "可裁为原问题、建议的新问题或 uncertain；若同一锚点包含两个独立问题，明确说明两个问题及所需单独资格审定。",
        "问题身份与边界证据须来自冻结 target，不依赖 GT 身份、历史运行或先前 reviewer 的标签。",
    ]
    forms = [f for f in forms if f["candidate_id"] in AFFECTED]
    payloads = {
        "reviewer_bundle.json": jbytes(bundle),
        "boundary_review_form_template.jsonl": jlbytes(forms),
        "calibration_rules.json": jbytes({"packet_version": VERSION, "rules": bundle["calibration_rules"]}),
    }
    manifest = {
        "packet_version": VERSION,
        "case_id": bundle["case_id"],
        "base_graph_manifest_sha256": bundle["base_graph_manifest_sha256"],
        "source_v5_packet_manifest_sha256": digest(v5["packet_manifest.json"]),
        "affected_candidate_ids": list(AFFECTED),
        "review_form_row_count": len(forms),
        "builder_sha256": digest(Path(__file__).read_bytes()),
        "reviewer_bundle_sha256": digest(payloads["reviewer_bundle.json"]),
        "review_form_sha256": digest(payloads["boundary_review_form_template.jsonl"]),
        "calibration_rules_sha256": digest(payloads["calibration_rules.json"]),
        "status": "ungraded_targeted_identity_recheck",
    }
    payloads["packet_manifest.json"] = jbytes(manifest)
    return payloads


def verify() -> dict[str, Any]:
    payloads = render()
    for name, data in payloads.items():
        path = DIR / name
        if not path.is_file() or path.is_symlink() or path.read_bytes() != data:
            raise ValueError(f"v6 identity recheck packet missing or changed: {name}")
    bundle = json.loads(payloads["reviewer_bundle.json"])
    if any(key in json.dumps(bundle, ensure_ascii=False).lower() for key in ("truth_status", "gt_root_ids", "near_miss_ids", "source_kind")):
        raise ValueError("v6 packet leaks evaluator labels")
    return {"status": "verified_ungraded_targeted_identity_recheck",
            "affected_candidate_ids": list(AFFECTED),
            "packet_manifest_sha256": digest(payloads["packet_manifest.json"]),
            "base_graph_manifest_sha256": bundle["base_graph_manifest_sha256"]}


def build() -> dict[str, Any]:
    DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    DIR.chmod(0o700)
    for name, data in render().items():
        path = DIR / name
        if path.exists() and path.read_bytes() != data:
            raise ValueError(f"v6 packet changed; use a new version: {name}")
        path.write_bytes(data)
        path.chmod(0o600)
    return verify()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("build", "verify"))
    args = parser.parse_args()
    print(json.dumps(build() if args.command == "build" else verify(), ensure_ascii=False, sort_keys=True))
