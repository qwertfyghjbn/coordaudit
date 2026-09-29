"""核验 Pilot A 双人有向边标注，裁决分歧并冻结私有校准 graph。"""

from __future__ import annotations

import argparse
import collections
import hashlib
import itertools
import json
import shutil
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

from experiments.emergent_coordination.harness.cases import load_case
from scripts.hidden_opportunity_graph import (
    ACTIONABLE_TYPES,
    CASE_ID,
    GRAPH_VERSION,
    OPPORTUNITY_TYPES,
    PRIVATE_GRAPH_DIR,
    GraphValidationError,
    _read_json,
    _read_jsonl,
    _require,
    _validate_edge,
    validate_graph,
)
from scripts.prepare_hidden_graph_pilot_a_edges import EDGE_DIR, verify as verify_edge_packet
from scripts.prepare_hidden_graph_pilot_a_edges_round2 import ROUND2_DIR, verify as verify_round2_packet


TAXONOMY = ("none", "thematic-only", "direct relation", "actionable cross-check", "strong dependency")
REVIEW_KEYS = {
    "reviewer_id", "source_node", "target_node", "opportunity_type", "mechanisms", "source_artifact",
    "target_claim", "expected_effect", "bounded_check", "evidence", "rationale", "confidence", "uncertainty_note"
}
ADJUDICATION_KEYS = (REVIEW_KEYS - {"reviewer_id"}) | {"adjudicator_id"}


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _jsonl_bytes(records: list[dict[str, Any]]) -> bytes:
    return b"".join((json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8") for item in records)


def _pair(record: dict[str, Any]) -> tuple[str, str]:
    return record["source_node"], record["target_node"]


def _final_shape(record: dict[str, Any], reviewer_ids: list[str], status: str = "adjudicated") -> dict[str, Any]:
    return {
        **{key: value for key, value in record.items() if key not in {"reviewer_id", "adjudicator_id"}},
        "edge_id": f"{GRAPH_VERSION}:{record['source_node']}:{record['target_node']}",
        "direction": "source_to_target",
        "adjudication_status": status,
        "reviewer_ids": reviewer_ids,
    }


def _load_records(
    path: Path,
    expected_pairs: set[tuple[str, str]],
    node_ids: set[str],
    target: Path,
    *,
    adjudicator: bool = False,
) -> tuple[str, dict[tuple[str, str], dict[str, Any]]]:
    _require(path.is_file() and not path.is_symlink(), f"missing or unsafe review file: {path.name}")
    records = _read_jsonl(path)
    _require(len(records) == len(expected_pairs), f"{path.name}: expected {len(expected_pairs)} directed rows")
    keyset = ADJUDICATION_KEYS if adjudicator else REVIEW_KEYS
    id_key = "adjudicator_id" if adjudicator else "reviewer_id"
    mapped = {}
    ids = set()
    for index, record in enumerate(records):
        where = f"{path.name}:{index + 1}"
        _require(set(record) == keyset, f"{where}: edge review schema mismatch")
        pair = _pair(record)
        _require(pair in expected_pairs and pair not in mapped, f"{where}: unexpected or duplicate direction")
        identity = record[id_key]
        _require(isinstance(identity, str) and identity.strip(), f"{where}: empty reviewer identity")
        _validate_edge(_final_shape(record, [identity]), where, target, node_ids, GRAPH_VERSION)
        ids.add(identity)
        mapped[pair] = record
    _require(len(ids) == 1 and set(mapped) == expected_pairs, f"{path.name}: reviewer identity or coverage mismatch")
    return ids.pop(), mapped


def _weighted_kappa(a: dict[tuple[str, str], dict[str, Any]], b: dict[tuple[str, str], dict[str, Any]]) -> float | None:
    pairs = list(a)
    n = len(pairs)
    counts_a = collections.Counter(a[p]["opportunity_type"] for p in pairs)
    counts_b = collections.Counter(b[p]["opportunity_type"] for p in pairs)
    positions = {category: index for index, category in enumerate(TAXONOMY)}
    observed = sum((positions[a[p]["opportunity_type"]] - positions[b[p]["opportunity_type"]]) ** 2 for p in pairs) / n
    expected = sum(
        (positions[left] - positions[right]) ** 2 * counts_a[left] * counts_b[right]
        for left in TAXONOMY for right in TAXONOMY
    ) / (n * n)
    return round(1 - observed / expected, 6) if expected else (1.0 if observed == 0 else None)


def _frozen_report(directory: Path) -> dict[str, Any]:
    validation = validate_graph(PRIVATE_GRAPH_DIR)
    _require(validation["status"] == "valid_frozen", "graph is not frozen")
    path = directory / "edge_qc.json"
    report = _read_json(path)
    _require(report["status"] == "frozen" and report["edge_count"] == validation["directed_pair_count"],
             "frozen edge QC report mismatch")
    for name, key in (
        ("nodes.jsonl", "nodes_sha256"), ("edges.jsonl", "edges_sha256"),
        ("edge_reviews.jsonl", "edge_reviews_sha256"), ("adjudications.jsonl", "adjudications_sha256"),
        ("graph_manifest.json", "graph_manifest_sha256"),
    ):
        _require(report[key] == _digest((PRIVATE_GRAPH_DIR / name).read_bytes()), f"frozen {name} digest mismatch")
    for name, digest in (
        ("edge_packet_manifest.json", report["edge_packet_manifest_sha256"]),
        ("edge_reviewer_bundle.json", report["reviewer_bundle_sha256"]),
        ("reviews/reviewer_a.jsonl", report["review_file_sha256"]["reviewer_a"]),
        ("reviews/reviewer_b.jsonl", report["review_file_sha256"]["reviewer_b"]),
    ):
        _require(digest == _digest((directory / name).read_bytes()), f"frozen private {name} digest mismatch")
    if report["adjudication_file_sha256"]:
        _require(report["adjudication_file_sha256"] == _digest((directory / "reviews/adjudicator.jsonl").read_bytes()),
                 "frozen private adjudicator digest mismatch")
    packet_manifest = _read_json(directory / "edge_packet_manifest.json")
    if "calibration_rules_sha256" in packet_manifest:
        _require(packet_manifest["calibration_rules_sha256"] == _digest((directory / "calibration_rules.json").read_bytes()),
                 "frozen calibration rules digest mismatch")
        _require(report["calibration_rules_sha256"] == packet_manifest["calibration_rules_sha256"],
                 "frozen calibration rules report mismatch")
        _require(report["round1_failed_qc_sha256"] == packet_manifest["round1_failed_qc_sha256"]
                 == _digest((EDGE_DIR / "edge_round1_qc.json").read_bytes()),
                 "frozen first-round QC provenance mismatch")
        first_packet = _read_json(EDGE_DIR / "edge_packet_manifest.json")
        node_qc = _read_json(directory.parent / "node_boundary_qc.json")
        first_qc = _read_json(EDGE_DIR / "edge_round1_qc.json")
        _require(packet_manifest["base_ungraded_packet_sha256"] == first_packet["edge_reviewer_bundle_sha256"]
                 == first_qc["reviewer_bundle_sha256"]
                 == _digest((EDGE_DIR / "edge_reviewer_bundle.json").read_bytes()),
                 "frozen first-round packet provenance mismatch")
        _require(first_qc["edge_packet_manifest_sha256"] == _digest((EDGE_DIR / "edge_packet_manifest.json").read_bytes())
                 and first_qc["status"] == "qc_failed_reblind_required"
                 and first_qc["binary_agreement_count"] < 27,
                 "frozen first-round failure provenance mismatch")
        for reviewer in ("reviewer_a", "reviewer_b"):
            _require(first_qc["review_file_sha256"][reviewer]
                     == _digest((EDGE_DIR / "reviews" / f"{reviewer}.jsonl").read_bytes()),
                     f"frozen first-round {reviewer} provenance mismatch")
        _require(first_qc["adjudication_file_sha256"]
                 == _digest((EDGE_DIR / "reviews/adjudicator.jsonl").read_bytes()),
                 "frozen first-round adjudication provenance mismatch")
        _require(first_packet["node_boundary_qc_sha256"]
                 == _digest((directory.parent / "node_boundary_qc.json").read_bytes())
                 and first_packet["nodes_frozen_sha256"] == node_qc["nodes_frozen_sha256"]
                 == packet_manifest["nodes_frozen_sha256"]
                 == _digest((directory.parent / "nodes_frozen.jsonl").read_bytes())
                 == report["nodes_sha256"],
                 "frozen node-boundary provenance mismatch")
        for reviewer in ("reviewer_a", "reviewer_b"):
            _require(node_qc["review_file_sha256"][reviewer]
                     == _digest((directory.parent / "reviews" / f"{reviewer}.jsonl").read_bytes()),
                     f"frozen node-boundary {reviewer} provenance mismatch")
    return report


def assess(directory: Path = EDGE_DIR) -> tuple[dict[str, Any], dict[str, Any]]:
    graph_status = validate_graph(PRIVATE_GRAPH_DIR)["status"]
    if graph_status == "valid_frozen":
        return _frozen_report(directory), {}
    packet = verify_round2_packet(directory) if directory.resolve() == ROUND2_DIR.resolve() else verify_edge_packet(directory)
    bundle = _read_json(directory / "edge_reviewer_bundle.json")
    node_ids = {node["node_id"] for node in bundle["nodes"]}
    pairs = [_pair(item) for item in bundle["directed_pairs"]]
    expected = set(pairs)
    _require(len(node_ids) == 6 and len(expected) == 30 and len(pairs) == 30, "Pilot A edge universe changed")
    review_dir = directory / "reviews"
    a_path, b_path = review_dir / "reviewer_a.jsonl", review_dir / "reviewer_b.jsonl"
    missing = [path.name for path in (a_path, b_path) if not path.is_file()]
    if missing:
        return {**packet, "status": "pending_independent_edge_reviews", "missing": missing}, {}
    target = load_case(CASE_ID).target_root
    a_id, a = _load_records(a_path, expected, node_ids, target)
    b_id, b = _load_records(b_path, expected, node_ids, target)
    _require(a_id != b_id, "edge reviewers must be distinct")
    ordered = list(pairs)
    binary_agreement = sum((a[p]["opportunity_type"] in ACTIONABLE_TYPES) ==
                           (b[p]["opportunity_type"] in ACTIONABLE_TYPES) for p in ordered)
    exact_agreement = sum(a[p]["opportunity_type"] == b[p]["opportunity_type"] for p in ordered)
    positive_disagreements = [p for p in ordered if (a[p]["opportunity_type"] in ACTIONABLE_TYPES) !=
                              (b[p]["opportunity_type"] in ACTIONABLE_TYPES)]
    needed = {
        p for p in ordered if a[p]["opportunity_type"] != b[p]["opportunity_type"]
        or a[p]["uncertainty_note"] or b[p]["uncertainty_note"]
    }
    unordered = list(itertools.combinations(sorted(node_ids), 2))
    direction_disagreements = []
    for left, right in unordered:
        directions_a = {pair for pair in ((left, right), (right, left))
                        if a[pair]["opportunity_type"] in ACTIONABLE_TYPES}
        directions_b = {pair for pair in ((left, right), (right, left))
                        if b[pair]["opportunity_type"] in ACTIONABLE_TYPES}
        if directions_a != directions_b:
            direction_disagreements.append((left, right))
    adjudication_path = review_dir / "adjudicator.jsonl"
    if needed and not adjudication_path.is_file():
        return {
            **packet,
            "status": "pending_third_edge_adjudication",
            "reviewer_ids": [a_id, b_id],
            "binary_agreement_count": binary_agreement,
            "binary_agreement_rate": round(binary_agreement / 30, 6),
            "exact_agreement_count": exact_agreement,
            "positive_disagreements": [list(p) for p in positive_disagreements],
            "needs_adjudication": [list(p) for p in sorted(needed)],
        }, {}
    if needed:
        third_id, adjudications = _load_records(adjudication_path, needed, node_ids, target, adjudicator=True)
        _require(third_id not in {a_id, b_id}, "edge adjudicator must be a third independent reviewer")
    else:
        _require(not adjudication_path.exists() or not _read_jsonl(adjudication_path),
                 "unexpected edge adjudication records")
        third_id, adjudications = None, {}
    final = []
    for pair in ordered:
        raw = adjudications[pair] if pair in adjudications else a[pair]
        status = "uncertain" if raw["uncertainty_note"] else "adjudicated"
        edge = _final_shape(raw, [a_id, b_id], status)
        _validate_edge(edge, f"final[{pair[0]}->{pair[1]}]", target, node_ids, GRAPH_VERSION)
        final.append(edge)
    categories_a = collections.Counter(a[p]["opportunity_type"] for p in ordered)
    categories_b = collections.Counter(b[p]["opportunity_type"] for p in ordered)
    categories_final = collections.Counter(item["opportunity_type"] for item in final)
    final_by_pair = {_pair(item): item for item in final}
    uncertain_count = sum(item["adjudication_status"] == "uncertain" for item in final)
    confirmed_actionable = sum(item["adjudication_status"] == "adjudicated"
                               and item["opportunity_type"] in ACTIONABLE_TYPES for item in final)
    control_pairs = {
        "shared_helper_R04_R20": ("F001", "F004"),
        "credential_negative_R04_NM04": ("F001", "F005"),
        "credential_negative_R05_NM04": ("F002", "F005"),
        "credential_negative_R06_NM04": ("F003", "F005"),
        "same_file_different_invariant_R20_R19": ("F004", "F006"),
    }
    confusion = {
        left: {right: sum(a[p]["opportunity_type"] == left and b[p]["opportunity_type"] == right for p in ordered)
               for right in TAXONOMY}
        for left in TAXONOMY
    }
    insufficient = binary_agreement < 27
    status = "qc_failed_reblind_required" if insufficient else "ready_to_freeze_pilot_a_edges"
    report = {
        "status": status,
        "case_id": CASE_ID,
        "graph_version": GRAPH_VERSION,
        "qc_date": date.today().isoformat(),
        "input_lock_sha256": bundle["input_lock_sha256"],
        "edge_packet_manifest_sha256": packet["edge_packet_manifest_sha256"],
        "reviewer_bundle_sha256": packet["edge_reviewer_bundle_sha256"],
        "calibration_rules_sha256": _read_json(directory / "edge_packet_manifest.json").get("calibration_rules_sha256"),
        "round1_failed_qc_sha256": _read_json(directory / "edge_packet_manifest.json").get("round1_failed_qc_sha256"),
        "reviewer_ids": [a_id, b_id],
        "adjudicator_id": third_id,
        "review_file_sha256": {"reviewer_a": _digest(a_path.read_bytes()), "reviewer_b": _digest(b_path.read_bytes())},
        "adjudication_file_sha256": _digest(adjudication_path.read_bytes()) if adjudication_path.exists() else None,
        "edge_count": 30,
        "binary_agreement_count": binary_agreement,
        "binary_agreement_rate": round(binary_agreement / 30, 6),
        "binary_gate_passed": not insufficient,
        "exact_agreement_count": exact_agreement,
        "exact_agreement_rate": round(exact_agreement / 30, 6),
        "quadratic_weighted_kappa": _weighted_kappa(a, b),
        "confusion_matrix": confusion,
        "categories_reviewer_a": {key: categories_a[key] for key in TAXONOMY},
        "categories_reviewer_b": {key: categories_b[key] for key in TAXONOMY},
        "categories_final": {key: categories_final[key] for key in TAXONOMY},
        "actionable_confirmed_lower_bound": confirmed_actionable,
        "actionable_uncertainty_upper_bound": confirmed_actionable + uncertain_count,
        "control_directions": {
            name: [
                {"source_node": source, "target_node": target,
                 "opportunity_type": final_by_pair[(source, target)]["opportunity_type"],
                 "adjudication_status": final_by_pair[(source, target)]["adjudication_status"]}
                for source, target in (pair, pair[::-1])
            ]
            for name, pair in control_pairs.items()
        },
        "positive_disagreements": [list(p) for p in positive_disagreements],
        "direction_agreement_count": len(unordered) - len(direction_disagreements),
        "direction_agreement_rate": round((len(unordered) - len(direction_disagreements)) / 15, 6),
        "direction_disagreements": [list(p) for p in direction_disagreements],
        "adjudicated_disagreement_count": len(adjudications),
        "uncertain_edges": [[item["source_node"], item["target_node"]] for item in final
                            if item["adjudication_status"] == "uncertain"],
        "final_actionable_anchor_pairs_verified": sum(
            item["opportunity_type"] in ACTIONABLE_TYPES
            and {"source", "target"} <= {ref["role"] for ref in item["evidence"]}
            for item in final
        ),
    }
    return report, {"a": a, "b": b, "adjudications": adjudications, "final": final}


def freeze_edges(directory: Path = EDGE_DIR) -> dict[str, Any]:
    if validate_graph(PRIVATE_GRAPH_DIR)["status"] == "valid_frozen":
        return _frozen_report(directory)
    report, sources = assess(directory)
    _require(report["status"] == "ready_to_freeze_pilot_a_edges", f"edge QC not passed: {report['status']}")
    graph_root = PRIVATE_GRAPH_DIR
    a = sources["a"]
    b = sources["b"]
    ordered = [_pair(item) for item in _read_json(directory / "edge_reviewer_bundle.json")["directed_pairs"]]
    reviews = [a[p] for p in ordered] + [b[p] for p in ordered]
    previous_adjudications = _read_jsonl(graph_root / "adjudications.jsonl")
    edge_adjudications = [
        {
            "kind": "edge",
            "item_id": f"{GRAPH_VERSION}:{pair[0]}:{pair[1]}",
            "adjudicator_id": item["adjudicator_id"],
            "decision": item["opportunity_type"],
            "rationale": item["rationale"],
            "reviewer_ids": report["reviewer_ids"],
            **({"uncertainty_note": item["uncertainty_note"]} if item["uncertainty_note"] else {}),
        }
        for pair, item in sorted(sources["adjudications"].items())
    ]
    data = {
        "nodes.jsonl": (directory.parent / "nodes_frozen.jsonl").read_bytes(),
        "edges.jsonl": _jsonl_bytes(sources["final"]),
        "edge_reviews.jsonl": _jsonl_bytes(reviews),
        "adjudications.jsonl": _jsonl_bytes(previous_adjudications + edge_adjudications),
    }
    _require(not (graph_root / "nodes.jsonl").read_bytes() and not (graph_root / "edges.jsonl").read_bytes()
             and not (graph_root / "edge_reviews.jsonl").read_bytes(),
             "main graph already contains edge annotations")
    manifest = _read_json(graph_root / "graph_manifest.json")
    _require(manifest["adjudication_status"] == "draft", "main graph is no longer a draft")
    for key, filename in (
        ("nodes_sha256", "nodes.jsonl"), ("edges_sha256", "edges.jsonl"),
        ("edge_reviews_sha256", "edge_reviews.jsonl"), ("adjudications_sha256", "adjudications.jsonl"),
    ):
        manifest[key] = _digest(data[filename])
    manifest["adjudication_status"] = "frozen"
    manifest["adjudication_date"] = date.today().isoformat()
    manifest_bytes = _json_bytes(manifest)
    with tempfile.TemporaryDirectory(prefix="coordaudit-pilot-a-edge-preflight-") as temporary:
        shadow = Path(temporary) / "graph-v1"
        shutil.copytree(graph_root, shadow)
        for name, payload in {**data, "graph_manifest.json": manifest_bytes}.items():
            (shadow / name).write_bytes(payload)
        _require(validate_graph(shadow)["status"] == "valid_frozen", "frozen graph preflight failed")
    for name, payload in {**data, "graph_manifest.json": manifest_bytes}.items():
        path = graph_root / name
        _require(not path.is_symlink(), f"unsafe graph path: {name}")
        path.write_bytes(payload)
        path.chmod(0o600)
    _require(validate_graph(graph_root)["status"] == "valid_frozen", "frozen graph validation failed")
    report.update({
        "status": "frozen",
        "nodes_sha256": _digest(data["nodes.jsonl"]),
        "edges_sha256": _digest(data["edges.jsonl"]),
        "edge_reviews_sha256": _digest(data["edge_reviews.jsonl"]),
        "adjudications_sha256": _digest(data["adjudications.jsonl"]),
        "graph_manifest_sha256": _digest(manifest_bytes),
    })
    qc_path = directory / "edge_qc.json"
    _require(not qc_path.exists(), "frozen edge QC report already exists")
    qc_path.write_bytes(_json_bytes(report))
    qc_path.chmod(0o600)
    return _frozen_report(directory)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "freeze-edges"))
    parser.add_argument("--round", choices=("1", "2"), default="2")
    args = parser.parse_args()
    try:
        directory = EDGE_DIR if args.round == "1" else ROUND2_DIR
        result = assess(directory)[0] if args.command == "check" else freeze_edges(directory)
    except GraphValidationError as exc:
        parser.exit(1, f"Pilot A edge QC failed: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
