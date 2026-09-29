#!/usr/bin/env python3
"""Validate formal expansion edge batch reviews, gate agreement, adjudicate and freeze one batch."""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import math
import re
from datetime import date
from pathlib import Path
from typing import Any

from experiments.emergent_coordination.harness.cases import load_case
from scripts.check_hidden_graph_pilot_b_edges import (
    ADJUDICATION_KEYS,
    REVIEW_KEYS as PRODUCTION_REVIEW_KEYS,
    TAXONOMY,
)
from scripts.freeze_hidden_graph_pair_universe import (
    PAIR_UNIVERSE_VERSION,
    verify as verify_pair_universe,
)
from scripts.hidden_opportunity_graph import (
    ACTIONABLE_TYPES,
    CASE_ID,
    GraphValidationError,
    _read_json,
    _read_jsonl,
    _require,
    _validate_edge,
)
from scripts.plan_hidden_graph_edge_annotation_batches import verify as verify_batch_plan
from scripts.prepare_hidden_graph_expansion_edge_batch import (
    BATCHES_DIR,
    EVALUATOR_PRIVATE_FILES,
    PACKET_FILES,
    PACKET_VERSION,
    RUBRIC_VERSION,
    TARGET_ROOT,
    batch_dir,
    batch_ordinal,
    load_batch,
    packet_dir,
    verify_cmd as verify_packet,
)


RUNTIME_REFERENCE_PATTERNS = (
    r"T4", r"S/P/B/T", r"Pilot\s*A", r"Pilot\s*B", r"Stage\s*9", r"run\s*mapping",
    r"operational\s*realizability", r"agent\s*(会|真的|之间)", r"运行\s*(中|时)\s*(观察到|表现)",
    r"历史\s*(run|运行)", r"condition\s*表现",
)
BINARY_THRESHOLD_RULE = "ceil(0.9 * 66) = 60"
# 每批执行事故备注：键为批号；无事故的批冻结为空列表。写入后不得回改（freeze 幂等复核逐字节比对）。
CONTROLLER_INCIDENT_NOTES: dict[str, list[str]] = {
    "01": [
        (
            "attempt1 QC（保存于 edge_qc_attempt1_accesslog_defect.json）：reviewer_b 的 access 日志把 "
            "38 个 target 文件记为 target 相对路径且漏记 4 个 packet 文件（均为日志格式缺陷，"
            "非越界读取：全部路径位于冻结 target 树内，标签文件未改动）；reviewer_b 本人按控制方要求"
            " 修正日志后重新运行 QC。标签与 agreement 计算不受影响。"
        ),
    ],
}


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _jbytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _batch_root(batch_no: str) -> str:
    return f"artifacts/hidden_opportunity_graph/{CASE_ID}/expansion-edge-batches-v1/batch-{batch_no}"


def _load_review(path: Path, expected_pairs: dict[tuple[str, str], str], node_ids: set[str],
                 target: Path, *, third: bool = False
                 ) -> tuple[str, dict[tuple[str, str], dict[str, Any]], list[str]]:
    _require(path.is_file() and not path.is_symlink(), f"missing batch review file: {path.name}")
    rows = _read_jsonl(path)
    keys = ADJUDICATION_KEYS if third else PRODUCTION_REVIEW_KEYS
    id_key = "adjudicator_id" if third else "reviewer_id"
    mapped: dict[tuple[str, str], dict[str, Any]] = {}
    identities = set()
    warnings: list[str] = []
    for index, row in enumerate(rows, 1):
        where = f"{path.name}:{index}"
        _require(set(row) == keys, f"{where}: schema keys differ from production template")
        pair = (row["source_node"], row["target_node"])
        _require(pair in expected_pairs and pair not in mapped,
                 f"{where}: pair not in batch set or duplicated")
        identity = row[id_key]
        _require(isinstance(identity, str) and identity.strip(), f"{where}: empty reviewer identity")
        final_shape = {key: value for key, value in row.items() if key not in (id_key,)}
        final_shape.update({
            "edge_id": expected_pairs[pair],
            "direction": "source_to_target",
            "adjudication_status": "proposed",
            "reviewer_ids": [identity],
        })
        _validate_edge(final_shape, where, target, node_ids, PAIR_UNIVERSE_VERSION)
        mapped[pair] = row
        identities.add(identity)
        text = " ".join(str(row[key]) for key in ("rationale", "bounded_check", "source_artifact",
                                                  "target_claim", "uncertainty_note") if row.get(key))
        for pattern in RUNTIME_REFERENCE_PATTERNS:
            if re.search(pattern, text):
                warnings.append(f"{where}: possible runtime/history reference ({pattern})")
    _require(len(identities) == 1, f"{path.name}: inconsistent reviewer identity")
    _require(set(mapped) == set(expected_pairs), f"{path.name}: missing or extra batch pairs")
    return identities.pop(), mapped, warnings


