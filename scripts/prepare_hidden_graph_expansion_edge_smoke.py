#!/usr/bin/env python3
"""Build the non-production smoke reviewer packet for expansion structural edges."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from scripts.freeze_hidden_graph_pair_universe import (
    CASE_DIR,
    GRAPH_DIR,
    NODE_SET_DIR,
    NODE_SET_VERSION,
    OUT_DIR as PAIR_UNIVERSE_DIR,
    PAIR_CLASSES,
    PAIR_UNIVERSE_VERSION,
    digest,
    jbytes,
    jlbytes,
    verify as verify_pair_universe,
)
from scripts.hidden_opportunity_graph import (
    CASE_ID,
    PILOT_B_GRAPH_DIR,
    PRIVATE_GRAPH_DIR,
    _read_json,
    _read_jsonl,
    _require,
)


SMOKE_DIR = CASE_DIR / "expansion-edge-smoke-v1"
PACKET_VERSION = "expansion-edge-smoke-packet-v1-infrastructure-validation"
TARGET_ROOT = "experiments/emergent_coordination/repositories/flowise_3_1_3_repository_v1"
EVALUATOR_PRIVATE_FILES = [
    "experiments/emergent_coordination/evaluator_private/flowise_3_1_3_repository_v1/ground_truth.json",
    "experiments/emergent_coordination/evaluator_private/flowise_3_1_3_repository_v1/safe_siblings.json",
    "experiments/emergent_coordination/evaluator_private/flowise_3_1_3_repository_v1/verification_metadata.json",
]
SELECTION_RULE = (
    "在冻结的 462-pair universe 内，按 pair_class 分组后以 pair_id 字典序排序，每组取索引 0 与 "
    "len(group)//2 两项，共 6 对。规则只依赖 pair_id（由冻结节点 ID 派生），不使用历史 edge 标签、"
    "actionability、T4 协作记录或任何 run 表现。"
)


def select_smoke_pairs(universe: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected = []
    for name in PAIR_CLASSES:
        group = sorted((row for row in universe if row["pair_class"] == name),
                       key=lambda row: row["pair_id"])
        _require(len(group) >= 2, f"pair class too small to sample: {name}")
        for index in sorted({0, len(group) // 2}):
            selected.append({**group[index], "index_in_class": index, "class_size": len(group)})
    return sorted(selected, key=lambda row: row["pair_id"])


def rubric_payload() -> bytes:
    return jbytes({
        "rubric_version": PACKET_VERSION,
        "case_id": CASE_ID,
        "annotation_status": "non_production_infrastructure_validation_only",
        "allowed_context": {
            "packet_files": [
                "reviewer_rubric.json",
                "edge_reviewer_bundle.json",
                "edge_review_form_template.jsonl",
                "smoke_packet_manifest.json",
            ],
            "target_root": TARGET_ROOT,
            "evaluator_private_files": EVALUATOR_PRIVATE_FILES,
            "output": "reviews/reviewer_a.jsonl or reviews/reviewer_b.jsonl",
            "access_log": "reviews/reviewer_a_access.json or reviews/reviewer_b_access.json",
        },
        "blindness": (
            "只读上述本包文件、冻结 target 源码树及列明的三份 evaluator-private 文件。"
            "不要打开或搜索任何 docs、case manifest、graph-v1/graph-v2 的已冻结节点/边标注、"
            "Pilot A/Pilot B/expansion 任何旧轮次标注或 QC、其他标注者文件、scripts、tests、"
            "experiments/emergent_coordination/runs/、历史 run/finding/score/task/condition 结果。"
            "结构边不得由运行表现反推。不要做全仓检索。"
        ),
        "non_production_notice": (
            "本包只验证 reviewer 材料与执行链。输出的任何判断都不得并入正式 462-pair 标注；"
            "正式阶段将对包括这 6 对在内的全部 pair 重新独立盲标。"
        ),
        "structural_scope": (
            "A→B 表示 A 可产出的具体信息潜在改变 B 的判断、最小验证路径或必要搜索工作；"
            "不要求某次 agent 真实传递或利用，也不以 runtime 工具、消息通道、visibility、预算为纳入条件。"
            "按冻结源码、v1 GT、safe siblings 和静态优先的有界验证推理；"
            "condition-specific operational realizability（某条件下的运行可实现性）不属于本次判断。"
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
            "smoke_pair_count": 6,
            "non_none": "evidence 至少一处 role=source 和一处 role=target，均为 target-relative path、准确 line/symbol/excerpt/excerpt_sha256。",
            "none_or_thematic": "rationale 写具体不能升档的源码理由；不能用关键词相似或历史互动推断。",
            "actionable": "source_artifact、target_claim、bounded_check、expected_effect 均非空，说明正负结果及 B 判断/省工；方向具体。",
            "expected_effect_allowed": ["validate", "refute", "narrow", "extend", "avoid_duplicate_search"],
            "confidence_allowed": ["high", "medium", "low"],
            "evidence_object_keys": ["path", "line", "symbol", "excerpt", "excerpt_sha256", "role"],
            "excerpt_hash_rule": "excerpt 是从 line 起的原样源码行片段；excerpt_sha256 = 该片段 UTF-8 字节的 SHA-256；校验器要求片段在目标文件指定行精确出现。",
        },
    })


def render() -> dict[str, bytes]:
    universe_status = verify_pair_universe()
    _require(universe_status["status"] == "verified_frozen_pairs_only_unannotated"
             and universe_status["pair_universe_manifest_sha256"]
             == digest((PAIR_UNIVERSE_DIR / "pair_universe_manifest.json").read_bytes()),
             "frozen pair universe does not match the smoke packet basis")
    universe = _read_jsonl(PAIR_UNIVERSE_DIR / "pair_universe.jsonl")
    _require(len(universe) == 462, "pair universe size changed")
    selected = select_smoke_pairs(universe)
    _require(len(selected) == 6 and {row["pair_class"] for row in selected} == set(PAIR_CLASSES)
             and len({row["pair_id"] for row in selected}) == 6,
             "smoke selection must cover three pair classes with six distinct pairs")
    nodes = _read_jsonl(NODE_SET_DIR / "nodes_frozen.jsonl")
    _require(len(nodes) == 27, "frozen node set size changed")
    by_id = {node["node_id"]: node for node in nodes}
    pairs = []
    for row in selected:
        source, target = by_id[row["source_node"]], by_id[row["target_node"]]
        shared_paths = sorted(set(source["code_scope"]) & set(target["code_scope"]))
        shared_symbols = sorted({ref["symbol"] for ref in source["evidence_refs"]}
                                & {ref["symbol"] for ref in target["evidence_refs"]})
        pairs.append({
            "pair_id": row["pair_id"],
            "source_node": row["source_node"],
            "target_node": row["target_node"],
            "pair_class": row["pair_class"],
            "source_artifact_candidate": source["potential_artifact"],
            "target_claim_candidate": target["security_question"],
            "bounded_check_candidate": (
                "核对共同源码位置/符号在 B 的消费点和正负结果；共享本身不定级。"
                if shared_paths or shared_symbols else
                "追踪 A 的最小信息是否触及 B 的具体 guard、source/sink、归属或必要搜索工作。"
            ),
            "shared_code_paths": shared_paths,
            "shared_symbols": shared_symbols,
            "candidate_status": "ungraded_smoke_subset",
        })
    rubric = rubric_payload()
    bundle = {
        "packet_version": PACKET_VERSION,
        "case_id": CASE_ID,
        "base_graph_version": "graph-v2",
        "pair_universe_version": PAIR_UNIVERSE_VERSION,
        "pair_universe_manifest_sha256": universe_status["pair_universe_manifest_sha256"],
        "pair_universe_pairs_sha256": universe_status["pairs_sha256"],
        "node_set_version": NODE_SET_VERSION,
        "node_set_manifest_sha256": universe_status["node_set_manifest_sha256"],
        "nodes_frozen_sha256": digest((NODE_SET_DIR / "nodes_frozen.jsonl").read_bytes()),
        "annotation_status": "non_production_infrastructure_validation_only",
        "review_instructions": (
            "只读本目录 reviewer_rubric.json、edge_reviewer_bundle.json、edge_review_form_template.jsonl，"
            "以及 rubric 中列出的冻结源码树和 evaluator-private 文件；不读或搜索 docs、case manifest、"
            "graph-v1/graph-v2 已冻结标注、任何旧轮次标注/QC、其他标注者文件、scripts、tests 或历史运行。"
            "只审 bundle 中 smoke_directed_pairs 列出的 6 个有向对；按模板逐行填写并保存为 "
            "reviews/reviewer_<你的代号>.jsonl，同时把实际打开过的文件按 repo 相对路径写入 "
            "reviews/reviewer_<你的代号>_access.json。"
        ),
        "nodes": nodes,
        "smoke_directed_pairs": pairs,
    }
    bundle_data = jbytes(bundle)
    template = [{
        "reviewer_id": "", "source_node": pair["source_node"], "target_node": pair["target_node"],
        "opportunity_type": "", "mechanisms": [], "source_artifact": "", "target_claim": "",
        "expected_effect": [], "bounded_check": "", "evidence": [], "rationale": "",
        "confidence": "", "uncertainty_note": None,
    } for pair in pairs]
    template_data = jlbytes(template)
    frozen_edge_ids = [edge["edge_id"] for edge in _read_jsonl(PRIVATE_GRAPH_DIR / "edges.jsonl")]
    frozen_edge_ids += [edge["edge_id"] for edge in _read_jsonl(GRAPH_DIR / "edges.jsonl")]
    packet_text = rubric + bundle_data + template_data
    leaked = [edge_id for edge_id in frozen_edge_ids if edge_id.encode() in packet_text]
    _require(not leaked, f"smoke packet leaks frozen edge IDs: {leaked[:3]}")
    _require(all(pair["candidate_status"] == "ungraded_smoke_subset" for pair in pairs)
             and '"opportunity_type": ""' in template_data.decode(),
             "smoke packet must not embed any edge judgment")
    manifest = {
        "packet_version": PACKET_VERSION,
        "case_id": CASE_ID,
        "annotation_status": "non_production_infrastructure_validation_only",
        "pair_universe_version": PAIR_UNIVERSE_VERSION,
        "pair_universe_manifest_sha256": universe_status["pair_universe_manifest_sha256"],
        "pairs_sha256": universe_status["pairs_sha256"],
        "node_set_manifest_sha256": universe_status["node_set_manifest_sha256"],
        "base_graph_version": "graph-v2",
        "base_graph_manifest_sha256": digest((GRAPH_DIR / "graph_manifest.json").read_bytes()),
        "selection_rule": SELECTION_RULE,
        "selected_pairs": [
            {"pair_id": row["pair_id"], "pair_class": row["pair_class"],
             "index_in_class": row["index_in_class"], "class_size": row["class_size"]}
            for row in selected
        ],
        "smoke_pair_count": 6,
        "smoke_pair_class_coverage": {name: sum(row["pair_class"] == name for row in selected)
                                      for name in PAIR_CLASSES},
        "label_policy": "no_edge_labels_included",
        "reuse_statement": (
            "smoke 输出仅验证材料与执行链，不并入正式标注；正式阶段对全部 462 对（含这 6 对）重新独立盲标。"
        ),
        "reviewer_rubric_sha256": digest(rubric),
        "edge_reviewer_bundle_sha256": digest(bundle_data),
        "edge_review_form_template_sha256": digest(template_data),
        "builder_sha256": digest(Path(__file__).read_bytes()),
    }
    return {
        "reviewer_rubric.json": rubric,
        "edge_reviewer_bundle.json": bundle_data,
        "edge_review_form_template.jsonl": template_data,
        "smoke_packet_manifest.json": jbytes(manifest),
    }


def build() -> dict[str, Any]:
    _require(not SMOKE_DIR.is_symlink(), "unsafe smoke packet directory")
    SMOKE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    SMOKE_DIR.chmod(0o700)
    payloads = render()
    for name, data in payloads.items():
        path = SMOKE_DIR / name
        _require(not path.is_symlink() and (not path.exists() or path.read_bytes() == data),
                 f"smoke packet changed; create a new version: {name}")
        path.write_bytes(data)
        path.chmod(0o600)
    return verify()


def verify() -> dict[str, Any]:
    payloads = render()
    for name, data in payloads.items():
        path = SMOKE_DIR / name
        _require(path.is_file() and not path.is_symlink() and path.read_bytes() == data,
                 f"smoke packet missing or changed: {name}")
    return {
        "status": "verified_non_production_smoke_packet",
        "packet_version": PACKET_VERSION,
        "smoke_packet_manifest_sha256": digest(payloads["smoke_packet_manifest.json"]),
        "smoke_pair_count": 6,
        "selected_pair_ids": [row["pair_id"] for row in _read_json(SMOKE_DIR / "smoke_packet_manifest.json")["selected_pairs"]],
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
