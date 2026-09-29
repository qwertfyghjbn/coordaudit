"""核验 Pilot B 所选节点的完整边界盲标；通过后锁定扩展节点语义。"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

from experiments.emergent_coordination.harness.cases import load_case
from scripts.hidden_opportunity_graph import (
    CASE_ID,
    PILOT_B_GRAPH_DIR,
    PILOT_B_GRAPH_VERSION,
    PRIVATE_GRAPH_DIR,
    GraphValidationError,
    _evidence,
    _read_json,
    _read_jsonl,
    _require,
    _validate_node,
    stamp_draft,
    validate_graph,
)
from scripts.prepare_hidden_graph_pilot_b_boundaries import BOUNDARY_DIR, verify as verify_packet


REVIEW_KEYS = {
    "reviewer_id", "candidate_a", "candidate_b", "security_question_a", "security_question_b",
    "decision", "counterfactual", "rationale", "evidence_refs",
}
ADJUDICATION_KEYS = (REVIEW_KEYS - {"reviewer_id"}) | {"adjudicator_id"}


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _jsonl_bytes(values: list[dict[str, Any]]) -> bytes:
    return b"".join((json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8") for value in values)


def _load_review(path: Path, pairs: set[tuple[str, str]], questions: dict[str, str], *, third: bool = False,
                 complete: bool = True) -> tuple[str, dict[tuple[str, str], dict[str, Any]]]:
    _require(path.is_file() and not path.is_symlink(), f"missing or unsafe boundary review: {path.name}")
    rows = _read_jsonl(path)
    _require(not complete or len(rows) == len(pairs), f"{path.name}: incomplete boundary pair review")
    expected_keys = ADJUDICATION_KEYS if third else REVIEW_KEYS
    id_key = "adjudicator_id" if third else "reviewer_id"
    mapped = {}
    identities = set()
    target = load_case(CASE_ID).target_root
    for index, row in enumerate(rows, 1):
        where = f"{path.name}:{index}"
        _require(set(row) == expected_keys, f"{where}: review schema mismatch")
        pair = (row["candidate_a"], row["candidate_b"])
        _require(all(isinstance(item, str) for item in pair) and pair in pairs and pair not in mapped,
                 f"{where}: unknown or duplicate boundary pair")
        identity = row[id_key]
        _require(isinstance(identity, str) and identity.strip(), f"{where}: empty reviewer identity")
        _require(row["security_question_a"] == questions[pair[0]]
                 and row["security_question_b"] == questions[pair[1]],
                 f"{where}: security question changed from blind bundle")
        _require(isinstance(row["decision"], str) and row["decision"] in {"split", "merge", "uncertain"},
                 f"{where}: invalid boundary decision")
        for key in ("counterfactual", "rationale"):
            _require(isinstance(row[key], str) and row[key].strip(), f"{where}: missing {key}")
        refs = row["evidence_refs"]
        _require(isinstance(refs, list) and len(refs) >= 2
                 and {"candidate_a", "candidate_b"} <= {ref.get("role") for ref in refs if isinstance(ref, dict)},
                 f"{where}: two-sided boundary evidence required")
        for ref_index, ref in enumerate(refs):
            _evidence(ref, f"{where}.evidence_refs[{ref_index}]", target)
        mapped[pair] = row
        identities.add(identity)
    _require(len(identities) == 1 and (not complete or set(mapped) == pairs),
             f"{path.name}: inconsistent reviewer or pair coverage")
    return identities.pop(), mapped


def assess(directory: Path = BOUNDARY_DIR) -> tuple[dict[str, Any], dict[str, Any]]:
    if directory == BOUNDARY_DIR and validate_graph(PILOT_B_GRAPH_DIR)["status"] == "valid_frozen":
        qc = _read_json(directory / "node_boundary_qc.json")
        nodes = _read_jsonl(directory / "nodes_frozen.jsonl")
        _require(qc["status"] == "ready_to_freeze_pilot_b_nodes"
                 and qc["nodes_frozen_sha256"] == _digest((directory / "nodes_frozen.jsonl").read_bytes())
                 and len(nodes) == 16 and qc["selected_node_count"] == 10,
                 "frozen Pilot B boundary QC report mismatch")
        return {
            **qc,
            "status": "frozen",
            "frozen_graph_status": "valid_frozen",
            "total_node_count": len(nodes),
            "total_directed_pair_denominator": len(nodes) * (len(nodes) - 1),
        }, {}
    packet = verify_packet()
    bundle = _read_json(directory / "boundary_reviewer_bundle.json")
    selected = bundle["selected_pilot_b_nodes_proposed"]
    all_nodes = bundle["pilot_a_nodes"] + selected
    questions = {node["node_id"]: node["security_question"] for node in all_nodes}
    ordered = [(item["candidate_a"], item["candidate_b"]) for item in bundle["unordered_pairs"]]
    pair_set = set(ordered)
    count = len(selected)
    _require(1 <= count <= 10 and len(questions) == 6 + count
             and len(ordered) == len(pair_set) == 6 * count + count * (count - 1) // 2,
             "Pilot B selected node or pair universe changed")
    review_dir = directory / "boundary_reviews"
    a_path, b_path = review_dir / "reviewer_a.jsonl", review_dir / "reviewer_b.jsonl"
    missing = [path.name for path in (a_path, b_path) if not path.is_file()]
    if missing:
        return {**packet, "status": "pending_independent_boundary_reviews", "missing": missing}, {}
    a_id, a = _load_review(a_path, pair_set, questions)
    b_id, b = _load_review(b_path, pair_set, questions)
    _require(a_id != b_id, "boundary reviewers must be distinct")
    agreement = sum(a[p]["decision"] == b[p]["decision"] for p in ordered)
    needed = {p for p in ordered if a[p]["decision"] != b[p]["decision"] or a[p]["decision"] == "uncertain"}
    third_path = review_dir / "adjudicator.jsonl"
    if needed and not third_path.is_file():
        return {
            **packet, "status": "pending_third_boundary_adjudication", "reviewer_ids": [a_id, b_id],
            "agreement_count": agreement, "agreement_denominator": len(ordered),
            "needs_adjudication": [list(p) for p in sorted(needed)],
        }, {}
    if needed:
        third_id, third = _load_review(third_path, needed, questions, third=True)
        _require(third_id not in {a_id, b_id}, "boundary adjudicator must be a third independent reviewer")
    else:
        _require(not third_path.exists() or not _read_jsonl(third_path), "unexpected boundary adjudication")
        third_id, third = None, {}
    final = {p: third.get(p, a[p]) for p in ordered}
    merged = [list(p) for p in ordered if final[p]["decision"] == "merge"]
    uncertain = [list(p) for p in ordered if final[p]["decision"] == "uncertain"]
    gate = math.ceil(0.9 * len(ordered))
    status = ("qc_failed_reblind_required" if agreement < gate else
              "unresolved_boundary" if uncertain else
              "selection_revision_required" if merged else "ready_to_freeze_pilot_b_nodes")
    report = {
        "status": status,
        "case_id": CASE_ID,
        "graph_version": PILOT_B_GRAPH_VERSION,
        "qc_date": date.today().isoformat(),
        "pilot_a_graph_manifest_sha256": bundle["pilot_a_graph_manifest_sha256"],
        "boundary_packet_manifest_sha256": packet["boundary_packet_manifest_sha256"],
        "selection_spec_sha256": bundle["selection_spec_sha256"],
        "reviewer_ids": [a_id, b_id],
        "adjudicator_id": third_id,
        "review_file_sha256": {"reviewer_a": _digest(a_path.read_bytes()), "reviewer_b": _digest(b_path.read_bytes())},
        "adjudication_file_sha256": _digest(third_path.read_bytes()) if third_path.is_file() else None,
        "selected_node_count": count,
        "total_node_count": len(all_nodes),
        "new_pair_count": len(ordered),
        "total_directed_pair_denominator": len(all_nodes) * (len(all_nodes) - 1),
        "agreement_count": agreement,
        "agreement_threshold": gate,
        "agreement_rate": round(agreement / len(ordered), 6),
        "adjudicated_pair_count": len(third),
        "merged_pairs": merged,
        "uncertain_pairs": uncertain,
        "final_pair_decisions": [{"candidate_a": p[0], "candidate_b": p[1], "decision": final[p]["decision"]}
                                 for p in ordered],
    }
    return report, {"a": a, "b": b, "third": third, "selected": selected, "ordered": ordered}


def freeze_nodes(directory: Path = BOUNDARY_DIR) -> dict[str, Any]:
    report, sources = assess(directory)
    _require(report["status"] == "ready_to_freeze_pilot_b_nodes", f"Pilot B boundary QC not passed: {report['status']}")
    pilot_a_nodes = _read_jsonl(PRIVATE_GRAPH_DIR / "nodes.jsonl")
    nodes = pilot_a_nodes + [
        {**node, "adjudication_status": "adjudicated",
         "boundary_rationale": node["boundary_rationale"]
         + " Pilot B selected-pair 双人边界 QC 全部裁为 split；反事实和源码链见私有原始记录及 node_boundary_qc.json。"}
        for node in sources["selected"]
    ]
    gt = _read_json(load_case(CASE_ID).ground_truth_path)
    roots, near = {item["id"] for item in gt["roots"]}, {item["id"] for item in gt["near_misses"]}
    target = load_case(CASE_ID).target_root
    for index, node in enumerate(nodes):
        _validate_node(node, f"Pilot B frozen node {index}", target, roots, near)
    a_reviews = _read_jsonl(PRIVATE_GRAPH_DIR / "node_reviews.jsonl")
    raw_reviews = a_reviews + [sources["a"][p] for p in sources["ordered"]]
    raw_reviews += [sources["b"][p] for p in sources["ordered"]]
    adjudications = _read_jsonl(PRIVATE_GRAPH_DIR / "adjudications.jsonl")
    adjudications += [{
        "kind": "node_boundary",
        "item_id": f"{PILOT_B_GRAPH_VERSION}:{p[0]}|{p[1]}",
        "adjudicator_id": item["adjudicator_id"],
        "decision": item["decision"],
        "rationale": f"{item['rationale']} 反事实：{item['counterfactual']}",
        "reviewer_ids": report["reviewer_ids"],
    } for p, item in sorted(sources["third"].items())]
    node_bytes = _jsonl_bytes(nodes)
    review_bytes = _jsonl_bytes(raw_reviews)
    adjudication_bytes = _jsonl_bytes(adjudications)
    report["nodes_frozen_sha256"] = _digest(node_bytes)
    report["node_reviews_sha256"] = _digest(review_bytes)
    report["adjudications_sha256"] = _digest(adjudication_bytes)
    outputs = {
        directory / "nodes_frozen.jsonl": node_bytes,
        directory / "node_boundary_qc.json": _json_bytes(report),
    }
    for path, data in outputs.items():
        _require(not path.is_symlink() and (not path.exists() or path.read_bytes() == data),
                 f"Pilot B frozen node artifact changed: {path.name}")
    main = {
        PILOT_B_GRAPH_DIR / "node_reviews.jsonl": review_bytes,
        PILOT_B_GRAPH_DIR / "adjudications.jsonl": adjudication_bytes,
    }
    _require(all(not path.read_bytes() for path in main), "Pilot B draft already contains node review logs")
    with tempfile.TemporaryDirectory(prefix="coordaudit-pilot-b-node-preflight-") as temporary:
        shadow = Path(temporary) / PILOT_B_GRAPH_VERSION
        shutil.copytree(PILOT_B_GRAPH_DIR, shadow)
        for path, data in main.items():
            (shadow / path.name).write_bytes(data)
        _require(stamp_draft(shadow, graph_version=PILOT_B_GRAPH_VERSION)["status"] == "valid_draft",
                 "Pilot B node freeze preflight failed")
    for path, data in main.items():
        path.write_bytes(data)
        path.chmod(0o600)
    stamp_draft(PILOT_B_GRAPH_DIR, graph_version=PILOT_B_GRAPH_VERSION)
    for path, data in outputs.items():
        path.write_bytes(data)
        path.chmod(0o600)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "freeze-nodes"))
    args = parser.parse_args()
    try:
        result = assess()[0] if args.command == "check" else freeze_nodes()
    except GraphValidationError as exc:
        parser.exit(1, f"Pilot B boundary QC failed: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
