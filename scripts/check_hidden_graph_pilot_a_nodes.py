"""检查 Pilot A 独立节点边界标注；QC 通过后冻结节点语义，不预判边。"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from datetime import date
from pathlib import Path
from typing import Any

from experiments.emergent_coordination.harness.cases import load_case
from scripts.hidden_opportunity_graph import (
    CASE_ID,
    PILOT_A_CANDIDATES,
    PRIVATE_GRAPH_DIR,
    GraphValidationError,
    _evidence,
    _read_json,
    _read_jsonl,
    _require,
    _validate_node,
    stamp_draft,
)
from scripts.prepare_hidden_graph_pilot_a import PILOT_DIR, verify as verify_packets


PAIRS = list(itertools.combinations(PILOT_A_CANDIDATES, 2))
REVIEW_KEYS = {
    "reviewer_id", "candidate_a", "candidate_b", "security_question_a", "security_question_b",
    "decision", "counterfactual", "rationale", "evidence_refs"
}
ADJUDICATION_KEYS = {
    "adjudicator_id", "candidate_a", "candidate_b", "decision", "counterfactual", "rationale", "evidence_refs"
}


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _jsonl_bytes(records: list[dict[str, Any]]) -> bytes:
    return b"".join((json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8") for item in records)


def _validate_refs(record: dict[str, Any], where: str, target: Path) -> None:
    refs = record["evidence_refs"]
    _require(isinstance(refs, list) and len(refs) >= 2, f"{where}: two-sided evidence required")
    _require({"candidate_a", "candidate_b"} <= {item.get("role") for item in refs if isinstance(item, dict)},
             f"{where}: missing candidate_a/candidate_b evidence roles")
    for index, item in enumerate(refs):
        _evidence(item, f"{where}.evidence_refs[{index}]", target)


def _load_review(path: Path, questions: dict[str, str], target: Path) -> tuple[str, dict[tuple[str, str], dict[str, Any]]]:
    records = _read_jsonl(path)
    _require(len(records) == 15, f"{path.name}: expected 15 candidate pairs")
    mapped: dict[tuple[str, str], dict[str, Any]] = {}
    reviewer_ids = set()
    for index, record in enumerate(records):
        where = f"{path.name}:{index + 1}"
        _require(set(record) == REVIEW_KEYS, f"{where}: reviewer schema mismatch")
        pair = (record["candidate_a"], record["candidate_b"])
        _require(pair in PAIRS and pair not in mapped, f"{where}: unknown or duplicate pair")
        _require(record["security_question_a"] == questions[pair[0]] and record["security_question_b"] == questions[pair[1]],
                 f"{where}: security question differs from locked bundle")
        for key in ("reviewer_id", "counterfactual", "rationale"):
            _require(isinstance(record[key], str) and record[key].strip(), f"{where}: empty {key}")
        _require(isinstance(record["decision"], str) and record["decision"] in {"split", "merge", "uncertain"},
                 f"{where}: invalid decision")
        _validate_refs(record, where, target)
        reviewer_ids.add(record["reviewer_id"])
        mapped[pair] = record
    _require(len(reviewer_ids) == 1 and set(mapped) == set(PAIRS), f"{path.name}: inconsistent reviewer or pair coverage")
    return reviewer_ids.pop(), mapped


def _load_adjudications(path: Path, needed: set[tuple[str, str]], reviewer_ids: set[str], target: Path) -> tuple[str | None, dict[tuple[str, str], dict[str, Any]]]:
    if not needed:
        if path.exists():
            _require(not _read_jsonl(path), "adjudication file contains unexpected decisions")
        return None, {}
    _require(path.is_file(), "independent decisions need a third adjudicator record")
    records = _read_jsonl(path)
    mapped = {}
    adjudicators = set()
    for index, record in enumerate(records):
        where = f"{path.name}:{index + 1}"
        _require(set(record) == ADJUDICATION_KEYS, f"{where}: adjudication schema mismatch")
        pair = (record["candidate_a"], record["candidate_b"])
        _require(pair in needed and pair not in mapped, f"{where}: unexpected or duplicate adjudication")
        _require(isinstance(record["decision"], str) and record["decision"] in {"split", "merge", "uncertain"},
                 f"{where}: invalid decision")
        for key in ("adjudicator_id", "counterfactual", "rationale"):
            _require(isinstance(record[key], str) and record[key].strip(), f"{where}: empty {key}")
        _require(record["adjudicator_id"] not in reviewer_ids, f"{where}: adjudicator must be a third person")
        _validate_refs(record, where, target)
        adjudicators.add(record["adjudicator_id"])
        mapped[pair] = record
    _require(set(mapped) == needed and len(adjudicators) == 1, "third adjudication does not cover exactly the disputed pairs")
    return adjudicators.pop(), mapped


def assess(directory: Path = PILOT_DIR) -> tuple[dict[str, Any], dict[str, Any]]:
    packet_status = verify_packets(directory)
    bundle = _read_json(directory / "reviewer_bundle.json")
    questions = {item["candidate_id"]: item["security_question"] for item in bundle["candidates"]}
    _require(set(questions) == set(PILOT_A_CANDIDATES), "review bundle candidate set mismatch")
    review_dir = directory / "reviews"
    a_path = review_dir / "reviewer_a.jsonl"
    b_path = review_dir / "reviewer_b.jsonl"
    missing = [path.name for path in (a_path, b_path) if not path.is_file()]
    if missing:
        return {**packet_status, "status": "pending_independent_reviews", "missing": missing}, {}
    target = load_case(CASE_ID).target_root
    a_id, a = _load_review(a_path, questions, target)
    b_id, b = _load_review(b_path, questions, target)
    _require(a_id != b_id, "reviewers must be distinct")
    agreement = sum(a[pair]["decision"] == b[pair]["decision"] for pair in PAIRS)
    needed = {
        pair for pair in PAIRS
        if a[pair]["decision"] != b[pair]["decision"] or a[pair]["decision"] == "uncertain"
    }
    adjudication_path = review_dir / "adjudicator.jsonl"
    if needed and not adjudication_path.is_file():
        return {
            **packet_status,
            "status": "pending_third_adjudication",
            "reviewer_ids": [a_id, b_id],
            "node_pair_agreement": f"{agreement}/15",
            "needs_adjudication": [list(pair) for pair in sorted(needed)],
        }, {}
    adjudicator_id, decisions = _load_adjudications(adjudication_path, needed, {a_id, b_id}, target)
    final = {pair: decisions[pair]["decision"] if pair in decisions else a[pair]["decision"] for pair in PAIRS}
    failed_agreement = agreement < 14
    unresolved = [list(pair) for pair in PAIRS if final[pair] == "uncertain"]
    merged = [list(pair) for pair in PAIRS if final[pair] == "merge"]
    status = (
        "qc_failed_reblind_required" if failed_agreement else
        "unresolved_boundary" if unresolved else
        "pilot_revision_required" if merged else
        "ready_to_freeze_six_nodes"
    )
    report = {
        "status": status,
        "case_id": CASE_ID,
        "graph_version": bundle["graph_version"],
        "adjudication_date": date.today().isoformat(),
        "input_lock_sha256": packet_status["input_lock_sha256"],
        "reviewer_bundle_sha256": _digest((directory / "reviewer_bundle.json").read_bytes()),
        "reviewer_ids": [a_id, b_id],
        "adjudicator_id": adjudicator_id,
        "review_file_sha256": {"reviewer_a": _digest(a_path.read_bytes()), "reviewer_b": _digest(b_path.read_bytes())},
        "adjudication_file_sha256": _digest(adjudication_path.read_bytes()) if adjudication_path.exists() else None,
        "node_pair_agreement_count": agreement,
        "node_pair_count": 15,
        "node_pair_gate_passed": agreement >= 14,
        "adjudicated_pair_count": len(decisions),
        "unresolved_pairs": unresolved,
        "merged_pairs": merged,
        "final_pair_decisions": [
            {"candidate_a": pair[0], "candidate_b": pair[1], "decision": final[pair]}
            for pair in PAIRS
        ],
        "frozen_node_count": 6 if status == "ready_to_freeze_six_nodes" else None,
        "directed_pair_denominator": 30 if status == "ready_to_freeze_six_nodes" else None,
    }
    return report, {"a": a, "b": b, "adjudications": decisions, "packets": bundle["candidates"]}


def freeze_nodes(directory: Path = PILOT_DIR) -> dict[str, Any]:
    report, sources = assess(directory)
    _require(report["status"] == "ready_to_freeze_six_nodes", f"node boundary QC not passed: {report['status']}")
    nodes = []
    for ordinal, packet in enumerate(sources["packets"], 1):
        candidate_id = packet["candidate_id"]
        root = packet["gt_status"] == "scored_positive"
        refs = [
            {key: evidence[key] for key in ("path", "line", "symbol", "excerpt", "excerpt_sha256", "role")}
            for evidence in packet["evidence"]
        ]
        nodes.append({
            "node_id": f"F{ordinal:03d}",
            "security_question": packet["security_question"],
            "code_scope": list(dict.fromkeys(ref["path"] for ref in refs if ref["role"] != "narrow_safe_contrast")),
            "invariant": packet["invariant"],
            "boundary_rationale": "Pilot A 15 对边界判断均裁为 split；具体反事实与必要源码链见已锁定的双人原始记录和 node_boundary_qc.json。",
            "potential_artifact": packet["minimal_artifact"],
            "evidence_refs": refs,
            "truth_status": packet["gt_status"],
            "gt_root_ids": [candidate_id] if root else [],
            "near_miss_ids": [] if root else [candidate_id],
            "adjudication_status": "adjudicated",
        })
    gt = _read_json(load_case(CASE_ID).ground_truth_path)
    root_ids = {item["id"] for item in gt["roots"]}
    near_ids = {item["id"] for item in gt["near_misses"]}
    target = load_case(CASE_ID).target_root
    for index, node in enumerate(nodes):
        _validate_node(node, f"frozen_nodes[{index}]", target, root_ids, near_ids)
    node_bytes = _jsonl_bytes(nodes)
    report["nodes_frozen_sha256"] = _digest(node_bytes)
    outputs = {
        directory / "nodes_frozen.jsonl": node_bytes,
        directory / "node_boundary_qc.json": _json_bytes(report),
    }
    for path, data in outputs.items():
        _require(not path.exists() or path.read_bytes() == data,
                 f"frozen node artifact differs; create a new graph version: {path.name}")
    # Bind both independent raw reviews and any third-person decisions to the draft graph manifest.
    reviews = [*sources["a"].values(), *sources["b"].values()]
    common_adjudications = []
    for pair, item in sources["adjudications"].items():
        common_adjudications.append({
            "kind": "node_boundary",
            "item_id": f"{pair[0]}|{pair[1]}",
            "adjudicator_id": item["adjudicator_id"],
            "decision": item["decision"],
            "rationale": f"{item['rationale']} 反事实：{item['counterfactual']}",
            "reviewer_ids": report["reviewer_ids"],
        })
    graph_root = directory.parent
    raw_outputs = {
        graph_root / "node_reviews.jsonl": _jsonl_bytes(reviews),
        graph_root / "adjudications.jsonl": _jsonl_bytes(common_adjudications),
    }
    for path, data in raw_outputs.items():
        _require(not path.read_bytes() or path.read_bytes() == data,
                 f"existing graph review log differs: {path.name}")
    for path, data in {**outputs, **raw_outputs}.items():
        path.write_bytes(data)
        path.chmod(0o600)
    stamp_draft(graph_root)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "freeze-nodes"))
    args = parser.parse_args()
    try:
        result = assess()[0] if args.command == "check" else freeze_nodes()
    except GraphValidationError as exc:
        parser.exit(1, f"Pilot A node QC failed: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
