"""核验 Pilot B 候选资格的独立盲标与分歧裁决。"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any

from experiments.emergent_coordination.harness.cases import load_case
from scripts.hidden_opportunity_graph import CASE_ID, GraphValidationError, _evidence, _read_json, _read_jsonl, _require
from scripts.prepare_hidden_graph_pilot_b_candidates import PREP_DIR, STRATA, verify as verify_packet
from scripts.prepare_hidden_graph_pilot_b_candidates_round2 import ROUND2_DIR, verify as verify_round2_packet


REVIEW_KEYS = {
    "reviewer_id", "candidate_id", "admission_decision", "security_question", "invariant",
    "independent_chain", "pilot_a_boundary", "evidence_refs", "rationale", "uncertainty_note",
}
DECISIONS = {"admit", "exclude", "uncertain"}


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _load_review(path: Path, candidates: dict[str, dict[str, Any]], *, complete: bool) -> tuple[str, dict[str, dict[str, Any]]]:
    _require(path.is_file() and not path.is_symlink(), f"missing or unsafe Pilot B review: {path.name}")
    records = _read_jsonl(path)
    _require(not complete or len(records) == len(candidates), f"{path.name}: incomplete candidate review")
    target = load_case(CASE_ID).target_root
    mapped = {}
    ids = set()
    for index, row in enumerate(records, 1):
        where = f"{path.name}:{index}"
        _require(set(row) == REVIEW_KEYS, f"{where}: review schema mismatch")
        identifier = row["candidate_id"]
        _require(isinstance(identifier, str) and identifier in candidates and identifier not in mapped,
                 f"{where}: unknown or duplicate candidate")
        identity = row["reviewer_id"]
        _require(isinstance(identity, str) and identity.strip(), f"{where}: empty reviewer identity")
        _require(isinstance(row["admission_decision"], str) and row["admission_decision"] in DECISIONS,
                 f"{where}: invalid admission decision")
        _require(isinstance(row["rationale"], str) and row["rationale"].strip(), f"{where}: missing rationale")
        for key in ("security_question", "invariant", "independent_chain", "pilot_a_boundary"):
            _require(isinstance(row[key], str), f"{where}: {key} must be text")
            if row["admission_decision"] == "admit":
                _require(row[key].strip(), f"{where}: admitted node lacks {key}")
        note = row["uncertainty_note"]
        _require(note is None or (isinstance(note, str) and note.strip()), f"{where}: invalid uncertainty note")
        if row["admission_decision"] == "uncertain":
            _require(bool(note), f"{where}: uncertain decision needs missing fact")
        refs = row["evidence_refs"]
        _require(isinstance(refs, list) and len(refs) >= (2 if row["admission_decision"] == "admit" else 1),
                 f"{where}: missing target evidence")
        for ref_index, ref in enumerate(refs):
            _evidence(ref, f"{where}.evidence_refs[{ref_index}]", target)
        anchor = candidates[identifier]["anchor"]
        _require(any(all(ref.get(key) == anchor[key] for key in ("path", "line", "excerpt_sha256")) for ref in refs),
                 f"{where}: candidate anchor not cited")
        if row["admission_decision"] == "admit":
            _require(len({(ref["path"], ref["line"]) for ref in refs}) >= 2,
                     f"{where}: admitted node needs a source-chain anchor beyond the GT location")
        ids.add(identity)
        mapped[identifier] = row
    _require(len(ids) == 1 and (not complete or set(mapped) == set(candidates)),
             f"{path.name}: inconsistent reviewer or candidate coverage")
    return ids.pop(), mapped


def assess(directory: Path = PREP_DIR) -> tuple[dict[str, Any], dict[str, Any]]:
    _require(directory in {PREP_DIR, ROUND2_DIR}, "unknown Pilot B candidate packet version")
    packet = verify_round2_packet() if directory == ROUND2_DIR else verify_packet()
    bundle = _read_json(directory / "reviewer_bundle.json")
    candidates = {item["candidate_id"]: item for item in bundle["candidates"]}
    _require(len(candidates) == 21 and {item["stratum"] for item in candidates.values()} == set(STRATA),
             "Pilot B candidate universe changed")
    review_dir = directory / "reviews"
    a_path, b_path = review_dir / "reviewer_a.jsonl", review_dir / "reviewer_b.jsonl"
    missing = [path.name for path in (a_path, b_path) if not path.is_file()]
    if missing:
        return {**packet, "status": "pending_independent_node_reviews", "missing": missing}, {}
    a_id, a = _load_review(a_path, candidates, complete=True)
    b_id, b = _load_review(b_path, candidates, complete=True)
    _require(a_id != b_id, "Pilot B node reviewers must be distinct")
    ordered = [item["candidate_id"] for item in bundle["candidates"]]
    agreement = sum(a[item]["admission_decision"] == b[item]["admission_decision"] for item in ordered)
    needed = {item for item in ordered if a[item]["admission_decision"] != b[item]["admission_decision"]
              or a[item]["admission_decision"] == "uncertain" or a[item]["uncertainty_note"] or b[item]["uncertainty_note"]}
    third_path = review_dir / "adjudicator.jsonl"
    if needed and not third_path.is_file():
        return {
            **packet, "status": "pending_third_node_adjudication", "reviewer_ids": [a_id, b_id],
            "agreement_count": agreement, "needs_adjudication": sorted(needed),
        }, {}
    if needed:
        third_id, third = _load_review(third_path, candidates, complete=False)
        _require(third_id not in {a_id, b_id} and set(third) == needed,
                 "third node adjudicator must cover exactly disputed or uncertain candidates")
    else:
        _require(not third_path.exists() or not _read_jsonl(third_path), "unexpected third node review")
        third_id, third = None, {}
    final = {item: third.get(item, a[item]) for item in ordered}
    unresolved = [item for item in ordered if final[item]["admission_decision"] == "uncertain"]
    admitted = [item for item in ordered if final[item]["admission_decision"] == "admit"]
    status = ("qc_failed_reblind_required" if agreement < 19 else
              "unresolved_node_eligibility" if unresolved else "ready_for_boundary_and_selection_qc")
    report = {
        "status": status,
        "case_id": CASE_ID,
        "qc_date": date.today().isoformat(),
        "packet_manifest_sha256": packet["packet_manifest_sha256"],
        "reviewer_bundle_sha256": packet["reviewer_bundle_sha256"],
        "reviewer_ids": [a_id, b_id],
        "adjudicator_id": third_id,
        "review_file_sha256": {"reviewer_a": _digest(a_path), "reviewer_b": _digest(b_path)},
        "adjudication_file_sha256": _digest(third_path) if third_path.is_file() else None,
        "candidate_count": len(ordered),
        "agreement_count": agreement,
        "agreement_rate": round(agreement / len(ordered), 6),
        "disputed_or_uncertain": sorted(needed),
        "admitted_candidate_ids": admitted,
        "unresolved_candidate_ids": unresolved,
        "admitted_by_stratum": {stratum: [item for item in admitted if candidates[item]["stratum"] == stratum]
                                for stratum in STRATA},
    }
    return report, {"candidates": candidates, "final": final}


def check(directory: Path = PREP_DIR) -> dict[str, Any]:
    report, _ = assess(directory)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check",))
    parser.add_argument("--round", type=int, choices=(1, 2), default=2)
    args = parser.parse_args()
    try:
        result = check(ROUND2_DIR if args.round == 2 else PREP_DIR)
    except GraphValidationError as exc:
        parser.exit(1, f"Pilot B node eligibility QC failed: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
