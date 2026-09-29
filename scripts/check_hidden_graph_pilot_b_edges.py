"""核验 Pilot B 新增方向的双人盲标、第三人裁决并冻结扩展结构图。"""

from __future__ import annotations

import argparse
import collections
import hashlib
import itertools
import json
import math
import shutil
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

from experiments.emergent_coordination.harness.cases import load_case
from scripts.hidden_opportunity_graph import (
    ACTIONABLE_TYPES,
    CASE_ID,
    PILOT_B_GRAPH_DIR,
    PILOT_B_GRAPH_VERSION,
    PRIVATE_GRAPH_DIR,
    GraphValidationError,
    _read_json,
    _read_jsonl,
    _require,
    _validate_edge,
    validate_graph,
)
from scripts.prepare_hidden_graph_pilot_b_boundaries import BOUNDARY_DIR
from scripts.prepare_hidden_graph_pilot_b_edges_round3 import ROUND3_DIR as EDGE_DIR, verify as verify_packet


TAXONOMY = ("none", "thematic-only", "direct relation", "actionable cross-check", "strong dependency")
REVIEW_KEYS = {
    "reviewer_id", "source_node", "target_node", "opportunity_type", "mechanisms", "source_artifact",
    "target_claim", "expected_effect", "bounded_check", "evidence", "rationale", "confidence", "uncertainty_note",
}
ADJUDICATION_KEYS = (REVIEW_KEYS - {"reviewer_id"}) | {"adjudicator_id"}


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _jsonl_bytes(values: list[dict[str, Any]]) -> bytes:
    return b"".join((json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8") for value in values)


def _pair(item: dict[str, Any]) -> tuple[str, str]:
    return item["source_node"], item["target_node"]


def _final_shape(item: dict[str, Any], reviewer_ids: list[str], status: str = "adjudicated") -> dict[str, Any]:
    source, target = _pair(item)
    return {
        **{key: value for key, value in item.items() if key not in {"reviewer_id", "adjudicator_id"}},
        "edge_id": f"{PILOT_B_GRAPH_VERSION}:{source}:{target}",
        "direction": "source_to_target",
        "adjudication_status": status,
        "reviewer_ids": reviewer_ids,
    }


def _load_review(path: Path, pairs: set[tuple[str, str]], node_ids: set[str], *, third: bool = False,
                 complete: bool = True) -> tuple[str, dict[tuple[str, str], dict[str, Any]]]:
    _require(path.is_file() and not path.is_symlink(), f"missing or unsafe Pilot B edge review: {path.name}")
    rows = _read_jsonl(path)
    _require(not complete or len(rows) == len(pairs), f"{path.name}: incomplete directed pair review")
    keys = ADJUDICATION_KEYS if third else REVIEW_KEYS
    id_key = "adjudicator_id" if third else "reviewer_id"
    mapped = {}
    identities = set()
    target = load_case(CASE_ID).target_root
    for index, row in enumerate(rows, 1):
        where = f"{path.name}:{index}"
        _require(set(row) == keys, f"{where}: edge review schema mismatch")
        pair = _pair(row)
        _require(all(isinstance(item, str) for item in pair) and pair in pairs and pair not in mapped,
                 f"{where}: unexpected or duplicate direction")
        identity = row[id_key]
        _require(isinstance(identity, str) and identity.strip(), f"{where}: empty reviewer identity")
        _validate_edge(_final_shape(row, [identity]), where, target, node_ids, PILOT_B_GRAPH_VERSION)
        mapped[pair] = row
        identities.add(identity)
    _require(len(identities) == 1 and (not complete or set(mapped) == pairs),
             f"{path.name}: inconsistent reviewer or pair coverage")
    return identities.pop(), mapped


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


def _frozen_report() -> dict[str, Any]:
    graph = validate_graph(PILOT_B_GRAPH_DIR)
    _require(graph["status"] == "valid_frozen", "Pilot B graph is not frozen")
    report = _read_json(EDGE_DIR / "edge_qc.json")
    _require(report["status"] == "frozen" and report["total_node_count"] == graph["node_count"]
             and report["total_directed_pair_count"] == graph["directed_pair_count"],
             "frozen Pilot B edge QC report mismatch")
    for name, key in (
        ("graph_manifest.json", "graph_manifest_sha256"), ("nodes.jsonl", "nodes_sha256"),
        ("edges.jsonl", "edges_sha256"), ("node_reviews.jsonl", "node_reviews_sha256"),
        ("edge_reviews.jsonl", "edge_reviews_sha256"), ("adjudications.jsonl", "adjudications_sha256"),
    ):
        _require(report[key] == _digest((PILOT_B_GRAPH_DIR / name).read_bytes()), f"frozen {name} digest mismatch")
    for name, digest in (
        ("edge_packet_manifest.json", report["edge_packet_manifest_sha256"]),
        ("edge_reviewer_bundle.json", report["reviewer_bundle_sha256"]),
        ("reviews/reviewer_a.jsonl", report["review_file_sha256"]["reviewer_a"]),
        ("reviews/reviewer_b.jsonl", report["review_file_sha256"]["reviewer_b"]),
    ):
        _require(digest == _digest((EDGE_DIR / name).read_bytes()), f"frozen private {name} digest mismatch")
    if report["adjudication_file_sha256"]:
        _require(report["adjudication_file_sha256"] == _digest((EDGE_DIR / "reviews/adjudicator.jsonl").read_bytes()),
                 "frozen Pilot B edge adjudicator digest mismatch")
    _require(report["pilot_a_graph_manifest_sha256"] == _digest((PRIVATE_GRAPH_DIR / "graph_manifest.json").read_bytes())
             and report["node_boundary_qc_sha256"] == _digest((BOUNDARY_DIR / "node_boundary_qc.json").read_bytes())
             and report["nodes_sha256"] == _digest((BOUNDARY_DIR / "nodes_frozen.jsonl").read_bytes()),
             "frozen Pilot A or Pilot B node provenance mismatch")
    first_edges = {_pair(item): item for item in _read_jsonl(PRIVATE_GRAPH_DIR / "edges.jsonl")}
    second_edges = {_pair(item): item for item in _read_jsonl(PILOT_B_GRAPH_DIR / "edges.jsonl")}
    _require(len(first_edges) == 30 and len(second_edges) == graph["directed_pair_count"],
             "frozen inherited pair universe mismatch")
    for pair, original in first_edges.items():
        inherited = {**original, "edge_id": f"{PILOT_B_GRAPH_VERSION}:{pair[0]}:{pair[1]}"}
        _require(second_edges[pair] == inherited, f"frozen Pilot A edge changed in extension: {pair}")
    return report


def assess() -> tuple[dict[str, Any], dict[str, Any]]:
    graph_status = validate_graph(PILOT_B_GRAPH_DIR)["status"]
    if graph_status == "valid_frozen":
        return _frozen_report(), {}
    packet = verify_packet()
    bundle = _read_json(EDGE_DIR / "edge_reviewer_bundle.json")
    nodes = bundle["nodes"]
    node_ids = {item["node_id"] for item in nodes}
    ordered = [_pair(item) for item in bundle["directed_pairs_to_review"]]
    pairs = set(ordered)
    expected = len(nodes) * (len(nodes) - 1) - 30
    _require(7 <= len(nodes) <= 16 and len(node_ids) == len(nodes)
             and len(ordered) == len(pairs) == expected,
             "Pilot B new directed pair universe changed")
    review_dir = EDGE_DIR / "reviews"
    a_path, b_path = review_dir / "reviewer_a.jsonl", review_dir / "reviewer_b.jsonl"
    missing = [path.name for path in (a_path, b_path) if not path.is_file()]
    if missing:
        return {**packet, "status": "pending_independent_edge_reviews", "missing": missing}, {}
    a_id, a = _load_review(a_path, pairs, node_ids)
    b_id, b = _load_review(b_path, pairs, node_ids)
    _require(a_id != b_id, "Pilot B edge reviewers must be distinct")
    binary = sum((a[p]["opportunity_type"] in ACTIONABLE_TYPES)
                 == (b[p]["opportunity_type"] in ACTIONABLE_TYPES) for p in ordered)
    exact = sum(a[p]["opportunity_type"] == b[p]["opportunity_type"] for p in ordered)
    positive_disagreements = [p for p in ordered if (a[p]["opportunity_type"] in ACTIONABLE_TYPES)
                              != (b[p]["opportunity_type"] in ACTIONABLE_TYPES)]
    needed = {p for p in ordered if a[p]["opportunity_type"] != b[p]["opportunity_type"]
              or a[p]["uncertainty_note"] or b[p]["uncertainty_note"]}
    third_path = review_dir / "adjudicator.jsonl"
    if needed and not third_path.is_file():
        return {
            **packet, "status": "pending_third_edge_adjudication", "reviewer_ids": [a_id, b_id],
            "binary_agreement_count": binary, "binary_agreement_denominator": len(ordered),
            "needs_adjudication": [list(p) for p in sorted(needed)],
            "positive_disagreements": [list(p) for p in positive_disagreements],
        }, {}
    if needed:
        third_id, third = _load_review(third_path, needed, node_ids, third=True)
        _require(third_id not in {a_id, b_id}, "Pilot B edge adjudicator must be a third independent reviewer")
    else:
        _require(not third_path.exists() or not _read_jsonl(third_path), "unexpected Pilot B edge adjudications")
        third_id, third = None, {}
    final = []
    for p in ordered:
        raw = third.get(p, a[p])
        status = "uncertain" if raw["uncertainty_note"] else "adjudicated"
        edge = _final_shape(raw, [a_id, b_id], status)
        _validate_edge(edge, f"final[{p[0]}->{p[1]}]", load_case(CASE_ID).target_root,
                       node_ids, PILOT_B_GRAPH_VERSION)
        final.append(edge)
    dyads = {tuple(sorted(p)) for p in ordered}
    direction_disagreements = []
    for left, right in sorted(dyads):
        options = ((left, right), (right, left))
        aa = {p for p in options if a[p]["opportunity_type"] in ACTIONABLE_TYPES}
        bb = {p for p in options if b[p]["opportunity_type"] in ACTIONABLE_TYPES}
        if aa != bb:
            direction_disagreements.append((left, right))
    categories_a = collections.Counter(a[p]["opportunity_type"] for p in ordered)
    categories_b = collections.Counter(b[p]["opportunity_type"] for p in ordered)
    categories_final = collections.Counter(edge["opportunity_type"] for edge in final)
    uncertain = [edge for edge in final if edge["adjudication_status"] == "uncertain"]
    actionable = sum(edge["adjudication_status"] == "adjudicated"
                     and edge["opportunity_type"] in ACTIONABLE_TYPES for edge in final)
    threshold = math.ceil(0.9 * len(ordered))
    report = {
        "status": "qc_failed_reblind_required" if binary < threshold else "ready_to_freeze_pilot_b_edges",
        "case_id": CASE_ID,
        "graph_version": PILOT_B_GRAPH_VERSION,
        "qc_date": date.today().isoformat(),
        "input_lock_sha256": bundle["input_lock_sha256"],
        "pilot_a_graph_manifest_sha256": bundle["pilot_a_graph_manifest_sha256"],
        "node_boundary_qc_sha256": bundle["node_boundary_qc_sha256"],
        "edge_packet_manifest_sha256": packet["edge_packet_manifest_sha256"],
        "reviewer_bundle_sha256": packet["edge_reviewer_bundle_sha256"],
        "reviewer_ids": [a_id, b_id],
        "adjudicator_id": third_id,
        "review_file_sha256": {"reviewer_a": _digest(a_path.read_bytes()), "reviewer_b": _digest(b_path.read_bytes())},
        "adjudication_file_sha256": _digest(third_path.read_bytes()) if third_path.is_file() else None,
        "total_node_count": len(nodes),
        "inherited_pilot_a_pair_count": 30,
        "new_directed_pair_count": len(ordered),
        "total_directed_pair_count": len(nodes) * (len(nodes) - 1),
        "binary_agreement_count": binary,
        "binary_agreement_threshold": threshold,
        "binary_agreement_rate": round(binary / len(ordered), 6),
        "exact_agreement_count": exact,
        "exact_agreement_rate": round(exact / len(ordered), 6),
        "quadratic_weighted_kappa": _weighted_kappa(a, b),
        "confusion_matrix": {left: {right: sum(a[p]["opportunity_type"] == left
                                                and b[p]["opportunity_type"] == right for p in ordered)
                                   for right in TAXONOMY} for left in TAXONOMY},
        "categories_reviewer_a": {key: categories_a[key] for key in TAXONOMY},
        "categories_reviewer_b": {key: categories_b[key] for key in TAXONOMY},
        "categories_final_new": {key: categories_final[key] for key in TAXONOMY},
        "actionable_confirmed_new_lower_bound": actionable,
        "actionable_uncertainty_new_upper_bound": actionable + len(uncertain),
        "positive_disagreements": [list(p) for p in positive_disagreements],
        "direction_agreement_count": len(dyads) - len(direction_disagreements),
        "direction_agreement_denominator": len(dyads),
        "direction_disagreements": [list(p) for p in direction_disagreements],
        "adjudicated_disagreement_count": len(third),
        "uncertain_new_edges": [[_pair(edge)[0], _pair(edge)[1]] for edge in uncertain],
        "final_actionable_anchor_pairs_verified": sum(edge["opportunity_type"] in ACTIONABLE_TYPES
                                                      and {"source", "target"} <= {ref["role"] for ref in edge["evidence"]}
                                                      for edge in final),
    }
    return report, {"a": a, "b": b, "third": third, "final": final, "ordered": ordered}


def freeze_edges() -> dict[str, Any]:
    if validate_graph(PILOT_B_GRAPH_DIR)["status"] == "valid_frozen":
        return _frozen_report()
    report, sources = assess()
    _require(report["status"] == "ready_to_freeze_pilot_b_edges", f"Pilot B edge QC not passed: {report['status']}")
    old = _read_jsonl(PRIVATE_GRAPH_DIR / "edges.jsonl")
    inherited = [{**edge, "edge_id": f"{PILOT_B_GRAPH_VERSION}:{edge['source_node']}:{edge['target_node']}"}
                 for edge in old]
    all_edges = {_pair(edge): edge for edge in inherited + sources["final"]}
    nodes = _read_jsonl(BOUNDARY_DIR / "nodes_frozen.jsonl")
    ordered_pairs = [(a["node_id"], b["node_id"]) for a, b in itertools.permutations(nodes, 2)]
    _require(len(all_edges) == len(ordered_pairs) and set(all_edges) == set(ordered_pairs),
             "Pilot B final directed matrix is incomplete")
    previous_reviews = _read_jsonl(PRIVATE_GRAPH_DIR / "edge_reviews.jsonl")
    new_reviews = [sources["a"][p] for p in sources["ordered"]]
    new_reviews += [sources["b"][p] for p in sources["ordered"]]
    previous_adjudications = _read_jsonl(PILOT_B_GRAPH_DIR / "adjudications.jsonl")
    new_adjudications = [{
        "kind": "edge",
        "item_id": f"{PILOT_B_GRAPH_VERSION}:{p[0]}:{p[1]}",
        "adjudicator_id": item["adjudicator_id"],
        "decision": item["opportunity_type"],
        "rationale": item["rationale"],
        "reviewer_ids": report["reviewer_ids"],
        **({"uncertainty_note": item["uncertainty_note"]} if item["uncertainty_note"] else {}),
    } for p, item in sorted(sources["third"].items())]
    data = {
        "nodes.jsonl": _jsonl_bytes(nodes),
        "edges.jsonl": _jsonl_bytes([all_edges[p] for p in ordered_pairs]),
        "edge_reviews.jsonl": _jsonl_bytes(previous_reviews + new_reviews),
        "adjudications.jsonl": _jsonl_bytes(previous_adjudications + new_adjudications),
    }
    root = PILOT_B_GRAPH_DIR
    _require(not (root / "nodes.jsonl").read_bytes() and not (root / "edges.jsonl").read_bytes()
             and not (root / "edge_reviews.jsonl").read_bytes(),
             "Pilot B main graph already contains structural annotations")
    manifest = _read_json(root / "graph_manifest.json")
    _require(manifest["adjudication_status"] == "draft", "Pilot B graph is no longer a draft")
    for key, name in (("nodes_sha256", "nodes.jsonl"), ("edges_sha256", "edges.jsonl"),
                      ("edge_reviews_sha256", "edge_reviews.jsonl"),
                      ("adjudications_sha256", "adjudications.jsonl")):
        manifest[key] = _digest(data[name])
    manifest["adjudication_status"] = "frozen"
    manifest["adjudication_date"] = date.today().isoformat()
    manifest_bytes = _json_bytes(manifest)
    with tempfile.TemporaryDirectory(prefix="coordaudit-pilot-b-edge-preflight-") as temporary:
        shadow = Path(temporary) / PILOT_B_GRAPH_VERSION
        shutil.copytree(root, shadow)
        for name, payload in {**data, "graph_manifest.json": manifest_bytes}.items():
            (shadow / name).write_bytes(payload)
        _require(validate_graph(shadow)["status"] == "valid_frozen", "Pilot B frozen graph preflight failed")
    for name, payload in {**data, "graph_manifest.json": manifest_bytes}.items():
        path = root / name
        _require(not path.is_symlink(), f"unsafe Pilot B graph path: {name}")
        path.write_bytes(payload)
        path.chmod(0o600)
    _require(validate_graph(root)["status"] == "valid_frozen", "Pilot B frozen graph validation failed")
    report.update({
        "status": "frozen",
        "nodes_sha256": _digest(data["nodes.jsonl"]),
        "edges_sha256": _digest(data["edges.jsonl"]),
        "node_reviews_sha256": _digest((root / "node_reviews.jsonl").read_bytes()),
        "edge_reviews_sha256": _digest(data["edge_reviews.jsonl"]),
        "adjudications_sha256": _digest(data["adjudications.jsonl"]),
        "graph_manifest_sha256": _digest(manifest_bytes),
    })
    path = EDGE_DIR / "edge_qc.json"
    _require(not path.exists(), "Pilot B frozen edge QC report already exists")
    path.write_bytes(_json_bytes(report))
    path.chmod(0o600)
    return _frozen_report()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "freeze-edges"))
    args = parser.parse_args()
    try:
        result = assess()[0] if args.command == "check" else freeze_edges()
    except GraphValidationError as exc:
        parser.exit(1, f"Pilot B edge QC failed: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