def _check_access_log(path: Path, reviewer_id: str, batch_no: str, own_files: list[str]) -> dict[str, Any]:
    _require(path.is_file() and not path.is_symlink(), f"missing batch access log: {path.name}")
    record = _read_json(path)
    _require(set(record) == {"reviewer_id", "files_read"}, f"{path.name}: access log schema mismatch")
    _require(record["reviewer_id"] == reviewer_id, f"{path.name}: access log reviewer mismatch")
    root = _batch_root(batch_no)
    allowed_exact = {f"{root}/packet/{name}" for name in PACKET_FILES}
    allowed_exact |= {f"{root}/reviews/{name}" for name in own_files}
    allowed_exact |= set(EVALUATOR_PRIVATE_FILES)
    allowed_prefixes = (f"{TARGET_ROOT}/",)
    violations = []
    for entry in record["files_read"]:
        if entry in allowed_exact or any(entry.startswith(prefix) for prefix in allowed_prefixes):
            continue
        violations.append(entry)
    required_packet_reads = {f"{root}/packet/reviewer_rubric.json", f"{root}/packet/edge_reviewer_bundle.json"}
    return {
        "reviewer_id": reviewer_id,
        "files_read_count": len(record["files_read"]),
        "scope_violations": sorted(violations),
        "read_rubric_and_bundle": required_packet_reads <= set(record["files_read"]),
        "touched_target_files": sorted({p for p in record["files_read"] if p.startswith(TARGET_ROOT)}),
    }


def _weighted_kappa(a: dict[tuple[str, str], dict[str, Any]], b: dict[tuple[str, str], dict[str, Any]]) -> float | None:
    pairs = list(a)
    n = len(pairs)
    counts_a = collections.Counter(a[p]["opportunity_type"] for p in pairs)
    counts_b = collections.Counter(b[p]["opportunity_type"] for p in pairs)
    position = {category: index for index, category in enumerate(TAXONOMY)}
    observed = sum((position[a[p]["opportunity_type"]] - position[b[p]["opportunity_type"]]) ** 2
                   for p in pairs) / n
    expected = sum((position[left] - position[right]) ** 2 * counts_a[left] * counts_b[right]
                   for left in TAXONOMY for right in TAXONOMY) / (n * n)
    return round(1 - observed / expected, 6) if expected else (1.0 if observed == 0 else None)


def _needed_pairs(a: dict[tuple[str, str], dict[str, Any]], b: dict[tuple[str, str], dict[str, Any]],
                  ordered: list[tuple[str, str]]) -> set[tuple[str, str]]:
    return {p for p in ordered if a[p]["opportunity_type"] != b[p]["opportunity_type"]
            or a[p]["uncertainty_note"] or b[p]["uncertainty_note"]}


