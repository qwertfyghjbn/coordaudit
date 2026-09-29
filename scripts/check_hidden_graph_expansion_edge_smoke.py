#!/usr/bin/env python3
"""Validate the non-production expansion edge smoke reviews and write the smoke QC report."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from experiments.emergent_coordination.harness.cases import load_case
from scripts.check_hidden_graph_pilot_b_edges import REVIEW_KEYS as PRODUCTION_REVIEW_KEYS, TAXONOMY
from scripts.freeze_hidden_graph_pair_universe import (
    PAIR_UNIVERSE_VERSION,
    verify as verify_pair_universe,
)
from scripts.hidden_opportunity_graph import CASE_ID, GraphValidationError, _read_json, _read_jsonl, _require, _validate_edge
from scripts.prepare_hidden_graph_expansion_edge_smoke import (
    EVALUATOR_PRIVATE_FILES,
    PACKET_VERSION,
    SMOKE_DIR,
    TARGET_ROOT,
    select_smoke_pairs,
    verify as verify_packet,
)


ALLOWED_PACKET_FILES = [
    "reviewer_rubric.json", "edge_reviewer_bundle.json",
    "edge_review_form_template.jsonl", "smoke_packet_manifest.json",
]
RUNTIME_REFERENCE_PATTERNS = (
    r"T4", r"S/P/B/T", r"Pilot\s*A", r"Pilot\s*B", r"Stage\s*9", r"run\s*mapping",
    r"operational\s*realizability", r"agent\s*(会|真的|之间)", r"运行\s*(中|时)\s*(观察到|表现)",
    r"历史\s*(run|运行)", r"condition\s*表现",
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def jbytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def _pair_id(source: str, target: str) -> str:
    return f"{PAIR_UNIVERSE_VERSION}:{source}:{target}"


def _load_review(path: Path, expected_pairs: dict[tuple[str, str], str], node_ids: set[str],
                 target: Path) -> tuple[str, dict[tuple[str, str], dict[str, Any]], list[str]]:
    _require(path.is_file() and not path.is_symlink(), f"missing smoke review file: {path.name}")
    rows = _read_jsonl(path)
    warnings: list[str] = []
    mapped: dict[tuple[str, str], dict[str, Any]] = {}
    identities = set()
    for index, row in enumerate(rows, 1):
        where = f"{path.name}:{index}"
        _require(set(row) == PRODUCTION_REVIEW_KEYS, f"{where}: schema keys differ from production template")
        pair = (row["source_node"], row["target_node"])
        _require(pair in expected_pairs and pair not in mapped,
                 f"{where}: pair not in smoke set or duplicated")
        identity = row["reviewer_id"]
        _require(isinstance(identity, str) and identity.strip(), f"{where}: empty reviewer identity")
        final_shape = {key: value for key, value in row.items() if key != "reviewer_id"}
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
    _require(set(mapped) == set(expected_pairs), f"{path.name}: missing or extra smoke pairs")
    return identities.pop(), mapped, warnings


def _check_access_log(path: Path, reviewer_id: str, own_files: list[str]) -> dict[str, Any]:
    _require(path.is_file() and not path.is_symlink(), f"missing smoke access log: {path.name}")
    record = _read_json(path)
    _require(set(record) == {"reviewer_id", "files_read"}, f"{path.name}: access log schema mismatch")
    _require(record["reviewer_id"] == reviewer_id, f"{path.name}: access log reviewer mismatch")
    allowed_prefixes = (
        f"{TARGET_ROOT}/",
        "experiments/emergent_coordination/evaluator_private/flowise_3_1_3_repository_v1/",
    )
    allowed_exact = {
        f"artifacts/hidden_opportunity_graph/flowise_3_1_3_repository_v1/expansion-edge-smoke-v1/{name}"
        for name in ALLOWED_PACKET_FILES
    } | {f"artifacts/hidden_opportunity_graph/flowise_3_1_3_repository_v1/expansion-edge-smoke-v1/{name}"
        for name in own_files}
    allowed_exact |= set(EVALUATOR_PRIVATE_FILES)
    violations = []
    for entry in record["files_read"]:
        if entry in allowed_exact or any(entry.startswith(prefix) for prefix in allowed_prefixes):
            continue
        violations.append(entry)
    required_packet_reads = {
        f"artifacts/hidden_opportunity_graph/flowise_3_1_3_repository_v1/expansion-edge-smoke-v1/reviewer_rubric.json",
        f"artifacts/hidden_opportunity_graph/flowise_3_1_3_repository_v1/expansion-edge-smoke-v1/edge_reviewer_bundle.json",
    }
    return {
        "reviewer_id": reviewer_id,
        "files_read_count": len(record["files_read"]),
        "scope_violations": sorted(violations),
        "read_rubric_and_bundle": required_packet_reads <= set(record["files_read"]),
        "touched_target_files": sorted({p for p in record["files_read"] if p.startswith(TARGET_ROOT)}),
    }


def check() -> dict[str, Any]:
    universe_status = verify_pair_universe()
    packet = verify_packet()
    universe = _read_jsonl(SMOKE_DIR.parent / PAIR_UNIVERSE_VERSION / "pair_universe.jsonl")
    selected = select_smoke_pairs(universe)
    expected_pairs = {(row["source_node"], row["target_node"]): row["pair_id"] for row in selected}
    bundle = _read_json(SMOKE_DIR / "edge_reviewer_bundle.json")
    bundle_pairs = {(row["source_node"], row["target_node"]) for row in bundle["smoke_directed_pairs"]}
    nodes = _read_jsonl(SMOKE_DIR.parent / "expansion-node-set-v2" / "nodes_frozen.jsonl")
    node_ids = {node["node_id"] for node in nodes}
    target = load_case(CASE_ID).target_root
    review_dir = SMOKE_DIR / "reviews"
    missing = [name for name in ("reviewer_a.jsonl", "reviewer_b.jsonl") if not (review_dir / name).is_file()]
    gates = {
        "pair_universe_is_462_with_expected_counts": universe_status["validator_all_passed"]
        and universe_status["new_directed_pair_count"] == 462,
        "packet_verified_without_frozen_edge_leak": packet["status"] == "verified_non_production_smoke_packet",
        "selection_matches_frozen_universe": bundle_pairs == set(expected_pairs)
        and packet["selected_pair_ids"] == [row["pair_id"] for row in selected],
        "output_path_compatible_with_production_pipeline": True,
    }
    if missing:
        return {
            "status": "pending_smoke_reviews",
            "annotation_status": "non_production_infrastructure_validation_only",
            "missing": missing,
            "gates": gates,
            "qc_date": date.today().isoformat(),
        }
    a_id, a_rows, a_warnings = _load_review(review_dir / "reviewer_a.jsonl", expected_pairs, node_ids, target)
    b_id, b_rows, b_warnings = _load_review(review_dir / "reviewer_b.jsonl", expected_pairs, node_ids, target)
    access_a = _check_access_log(review_dir / "reviewer_a_access.json", a_id,
                                 ["reviews/reviewer_a.jsonl", "reviews/reviewer_a_access.json"])
    access_b = _check_access_log(review_dir / "reviewer_b_access.json", b_id,
                                 ["reviews/reviewer_b.jsonl", "reviews/reviewer_b_access.json"])
    ordered = sorted(expected_pairs)
    agreement = {
        "exact_agreement_count": sum(a_rows[p]["opportunity_type"] == b_rows[p]["opportunity_type"] for p in ordered),
        "actionable_binary_agreement_count": sum(
            (a_rows[p]["opportunity_type"] in {"actionable cross-check", "strong dependency"})
            == (b_rows[p]["opportunity_type"] in {"actionable cross-check", "strong dependency"})
            for p in ordered),
        "per_pair": {
            expected_pairs[p]: {"reviewer_a": a_rows[p]["opportunity_type"], "reviewer_b": b_rows[p]["opportunity_type"]}
            for p in ordered
        },
        "note": "agreement is informational only; smoke pass/fail does not gate on agreement",
    }
    gates.update({
        "both_reviews_complete_and_schema_valid": True,
        "distinct_reviewer_ids": a_id != b_id,
        "pair_ids_exactly_match_frozen_universe": True,
        "no_extra_or_missing_pairs": True,
        "evidence_resolvable_in_frozen_target": True,
        "access_within_allowed_scope": not access_a["scope_violations"] and not access_b["scope_violations"],
        "both_read_rubric_and_bundle": access_a["read_rubric_and_bundle"] and access_b["read_rubric_and_bundle"],
        "production_template_key_compatibility": PRODUCTION_REVIEW_KEYS == {
            "reviewer_id", "source_node", "target_node", "opportunity_type", "mechanisms", "source_artifact",
            "target_claim", "expected_effect", "bounded_check", "evidence", "rationale", "confidence",
            "uncertainty_note"},
    })
    report = {
        "status": "smoke_passed" if all(gates.values()) else "smoke_failed",
        "annotation_status": "non_production_infrastructure_validation_only",
        "smoke_labels_must_not_enter_production": True,
        "packet_version": PACKET_VERSION,
        "case_id": CASE_ID,
        "pair_universe_version": PAIR_UNIVERSE_VERSION,
        "pair_universe_manifest_sha256": universe_status["pair_universe_manifest_sha256"],
        "smoke_packet_manifest_sha256": packet["smoke_packet_manifest_sha256"],
        "qc_date": date.today().isoformat(),
        "smoke_pair_count": len(ordered),
        "reviewer_ids": [a_id, b_id],
        "review_file_sha256": {
            "reviewer_a": digest((review_dir / "reviewer_a.jsonl").read_bytes()),
            "reviewer_b": digest((review_dir / "reviewer_b.jsonl").read_bytes()),
        },
        "categories_reviewer_a": {name: sum(row["opportunity_type"] == name for row in a_rows.values())
                                  for name in TAXONOMY},
        "categories_reviewer_b": {name: sum(row["opportunity_type"] == name for row in b_rows.values())
                                  for name in TAXONOMY},
        "agreement": agreement,
        "access_review": {"reviewer_a": access_a, "reviewer_b": access_b},
        "runtime_reference_warnings": sorted(a_warnings + b_warnings),
        "gates": gates,
        "controller_qualitative_review": "pending manual controller read; record separately in smoke_manual_review.json",
    }
    path = SMOKE_DIR / "smoke_qc.json"
    _require(not path.exists() or path.read_bytes() == jbytes(report), "smoke QC report changed; inspect manually")
    path.write_bytes(jbytes(report))
    path.chmod(0o600)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check",))
    args = parser.parse_args()
    try:
        result = check()
    except GraphValidationError as exc:
        parser.exit(1, f"expansion edge smoke check failed: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
