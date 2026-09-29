#!/usr/bin/env python3
"""QC two independent structural-expansion node reviews.

This checker consumes the ungraded expansion-prep-v3 packet and review files
written outside the packet.  It never creates or mutates a graph version.
Every candidate disagreement or uncertainty must be covered by a distinct
third adjudicator before the result can be used for a new graph draft.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import date
from pathlib import Path
from typing import Any

from experiments.emergent_coordination.harness.cases import load_case
from scripts.hidden_opportunity_graph import CASE_ID, GraphValidationError, _evidence, _read_json, _read_jsonl, _require
from scripts.prepare_hidden_graph_expansion_blind import BLIND_DIR, verify as verify_packet


REVIEW_KEYS = {
    "reviewer_id", "candidate_id", "admission_decision", "security_question", "invariant",
    "independent_chain", "pilot_a_boundary", "evidence_refs", "rationale", "uncertainty_note",
}
DECISIONS = {"admit", "exclude", "uncertain"}


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_review(path: Path, candidates: dict[str, dict[str, Any]], *, complete: bool) -> tuple[str, dict[str, dict[str, Any]]]:
    _require(path.is_file() and not path.is_symlink(), f"missing or unsafe expansion review: {path}")
    rows = _read_jsonl(path)
    if complete:
        _require(len(rows) == len(candidates), f"{path.name}: expected {len(candidates)} rows")
    target = load_case(CASE_ID).target_root
    mapped: dict[str, dict[str, Any]] = {}
    reviewer_ids: set[str] = set()
    for index, row in enumerate(rows, 1):
        where = f"{path.name}:{index}"
        _require(set(row) == REVIEW_KEYS, f"{where}: review schema mismatch")
        candidate_id = row["candidate_id"]
        _require(isinstance(candidate_id, str) and candidate_id in candidates and candidate_id not in mapped,
                 f"{where}: unknown or duplicate candidate")
        reviewer_id = row["reviewer_id"]
        _require(isinstance(reviewer_id, str) and reviewer_id.strip(), f"{where}: empty reviewer identity")
        reviewer_ids.add(reviewer_id)
        decision = row["admission_decision"]
        _require(isinstance(decision, str) and decision in DECISIONS, f"{where}: invalid decision")
        _require(isinstance(row["rationale"], str) and row["rationale"].strip(), f"{where}: missing rationale")
        for key in ("security_question", "invariant", "independent_chain", "pilot_a_boundary"):
            _require(isinstance(row[key], str), f"{where}: {key} must be text")
            if decision == "admit":
                _require(row[key].strip(), f"{where}: admitted candidate lacks {key}")
        note = row["uncertainty_note"]
        _require(note is None or (isinstance(note, str) and note.strip()), f"{where}: invalid uncertainty_note")
        if decision == "uncertain":
            _require(bool(note), f"{where}: uncertain decision needs uncertainty_note")
        refs = row["evidence_refs"]
        _require(isinstance(refs, list) and len(refs) >= (2 if decision == "admit" else 1),
                 f"{where}: insufficient evidence_refs")
        for ref_index, ref in enumerate(refs):
            _evidence(ref, f"{where}.evidence_refs[{ref_index}]", target)
        anchor = candidates[candidate_id]["anchor"]
        _require(any(all(ref.get(key) == anchor[key] for key in ("path", "line", "excerpt_sha256")) for ref in refs),
                 f"{where}: candidate anchor not cited")
        if decision == "admit":
            _require(len({(ref["path"], ref["line"]) for ref in refs}) >= 2,
                     f"{where}: admitted candidate needs a second source location")
        mapped[candidate_id] = row
    _require(len(reviewer_ids) == 1, f"{path.name}: mixed reviewer identities")
    if complete:
        _require(set(mapped) == set(candidates), f"{path.name}: incomplete candidate set")
    return next(iter(reviewer_ids)), mapped


def assess(
    review_a: Path = Path("/tmp/expansion-v4-review-a.jsonl"),
    review_b: Path = Path("/tmp/expansion-v4-review-b.jsonl"),
    adjudicator: Path = Path("/tmp/expansion-v4-adjudicator.jsonl"),
) -> dict[str, Any]:
    packet = verify_packet()
    bundle = _read_json(BLIND_DIR / "reviewer_bundle.json")
    candidates = {row["candidate_id"]: row for row in bundle["candidates"]}
    _require(len(candidates) == 11, "expansion packet candidate universe changed")
    missing = [str(path) for path in (review_a, review_b) if not path.is_file()]
    if missing:
        return {**packet, "status": "pending_independent_node_reviews", "missing": missing}
    reviewer_a, rows_a = _load_review(review_a, candidates, complete=True)
    reviewer_b, rows_b = _load_review(review_b, candidates, complete=True)
    _require(reviewer_a != reviewer_b, "independent expansion reviewers must be distinct")
    ordered = [row["candidate_id"] for row in bundle["candidates"]]
    agreement = sum(rows_a[c]["admission_decision"] == rows_b[c]["admission_decision"] for c in ordered)
    disputed = [
        c for c in ordered
        if rows_a[c]["admission_decision"] != rows_b[c]["admission_decision"]
        or rows_a[c]["admission_decision"] == "uncertain"
        or rows_b[c]["admission_decision"] == "uncertain"
        or rows_a[c]["uncertainty_note"] or rows_b[c]["uncertainty_note"]
    ]
    if disputed and not adjudicator.is_file():
        return {
            **packet, "status": "pending_third_node_adjudication", "reviewer_ids": [reviewer_a, reviewer_b],
            "agreement_count": agreement, "agreement_rate": round(agreement / len(ordered), 6),
            "needs_adjudication": disputed,
        }
    third_id = None
    rows_third: dict[str, dict[str, Any]] = {}
    if disputed:
        third_id, rows_third = _load_review(adjudicator, candidates, complete=False)
        _require(third_id not in {reviewer_a, reviewer_b}, "third adjudicator must be distinct")
        _require(set(rows_third) == set(disputed), "third adjudicator must cover exactly disputed candidates")
    elif adjudicator.is_file() and _read_jsonl(adjudicator):
        raise GraphValidationError("unexpected adjudicator file with no disputed candidates")
    final = {candidate: rows_third.get(candidate, rows_a[candidate]) for candidate in ordered}
    unresolved = [candidate for candidate in ordered if final[candidate]["admission_decision"] == "uncertain"]
    admitted = [candidate for candidate in ordered if final[candidate]["admission_decision"] == "admit"]
    agreement_reference_count = math.ceil(0.9 * len(ordered))
    # Neither the 2026-09-23 plan §8 nor the frozen schema pre-registers a
    # qualification agreement threshold for this 11-candidate expansion.
    # The 90% figure is an explicitly non-gating comparison to earlier pilots.
    # Qualification requires complete independent records, adjudication of
    # disagreements/uncertainty, and zero unresolved final decisions.
    status = "unresolved_node_eligibility" if unresolved else "ready_for_boundary_and_selection_qc"
    return {
        "status": status,
        "case_id": CASE_ID,
        "qc_date": date.today().isoformat(),
        "packet_manifest_sha256": packet["packet_manifest_sha256"],
        "reviewer_ids": [reviewer_a, reviewer_b],
        "adjudicator_id": third_id,
        "review_file_sha256": {"reviewer_a": _digest(review_a), "reviewer_b": _digest(review_b)},
        "adjudication_file_sha256": _digest(adjudicator) if disputed else None,
        "candidate_count": len(ordered),
        "agreement_reference_count_non_preregistered": agreement_reference_count,
        "agreement_count": agreement,
        "agreement_rate": round(agreement / len(ordered), 6),
        "agreement_reference_status": "met" if agreement >= agreement_reference_count else "below_non_gating_reference",
        "disputed_or_uncertain": disputed,
        "admitted_candidate_ids": admitted,
        "unresolved_candidate_ids": unresolved,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check",))
    parser.add_argument("--review-a", type=Path, default=Path("/tmp/expansion-v4-review-a.jsonl"))
    parser.add_argument("--review-b", type=Path, default=Path("/tmp/expansion-v4-review-b.jsonl"))
    parser.add_argument("--adjudicator", type=Path, default=Path("/tmp/expansion-v4-adjudicator.jsonl"))
    args = parser.parse_args()
    try:
        print(json.dumps(assess(args.review_a, args.review_b, args.adjudicator), ensure_ascii=False, indent=2))
        return 0
    except GraphValidationError as exc:
        parser.exit(1, f"expansion node QC failed: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