def _agreement_block(a, b, ordered, expected_pairs) -> dict[str, Any]:
    binary = sum((a[p]["opportunity_type"] in ACTIONABLE_TYPES)
                 == (b[p]["opportunity_type"] in ACTIONABLE_TYPES) for p in ordered)
    exact = sum(a[p]["opportunity_type"] == b[p]["opportunity_type"] for p in ordered)
    positive = [p for p in ordered if (a[p]["opportunity_type"] in ACTIONABLE_TYPES)
                != (b[p]["opportunity_type"] in ACTIONABLE_TYPES)]
    dyads = {tuple(sorted(p)) for p in ordered}
    present = set(ordered)
    direction_disagreements = []
    for left, right in sorted(dyads):
        options = ((left, right), (right, left))
        aa = {p for p in options if p in present and a[p]["opportunity_type"] in ACTIONABLE_TYPES}
        bb = {p for p in options if p in present and b[p]["opportunity_type"] in ACTIONABLE_TYPES}
        if aa != bb:
            direction_disagreements.append((left, right))
    threshold = math.ceil(0.9 * len(ordered))
    return {
        "exact_agreement_count": exact,
        "exact_agreement_rate": round(exact / len(ordered), 6),
        "binary_agreement_count": binary,
        "binary_agreement_threshold": threshold,
        "binary_agreement_threshold_rule": BINARY_THRESHOLD_RULE,
        "binary_agreement_rate": round(binary / len(ordered), 6),
        "binary_threshold_met": binary >= threshold,
        "quadratic_weighted_kappa": _weighted_kappa(a, b),
        "confusion_matrix_rows_reviewer_a_cols_reviewer_b": {
            left: {right: sum(a[p]["opportunity_type"] == left and b[p]["opportunity_type"] == right
                              for p in ordered) for right in TAXONOMY} for left in TAXONOMY},
        "positive_disagreements": [list(p) for p in positive],
        "direction_agreement_count": len(dyads) - len(direction_disagreements),
        "direction_agreement_denominator": len(dyads),
        "direction_disagreements": [list(p) for p in direction_disagreements],
        "per_pair": {expected_pairs[p]: {"reviewer_a": a[p]["opportunity_type"],
                                         "reviewer_b": b[p]["opportunity_type"]} for p in ordered},
    }


def _write_idempotent(path: Path, data: bytes) -> None:
    _require(not path.is_symlink() and (not path.exists() or path.read_bytes() == data),
             f"artifact changed; inspect manually before rewriting: {path.name}")
    if not path.exists():
        path.write_bytes(data)
    path.chmod(0o600)


