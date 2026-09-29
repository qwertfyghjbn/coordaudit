#!/usr/bin/env python3
"""Plan deterministic label-blind annotation batches for the frozen 462-pair universe."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from datetime import date
from pathlib import Path
from typing import Any

from scripts.freeze_hidden_graph_pair_universe import (
    CASE_DIR,
    PAIR_CLASSES,
    PAIR_UNIVERSE_VERSION,
    digest,
    jbytes,
    jlbytes,
    verify as verify_pair_universe,
)
from scripts.hidden_opportunity_graph import CASE_ID, GraphValidationError, _read_json, _read_jsonl, _require


BATCH_PLAN_VERSION = "expansion-edge-batch-plan-v1"
OUT_DIR = CASE_DIR / "expansion-edge-batches-v1"
BATCH_COUNT = 7
BATCH_SIZE = 66
# 固定类别处理顺序：先给 new_to_old 派余数，再 new_to_new，最后 old_to_new；
# 每个余数槽给当前累计总量最小、平手取最小编号的 batch。该顺序是纯机械约定。
EXTRA_CLASS_ORDER = ("new_to_old", "new_to_new", "old_to_new")
ALGORITHM = {
    "name": "canonical-order serpentine dealing with mechanically derived class quotas",
    "steps": [
        "1. 读取冻结 pair_universe.jsonl；每个 pair_class 内按 pair_id 字典序升序（canonical order）。",
        "2. 7 个 batch（edge-annotation-batch-01..07），每批目标 66 对。",
        "3. 每类 base = N_class // 7，extras = N_class % 7；按固定类别顺序 (new_to_old, new_to_new, old_to_new) "
        "逐类派发 extras，每个 extra 给当前各类已分配总量最小且编号最小的 batch（平手取最小编号）。",
        "4. 类内按 pair_id 顺序做蛇形轮发：偶数轮按 batch 01→07、奇数轮按 07→01，跳过该类配额已满的 batch；"
        "蛇形用于打散纯升序轮发造成的 mod-7 residue 对齐（该对齐会把同一无序节点对的双方向集中到单个 batch）。",
    ],
    "label_blindness": (
        "分配只使用 pair_id、source/target node ID、pair_class 与批次算术；不使用任何机会类型猜测、"
        "Pilot A/B 历史 edge 标签、T4/P/B/S/M 行为、actionability、verification 或 Stage 9 结果。"
    ),
    "derived_quota_note": (
        "唯一能使 7 批都恰为 66 的类别配额组合是 5×(25,25,16) + 1×(26,25,15) + 1×(25,26,15)；"
        "步骤 3 的机械规则自动产出：batch-01=(25,26,15)、batch-02..06=(25,25,16)、batch-07=(26,25,15)。"
    ),
}
EXECUTION_SEMANTICS = {
    "pipeline_per_batch": [
        "reviewer A independent annotation (isolated context, self-contained batch packet)",
        "reviewer B independent annotation (parallel, identical packet, no cross-visibility)",
        "schema/completeness QC (production REVIEW_KEYS, exact pair coverage, evidence anchors in frozen target)",
        "agreement report (actionable-binary and exact agreement; thresholds per frozen annotation protocol)",
        "disagreement-only third adjudication",
        "batch freeze (records and digests bound to the batch manifest)",
    ],
    "blindness": (
        "reviewer A/B 不得看到对方结果、此前任何 batch 的最终 edge labels、adjudication summaries 或"
        " history-based collaboration results；batch packet 必须自足（与 smoke 包同一模式）。"
        "若 reviewer 需要历史 batch 才能理解 rubric，判定为 package 缺陷：修 bundle，不开放历史标签。"
    ),
    "checkpointed_execution": (
        "batch N+1 仅在 batch N 冻结后启动；中断只损失当前 batch 的标注，批内 pair 集合由 manifest 固定，"
        "重跑只重做标注本身。不一次启动全部 462×2 的 reviewer workload。"
    ),
    "rubric_freeze_policy": (
        "batch-01 正式开始后 rubric/schema/版本冻结；若必须修改 rubric，需开新 batch-plan 版本并显式列出"
        " 因版本变更而失效的已完成 batch，禁止静默混用版本。各 batch 执行记录在启动时绑定 rubric 版本摘要。"
    ),
}


def quota_table() -> dict[str, list[int]]:
    totals = [0] * BATCH_COUNT
    quotas = {name: [0] * BATCH_COUNT for name in PAIR_CLASSES}
    class_sizes = {"old_to_new": 176, "new_to_old": 176, "new_to_new": 110}
    for name in EXTRA_CLASS_ORDER:
        base, extras = divmod(class_sizes[name], BATCH_COUNT)
        for ordinal in range(BATCH_COUNT):
            quotas[name][ordinal] = base
        for _ in range(extras):
            smallest = min(totals)
            ordinal = totals.index(smallest)
            quotas[name][ordinal] += 1
            totals[ordinal] += 1
    _require(all(sum(row) == class_sizes[name] for name, row in quotas.items()), "class quota totals wrong")
    _require(all(sum(quotas[name][o] for name in PAIR_CLASSES) == BATCH_SIZE for o in range(BATCH_COUNT)),
             "per-batch quota totals are not 66")
    return quotas


def deal_batches(universe: list[dict[str, Any]]) -> list[dict[str, Any]]:
    quotas = quota_table()
    by_class = {name: sorted((row for row in universe if row["pair_class"] == name),
                             key=lambda row: row["pair_id"]) for name in PAIR_CLASSES}
    _require([len(by_class[name]) for name in PAIR_CLASSES] == [176, 176, 110], "class sizes changed")
    assigned: dict[str, list[dict[str, Any]]] = {f"edge-annotation-batch-{i:02d}": [] for i in range(1, 8)}
    filled = {name: [0] * BATCH_COUNT for name in PAIR_CLASSES}
    names = [f"edge-annotation-batch-{i:02d}" for i in range(1, 8)]
    for name in PAIR_CLASSES:
        queue = list(by_class[name])
        round_index = 0
        while queue:
            order = range(BATCH_COUNT) if round_index % 2 == 0 else range(BATCH_COUNT - 1, -1, -1)
            for ordinal in order:
                if not queue:
                    break
                if filled[name][ordinal] < quotas[name][ordinal]:
                    assigned[names[ordinal]].append(queue.pop(0))
                    filled[name][ordinal] += 1
            round_index += 1
        _require(all(filled[name][o] == quotas[name][o] for o in range(BATCH_COUNT)),
                 f"serpentine dealing did not fill quotas: {name}")
    return [{"batch_id": batch_id, "pairs": assigned[batch_id]} for batch_id in names]


def node_area(nodes: list[dict[str, Any]]) -> dict[str, str]:
    areas = {}
    for node in nodes:
        counts: dict[str, int] = {}
        for path in node["code_scope"]:
            parts = Path(path).parts
            area = "/".join(parts[:2]) if len(parts) >= 2 else parts[0]
            counts[area] = counts.get(area, 0) + 1
        areas[node["node_id"]] = max(counts, key=lambda key: (counts[key], key))
    return areas


def workload_profile(batches: list[dict[str, Any]], nodes: list[dict[str, Any]]) -> dict[str, Any]:
    areas = node_area(nodes)
    profile = {}
    for batch in batches:
        pairs = batch["pairs"]
        sources = [row["source_node"] for row in pairs]
        targets = [row["target_node"] for row in pairs]
        dyads = {tuple(sorted((row["source_node"], row["target_node"]))) for row in pairs}
        both_directions = sum(1 for s, t in dyads
                              if any(r["source_node"] == s and r["target_node"] == t for r in pairs)
                              and any(r["source_node"] == t and r["target_node"] == s for r in pairs))
        source_counts = {key: sources.count(key) for key in sorted(set(sources))}
        target_counts = {key: targets.count(key) for key in sorted(set(targets))}
        area_counts: dict[str, int] = {}
        for row in pairs:
            for node_id in (row["source_node"], row["target_node"]):
                area_counts[areas[node_id]] = area_counts.get(areas[node_id], 0) + 1
        profile[batch["batch_id"]] = {
            "distinct_source_nodes": len(set(sources)),
            "distinct_target_nodes": len(set(targets)),
            "max_pairs_from_single_source": max(source_counts.values()),
            "max_pairs_into_single_target": max(target_counts.values()),
            "node_dyads_with_both_directions_in_batch": both_directions,
            "endpoint_code_area_counts": dict(sorted(area_counts.items())),
        }
    return profile


def validate_plan(batches: list[dict[str, Any]], universe: list[dict[str, Any]]) -> dict[str, Any]:
    universe_ids = [row["pair_id"] for row in universe]
    universe_set = set(universe_ids)
    batch_id_sets = [ {row["pair_id"] for row in batch["pairs"]} for batch in batches ]
    per_batch_totals = [len(batch["pairs"]) == BATCH_SIZE for batch in batches]
    class_counts = {
        name: [sum(row["pair_class"] == name for row in batch["pairs"]) for batch in batches]
        for name in PAIR_CLASSES
    }
    intersections_empty = all(not (batch_id_sets[i] & batch_id_sets[j])
                              for i, j in itertools.combinations(range(len(batches)), 2))
    unknown = sorted(set().union(*batch_id_sets) - universe_set)
    checks = {
        "coverage_is_462_of_462": sum(len(s) for s in batch_id_sets) == 462 and set().union(*batch_id_sets) == universe_set,
        "batch_count_is_7": len(batches) == BATCH_COUNT,
        "every_batch_is_66": all(per_batch_totals),
        "no_duplicates_within_batches": all(len(s) == len(batch["pairs"]) for s, batch in zip(batch_id_sets, batches)),
        "pairwise_intersections_all_empty": intersections_empty,
        "missing_are_0": not (universe_set - set().union(*batch_id_sets)),
        "unknown_pair_ids_are_0": not unknown,
        "class_totals_are_176_176_110": [sum(class_counts[name]) for name in PAIR_CLASSES] == [176, 176, 110],
        "max_class_spread_per_batch_le_1": all(max(counts) - min(counts) <= 1 for counts in class_counts.values()),
    }
    return {"checks": checks, "class_counts_per_batch": class_counts, "all_passed": all(checks.values())}


def render(plan_date: str) -> tuple[dict[str, bytes], dict[str, Any]]:
    universe_status = verify_pair_universe()
    universe = _read_jsonl(CASE_DIR / PAIR_UNIVERSE_VERSION / "pair_universe.jsonl")
    _require(len(universe) == 462 and universe_status["validator_all_passed"],
             "frozen pair universe is not the validated 462-pair input")
    nodes = _read_jsonl(CASE_DIR / "expansion-node-set-v2" / "nodes_frozen.jsonl")
    _require(len(nodes) == 27, "frozen node set size changed")
    batches = deal_batches(universe)
    validation = validate_plan(batches, universe)
    _require(validation["all_passed"], "batch plan validation failed; refusing to write")
    workload = workload_profile(batches, nodes)
    universe_manifest = _read_json(CASE_DIR / PAIR_UNIVERSE_VERSION / "pair_universe_manifest.json")
    outputs: dict[str, bytes] = {}
    index_batches = []
    for batch in batches:
        pairs_data = jlbytes(batch["pairs"])
        counts = {name: sum(row["pair_class"] == name for row in batch["pairs"]) for name in PAIR_CLASSES}
        manifest = {
            "schema_version": 1,
            "batch_id": batch["batch_id"],
            "batch_plan_version": BATCH_PLAN_VERSION,
            "status": "planned",
            "case_id": CASE_ID,
            "pair_universe_version": PAIR_UNIVERSE_VERSION,
            "pair_universe_manifest_sha256": universe_status["pair_universe_manifest_sha256"],
            "pair_universe_pairs_sha256": universe_status["pairs_sha256"],
            "node_set_version": universe_manifest["node_set_version"],
            "node_set_manifest_sha256": universe_status["node_set_manifest_sha256"],
            "base_graph_version": universe_manifest["base_graph_version"],
            "annotation_protocol_version": universe_manifest["annotation_protocol_version"],
            "target_sha256": universe_manifest["target_sha256"],
            "plan_date": plan_date,
            "pair_count": len(batch["pairs"]),
            "old_to_new_count": counts["old_to_new"],
            "new_to_old_count": counts["new_to_old"],
            "new_to_new_count": counts["new_to_new"],
            "pair_ids": [row["pair_id"] for row in batch["pairs"]],
            "pairs_file": "pairs.jsonl",
            "batch_digest": digest(pairs_data),
            "planned_execution": (
                "reviewer A/B 并行独立盲标 → schema/completeness QC → agreement report → "
                "disagreement-only adjudication → batch freeze；详见 ../batch_index.json 的 execution_semantics。"
            ),
        }
        batch_dir = f"batch-{batch['batch_id'][-2:]}"
        outputs[f"{batch_dir}/pairs.jsonl"] = pairs_data
        manifest_data = jbytes(manifest)
        outputs[f"{batch_dir}/manifest.json"] = manifest_data
        index_batches.append({
            "batch_id": batch["batch_id"],
            "pair_count": manifest["pair_count"],
            "old_to_new_count": manifest["old_to_new_count"],
            "new_to_old_count": manifest["new_to_old_count"],
            "new_to_new_count": manifest["new_to_new_count"],
            "batch_digest": manifest["batch_digest"],
            "manifest_sha256": digest(manifest_data),
        })
    index = {
        "schema_version": 1,
        "batch_plan_version": BATCH_PLAN_VERSION,
        "status": "planned",
        "case_id": CASE_ID,
        "pair_universe_version": PAIR_UNIVERSE_VERSION,
        "pair_universe_manifest_sha256": universe_status["pair_universe_manifest_sha256"],
        "pair_universe_pairs_sha256": universe_status["pairs_sha256"],
        "node_set_version": universe_manifest["node_set_version"],
        "node_set_manifest_sha256": universe_status["node_set_manifest_sha256"],
        "base_graph_version": universe_manifest["base_graph_version"],
        "annotation_protocol_version": universe_manifest["annotation_protocol_version"],
        "target_sha256": universe_manifest["target_sha256"],
        "plan_date": plan_date,
        "total_pairs": 462,
        "batch_count": BATCH_COUNT,
        "batch_size": BATCH_SIZE,
        "algorithm": ALGORITHM,
        "batches": index_batches,
        "validation": validation,
        "workload_profile": workload,
        "execution_semantics": EXECUTION_SEMANTICS,
    }
    outputs["batch_index.json"] = jbytes(index)
    return outputs, index


def plan() -> dict[str, Any]:
    _require(not OUT_DIR.is_symlink(), "unsafe batch-plan directory")
    OUT_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    OUT_DIR.chmod(0o700)
    outputs, _ = render(date.today().isoformat())
    for name, content in outputs.items():
        path = OUT_DIR / name
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.parent.chmod(0o700)
        _require(not path.is_symlink() and (not path.exists() or path.read_bytes() == content),
                 f"batch-plan artifact changed; create a new plan version: {name}")
        if not path.exists():
            path.write_bytes(content)
        path.chmod(0o600)
    return verify()


def verify() -> dict[str, Any]:
    index_path = OUT_DIR / "batch_index.json"
    _require(index_path.is_file() and not index_path.is_symlink(), "batch index missing")
    recorded = _read_json(index_path)
    outputs, index = render(recorded["plan_date"])
    for name, content in outputs.items():
        path = OUT_DIR / name
        _require(path.is_file() and not path.is_symlink() and path.read_bytes() == content,
                 f"batch-plan artifact mismatch: {name}")
    _require(recorded == index, "batch index mismatch")
    return {
        "status": "verified_planned_batches",
        "batch_plan_version": BATCH_PLAN_VERSION,
        "total_pairs": 462,
        "batch_count": BATCH_COUNT,
        "batch_size": BATCH_SIZE,
        "validation_all_passed": index["validation"]["all_passed"],
        "batch_index_sha256": digest(outputs["batch_index.json"]),
        "batch_digests": {row["batch_id"]: row["batch_digest"] for row in index["batches"]},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("plan", "verify"))
    args = parser.parse_args()
    try:
        result = plan() if args.command == "plan" else verify()
    except GraphValidationError as exc:
        parser.exit(1, f"edge annotation batch planning failed: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