def check(batch_no: str) -> dict[str, Any]:
    batch_ordinal(batch_no)
    universe_status = verify_pair_universe()
    plan_status = verify_batch_plan()
    packet_status = verify_packet(batch_no)
    manifest, pairs = load_batch(batch_no)
    expected_pairs = {(row["source_node"], row["target_node"]): row["pair_id"] for row in pairs}
    _require(len(expected_pairs) == 66, "batch must carry exactly 66 directed pairs")
    bundle = _read_json(packet_dir(batch_no) / "edge_reviewer_bundle.json")
    _require({(row["source_node"], row["target_node"]) for row in bundle["directed_pairs"]} == set(expected_pairs),
             "bundle pairs differ from the frozen batch manifest")
    node_ids = {node["node_id"] for node in bundle["nodes"]}
    target = load_case(CASE_ID).target_root
    review_dir = batch_dir(batch_no) / "reviews"
    missing = [name for name in ("reviewer_a.jsonl", "reviewer_b.jsonl") if not (review_dir / name).is_file()]
    gates = {
        "pair_universe_verified": universe_status["validator_all_passed"],
        "batch_plan_verified": plan_status["validation_all_passed"],
        "packet_verified_without_frozen_edge_leak": packet_status["status"] == "verified_formal_batch_packet",
        "packet_pairs_match_batch_manifest": True,
        "production_template_key_compatibility": PRODUCTION_REVIEW_KEYS == {
            "reviewer_id", "source_node", "target_node", "opportunity_type", "mechanisms", "source_artifact",
            "target_claim", "expected_effect", "bounded_check", "evidence", "rationale", "confidence",
            "uncertainty_note"},
    }
    if missing:
        return {"status": "pending_batch_reviews", "batch_id": manifest["batch_id"], "missing": missing,
                "gates": gates}
    a_id, a_rows, a_warnings = _load_review(review_dir / "reviewer_a.jsonl", expected_pairs, node_ids, target)
    b_id, b_rows, b_warnings = _load_review(review_dir / "reviewer_b.jsonl", expected_pairs, node_ids, target)
    access_a = _check_access_log(review_dir / "reviewer_a_access.json", a_id, batch_no,
                                 ["reviewer_a.jsonl", "reviewer_a_access.json"])
    access_b = _check_access_log(review_dir / "reviewer_b_access.json", b_id, batch_no,
                                 ["reviewer_b.jsonl", "reviewer_b_access.json"])
    ordered = [(row["source_node"], row["target_node"]) for row in bundle["directed_pairs"]]
    agreement = _agreement_block(a_rows, b_rows, ordered, expected_pairs)
    needed = _needed_pairs(a_rows, b_rows, ordered)
    gates.update({
        "both_reviews_complete_and_schema_valid": True,
        "evidence_resolvable_in_frozen_target": True,
        "distinct_reviewer_ids": a_id != b_id,
        "access_within_allowed_scope": not access_a["scope_violations"] and not access_b["scope_violations"],
        "both_read_rubric_and_bundle": access_a["read_rubric_and_bundle"] and access_b["read_rubric_and_bundle"],
    })
    if not agreement["binary_threshold_met"]:
        status = "qc_failed_reblind_required"
    elif needed:
        status = "pending_adjudication"
    else:
        status = "ready_to_freeze"
    qc_path = batch_dir(batch_no) / "edge_qc.json"
    recorded = _read_json(qc_path) if qc_path.is_file() else {}
    qc_date = recorded.get("qc_date", date.today().isoformat())
    report = {
        "status": status,
        "annotation_status": "production_formal_double_blind",
        "batch_plan_version": manifest["batch_plan_version"],
        "batch_id": manifest["batch_id"],
        "case_id": CASE_ID,
        "qc_date": qc_date,
        "pair_universe_version": PAIR_UNIVERSE_VERSION,
        "pair_universe_manifest_sha256": universe_status["pair_universe_manifest_sha256"],
        "batch_manifest_sha256": _digest((batch_dir(batch_no) / "manifest.json").read_bytes()),
        "batch_digest": manifest["batch_digest"],
        "packet_version": PACKET_VERSION,
        "packet_manifest_sha256": packet_status["packet_manifest_sha256"],
        "rubric_version": RUBRIC_VERSION,
        "rubric_sha256": packet_status["rubric_sha256"],
        "reviewer_ids": [a_id, b_id],
        "review_file_sha256": {
            "reviewer_a": _digest((review_dir / "reviewer_a.jsonl").read_bytes()),
            "reviewer_b": _digest((review_dir / "reviewer_b.jsonl").read_bytes()),
        },
        "batch_pair_count": len(ordered),
        "pair_class_counts": {
            "old_to_new": manifest["old_to_new_count"],
            "new_to_old": manifest["new_to_old_count"],
            "new_to_new": manifest["new_to_new_count"],
        },
        "categories_reviewer_a": {name: sum(row["opportunity_type"] == name for row in a_rows.values())
                                  for name in TAXONOMY},
        "categories_reviewer_b": {name: sum(row["opportunity_type"] == name for row in b_rows.values())
                                  for name in TAXONOMY},
        "agreement": agreement,
        "needs_adjudication": [list(p) for p in sorted(needed)],
        "uncertain_review_pairs": [list(p) for p in sorted(
            p for p in ordered if a_rows[p]["uncertainty_note"] or b_rows[p]["uncertainty_note"])],
        "access_review": {"reviewer_a": access_a, "reviewer_b": access_b},
        "runtime_reference_warnings": sorted(a_warnings + b_warnings),
        "gates": gates,
        "reblind_policy": (
            "binary 一致率未达门槛时：保存失败轮记录，只允许修订通用定义，整批换新包新子代理重盲，"
            "禁止用裁决把失败轮转为通过。"
        ),
    }
    _write_idempotent(qc_path, _jbytes(report))
    if status == "pending_adjudication":
        adjudication_input = {
            "batch_id": manifest["batch_id"],
            "pair_universe_version": PAIR_UNIVERSE_VERSION,
            "rubric_version": RUBRIC_VERSION,
            "rubric_sha256": packet_status["rubric_sha256"],
            "scope": "disagreement_or_uncertain_pairs_only",
            "needed_pair_count": len(needed),
            "pairs": [{
                "pair_id": expected_pairs[p],
                "source_node": p[0],
                "target_node": p[1],
                "reviewer_a": a_rows[p],
                "reviewer_b": b_rows[p],
            } for p in sorted(needed)],
        }
        _write_idempotent(review_dir / "adjudication_input.json", _jbytes(adjudication_input))
    elif (review_dir / "adjudication_input.json").exists():
        _require(status == "qc_failed_reblind_required"
                 or not needed, "adjudication input exists but QC no longer flags any pair")
    return report


def freeze(batch_no: str) -> dict[str, Any]:
    batch_ordinal(batch_no)
    packet_status = verify_packet(batch_no)
    verify_batch_plan()
    manifest, pairs = load_batch(batch_no)
    qc = _read_json(batch_dir(batch_no) / "edge_qc.json")
    _require(qc.get("gates", {}).get("access_within_allowed_scope", False)
             and qc.get("gates", {}).get("both_read_rubric_and_bundle", False),
             "batch QC gates not satisfied; refusing to freeze")
    _require(qc["batch_digest"] == manifest["batch_digest"], "QC report is bound to a different batch digest")
    review_dir = batch_dir(batch_no) / "reviews"
    for name, key in (("reviewer_a.jsonl", "reviewer_a"), ("reviewer_b.jsonl", "reviewer_b")):
        _require(qc["review_file_sha256"][key] == _digest((review_dir / name).read_bytes()),
                 f"review file changed after QC: {name}")
    if qc["status"] not in {"ready_to_freeze", "pending_adjudication"}:
        raise GraphValidationError(f"batch QC status does not allow freeze: {qc['status']}")
    expected_pairs = {(row["source_node"], row["target_node"]): row["pair_id"] for row in pairs}
    bundle = _read_json(packet_dir(batch_no) / "edge_reviewer_bundle.json")
    node_ids = {node["node_id"] for node in bundle["nodes"]}
    target = load_case(CASE_ID).target_root
    a_id, a_rows, _ = _load_review(review_dir / "reviewer_a.jsonl", expected_pairs, node_ids, target)
    b_id, b_rows, _ = _load_review(review_dir / "reviewer_b.jsonl", expected_pairs, node_ids, target)
    ordered = [(row["source_node"], row["target_node"]) for row in bundle["directed_pairs"]]
    needed = _needed_pairs(a_rows, b_rows, ordered)
    _require([list(p) for p in sorted(needed)] == qc["needs_adjudication"],
             "disagreement set changed since QC; re-run check")
    third_id, third_rows = None, {}
    adjudication_sha = None
    adjudication_input_sha = None
    if needed:
        input_path = review_dir / "adjudication_input.json"
        _require(input_path.is_file(), "adjudication input missing; re-run check")
        adjudication_input_sha = _digest(input_path.read_bytes())
        recorded_input = _read_json(input_path)
        _require({(row["source_node"], row["target_node"]) for row in recorded_input["pairs"]} == needed,
                 "adjudication input does not cover exactly the needed pairs")
        third_path = review_dir / "adjudicator.jsonl"
        third_id, third_rows, _ = _load_review(third_path, {p: expected_pairs[p] for p in needed},
                                               node_ids, target, third=True)
        _require(third_id not in {a_id, b_id}, "adjudicator must be a third independent reviewer")
        access = _check_access_log(review_dir / "adjudicator_access.json", third_id, batch_no,
                                   ["adjudicator.jsonl", "adjudicator_access.json", "adjudication_input.json"])
        _require(not access["scope_violations"] and access["read_rubric_and_bundle"],
                 "adjudicator access out of scope")
        adjudication_sha = _digest(third_path.read_bytes())
    final_labels = []
    for pair in ordered:
        raw = third_rows.get(pair, a_rows[pair])
        if raw["uncertainty_note"]:
            label_status = "uncertain"
        elif pair in third_rows:
            label_status = "adjudicated"
        else:
            label_status = "agreed"
        id_key = "adjudicator_id" if "adjudicator_id" in raw else "reviewer_id"
        edge = {key: value for key, value in raw.items() if key != id_key}
        edge.update({
            "edge_id": expected_pairs[pair],
            "direction": "source_to_target",
            "adjudication_status": label_status,
            "reviewer_ids": [a_id, b_id],
        })
        _validate_edge(edge, f"final[{pair[0]}->{pair[1]}]", target, node_ids, PAIR_UNIVERSE_VERSION)
        final_labels.append(edge)
    labels_data = b"".join((json.dumps(edge, ensure_ascii=False, sort_keys=True) + "\n").encode()
                           for edge in final_labels)
    _write_idempotent(batch_dir(batch_no) / "final_labels.jsonl", labels_data)
    freeze_path = batch_dir(batch_no) / "batch_freeze.json"
    recorded = _read_json(freeze_path) if freeze_path.is_file() else {}
    freeze_date = recorded.get("freeze_date", date.today().isoformat())
    categories_final = collections.Counter(edge["opportunity_type"] for edge in final_labels)
    uncertain = [edge for edge in final_labels if edge["adjudication_status"] == "uncertain"]
    payload = {
        "status": "frozen_batch",
        "status_transition": "planned -> frozen_batch",
        "batch_plan_version": manifest["batch_plan_version"],
        "batch_id": manifest["batch_id"],
        "case_id": CASE_ID,
        "freeze_date": freeze_date,
        "pair_universe_version": PAIR_UNIVERSE_VERSION,
        "pair_universe_manifest_sha256": qc["pair_universe_manifest_sha256"],
        "batch_manifest_sha256": qc["batch_manifest_sha256"],
        "batch_digest": manifest["batch_digest"],
        "packet_manifest_sha256": packet_status["packet_manifest_sha256"],
        "rubric_version": RUBRIC_VERSION,
        "rubric_sha256": packet_status["rubric_sha256"],
        "reviewer_ids": [a_id, b_id],
        "adjudicator_id": third_id,
        "review_file_sha256": qc["review_file_sha256"],
        "adjudication_input_sha256": adjudication_input_sha,
        "adjudication_file_sha256": adjudication_sha,
        "edge_qc_sha256": _digest((batch_dir(batch_no) / "edge_qc.json").read_bytes()),
        "final_labels_sha256": _digest(labels_data),
        "final_label_count": len(final_labels),
        "categories_final": {name: categories_final[name] for name in TAXONOMY},
        "agreed_count": sum(edge["adjudication_status"] == "agreed" for edge in final_labels),
        "adjudicated_count": len(third_rows),
        "uncertain_pairs": [[edge["source_node"], edge["target_node"]] for edge in uncertain],
        "agreement_summary": {
            "exact_agreement_count": qc["agreement"]["exact_agreement_count"],
            "exact_agreement_rate": qc["agreement"]["exact_agreement_rate"],
            "binary_agreement_count": qc["agreement"]["binary_agreement_count"],
            "binary_agreement_threshold": qc["agreement"]["binary_agreement_threshold"],
            "binary_agreement_rate": qc["agreement"]["binary_agreement_rate"],
        },
        "controller_incident_notes": CONTROLLER_INCIDENT_NOTES.get(batch_no, []),
        "scope_note": (
            "本 freeze 仅冻结该 batch 的双人盲标+裁决标签；不构成 702-pair 全图冻结，"
            "不含 opportunity density、operational realizability、run mapping 或 Stage 9 更新。"
        ),
        "checkpoint_rule": "batch N+1 仅在本 batch freeze 后启动。",
    }
    _write_idempotent(freeze_path, _jbytes(payload))
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "freeze"))
    parser.add_argument("batch_no", help="batch number 01..07")
    args = parser.parse_args()
    try:
        result = check(args.batch_no) if args.command == "check" else freeze(args.batch_no)
    except GraphValidationError as exc:
        parser.exit(1, f"expansion edge batch {args.command} failed: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
