#!/usr/bin/env python3
"""QC independent split/merge boundary reviews for expansion candidates."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any

from experiments.emergent_coordination.harness.cases import load_case
from scripts.hidden_opportunity_graph import CASE_ID, GraphValidationError, _evidence, _read_json, _read_jsonl, _require
from scripts.prepare_hidden_graph_expansion_boundary_v5 import BOUNDARY_DIR, verify as verify_packet

KEYS = {
    "reviewer_id", "candidate_id", "boundary_decision", "merged_existing_node_ids", "merged_candidate_ids",
    "reviewed_existing_node_ids", "reviewed_candidate_ids",
    "security_question", "invariant", "code_scope", "evidence_refs", "rationale", "uncertainty_note",
}
DECISIONS = {"standalone", "merge_existing", "merge_candidate", "uncertain"}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_review(path: Path, candidates: dict[str, dict[str, Any]], existing_ids: set[str], *, complete: bool) -> tuple[str, dict[str, dict[str, Any]]]:
    _require(path.is_file() and not path.is_symlink(), f"missing boundary review: {path}")
    rows = _read_jsonl(path)
    if complete:
        _require(len(rows) == len(candidates), f"{path.name}: expected {len(candidates)} rows")
    target = load_case(CASE_ID).target_root
    mapped: dict[str, dict[str, Any]] = {}
    identities: set[str] = set()
    for index, row in enumerate(rows, 1):
        where = f"{path.name}:{index}"
        _require(set(row) == KEYS, f"{where}: schema mismatch")
        cid = row["candidate_id"]
        _require(isinstance(cid, str) and cid in candidates and cid not in mapped, f"{where}: unknown/duplicate candidate")
        rid = row["reviewer_id"]
        _require(isinstance(rid, str) and rid.strip(), f"{where}: empty reviewer_id")
        identities.add(rid)
        decision = row["boundary_decision"]
        _require(decision in DECISIONS, f"{where}: invalid boundary_decision")
        for key in ("security_question", "invariant", "rationale"):
            _require(isinstance(row[key], str) and row[key].strip(), f"{where}: missing {key}")
        scope = row["code_scope"]
        _require(isinstance(scope, list) and scope and all(isinstance(v, str) and v.strip() for v in scope), f"{where}: invalid code_scope")
        existing = row["merged_existing_node_ids"]
        merged = row["merged_candidate_ids"]
        reviewed_existing = row["reviewed_existing_node_ids"]
        reviewed_candidates = row["reviewed_candidate_ids"]
        _require(isinstance(reviewed_existing, list) and len(reviewed_existing) == len(existing_ids)
                 and set(reviewed_existing) == existing_ids, f"{where}: all existing nodes must be reviewed")
        _require(isinstance(reviewed_candidates, list) and len(reviewed_candidates) == len(candidates) - 1
                 and set(reviewed_candidates) == set(candidates) - {cid},
                 f"{where}: all other candidates must be reviewed")
        _require(isinstance(existing, list) and all(v in existing_ids for v in existing), f"{where}: invalid merged_existing_node_ids")
        _require(isinstance(merged, list) and all(isinstance(v, str) and v in candidates and v != cid for v in merged), f"{where}: invalid merged_candidate_ids")
        _require(len(existing) == len(set(existing)) and len(merged) == len(set(merged)), f"{where}: duplicate merge IDs")
        if decision == "standalone":
            _require(not existing and not merged, f"{where}: standalone cannot list merges")
        if decision == "merge_existing":
            _require(bool(existing) and not merged, f"{where}: merge_existing needs existing IDs only")
        if decision == "merge_candidate":
            _require(bool(merged) and not existing, f"{where}: merge_candidate needs candidate IDs only")
        note = row["uncertainty_note"]
        _require(note is None or (isinstance(note, str) and note.strip()), f"{where}: invalid uncertainty_note")
        if decision == "uncertain":
            _require(bool(note), f"{where}: uncertain boundary needs uncertainty_note")
        refs = row["evidence_refs"]
        _require(isinstance(refs, list) and refs, f"{where}: evidence_refs required")
        for ri, ref in enumerate(refs):
            _evidence(ref, f"{where}.evidence_refs[{ri}]", target)
        anchor = candidates[cid]["anchor"]
        _require(any(all(ref.get(k) == anchor[k] for k in ("path", "line", "excerpt_sha256")) for ref in refs), f"{where}: candidate anchor not cited")
        mapped[cid] = row
    _require(len(identities) == 1, f"{path.name}: mixed reviewer IDs")
    if complete:
        _require(set(mapped) == set(candidates), f"{path.name}: incomplete candidate set")
    return next(iter(identities)), mapped


def pair_decisions(rows: dict[str, dict[str, Any]], candidates: list[str], existing_ids: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for cid in candidates:
        row = rows[cid]
        for fid in existing_ids:
            pair = f"{fid}|{cid}"
            result[pair] = ("uncertain" if row["boundary_decision"] == "uncertain" else
                            "merge" if fid in row["merged_existing_node_ids"] else "split")
    for i, left in enumerate(candidates):
        for right in candidates[i + 1:]:
            left_row, right_row = rows[left], rows[right]
            left_merge = right in left_row["merged_candidate_ids"]
            right_merge = left in right_row["merged_candidate_ids"]
            _require(left_merge == right_merge, f"candidate pair {left}|{right}: asymmetric merge")
            result[f"{left}|{right}"] = (
                "uncertain" if "uncertain" in (left_row["boundary_decision"], right_row["boundary_decision"])
                else "merge" if left_merge else "split"
            )
    _require(len(result) == 231, f"expected 231 reviewed boundary pairs, got {len(result)}")
    return result


def assess(
    review_a: Path = Path("/tmp/expansion-v5-boundary-review-a.jsonl"),
    review_b: Path = Path("/tmp/expansion-v5-boundary-review-b.jsonl"),
    adjudicator: Path = Path("/tmp/expansion-v5-boundary-adjudicator.jsonl"),
) -> dict[str, Any]:
    packet = verify_packet()
    bundle = _read_json(BOUNDARY_DIR / "reviewer_bundle.json")
    candidates = {row["candidate_id"]: row for row in bundle["candidates"]}
    existing_ids = {row["node_id"] for row in bundle["existing_node_boundaries"]}
    missing = [str(p) for p in (review_a, review_b) if not p.is_file()]
    if missing:
        return {**packet, "status": "pending_independent_boundary_reviews", "missing": missing}
    rid_a, a = load_review(review_a, candidates, existing_ids, complete=True)
    rid_b, b = load_review(review_b, candidates, existing_ids, complete=True)
    _require(rid_a != rid_b, "boundary reviewers must be distinct")
    ordered = sorted(candidates)
    pair_a = pair_decisions(a, ordered, sorted(existing_ids))
    pair_b = pair_decisions(b, ordered, sorted(existing_ids))
    disputed_pairs = [pair for pair in pair_a if pair_a[pair] != pair_b[pair]
                      or "uncertain" in (pair_a[pair], pair_b[pair])]
    agreed_count = sum(pair_a[pair] == pair_b[pair] for pair in pair_a)
    disputed = set()
    for pair in disputed_pairs:
        disputed.update(part for part in pair.split("|") if part.startswith("C"))
    disputed.update(cid for cid in ordered if a[cid]["uncertainty_note"] or b[cid]["uncertainty_note"])
    disputed = sorted(disputed)
    if disputed and not adjudicator.is_file():
        return {**packet, "status": "pending_third_boundary_adjudication", "reviewer_ids": [rid_a, rid_b],
                "pair_agreement_count": agreed_count, "pair_agreement_rate": round(agreed_count / 231, 6),
                "disputed_pair_count": len(disputed_pairs), "disputed_pairs": disputed_pairs,
                "needs_adjudication": disputed}
    third_id = None
    third: dict[str, dict[str, Any]] = {}
    if disputed:
        third_id, third = load_review(adjudicator, candidates, existing_ids, complete=False)
        _require(third_id not in {rid_a, rid_b}, "boundary adjudicator must be distinct")
        _require(set(third) == set(disputed), "boundary adjudicator must cover exactly disputed candidates")
    elif adjudicator.is_file() and _read_jsonl(adjudicator):
        raise GraphValidationError("unexpected boundary adjudicator file")
    final = {cid: third.get(cid, a[cid]) for cid in ordered}
    final_pairs = pair_decisions(final, ordered, sorted(existing_ids))
    for pair, decision in final_pairs.items():
        if pair not in disputed_pairs:
            _require(decision == pair_a[pair] == pair_b[pair],
                     f"adjudicator changed an agreed pair: {pair}")
        if decision != "merge":
            continue
        left, right = pair.split("|")
        if left.startswith("F"):
            node = next(item for item in bundle["existing_node_boundaries"] if item["node_id"] == left)
            _require(any(ref["path"] in node["code_scope"] for ref in final[right]["evidence_refs"]),
                     f"merged pair {pair}: missing existing-node source evidence")
        else:
            left_anchor = candidates[left]["anchor"]
            right_anchor = candidates[right]["anchor"]
            refs = final[left]["evidence_refs"] + final[right]["evidence_refs"]
            for anchor in (left_anchor, right_anchor):
                _require(any(all(ref.get(k) == anchor[k] for k in ("path", "line", "excerpt_sha256")) for ref in refs),
                         f"merged pair {pair}: missing two-sided candidate anchors")
    unresolved = [cid for cid in ordered if final[cid]["boundary_decision"] == "uncertain"]
    _require(not unresolved or any(value == "uncertain" for value in final_pairs.values()),
             "unresolved candidate must leave uncertain pairs")
    return {
        "status": "unresolved_boundary" if unresolved else "ready_to_freeze_expansion_nodes",
        "case_id": CASE_ID,
        "qc_date": date.today().isoformat(),
        "packet_manifest_sha256": packet["packet_manifest_sha256"],
        "reviewer_ids": [rid_a, rid_b],
        "adjudicator_id": third_id,
        "review_file_sha256": {"reviewer_a": digest(review_a), "reviewer_b": digest(review_b)},
        "adjudication_file_sha256": digest(adjudicator) if disputed else None,
        "candidate_count": len(ordered),
        "pair_denominator": 231,
        "pair_agreement_count": agreed_count,
        "pair_agreement_rate": round(agreed_count / 231, 6),
        "disputed_pair_count": len(disputed_pairs),
        "disputed_pairs": disputed_pairs,
        "disputed_candidates": disputed,
        "unresolved_candidate_ids": unresolved,
        "final_pair_counts": {value: sum(v == value for v in final_pairs.values()) for value in ("split", "merge", "uncertain")},
        "final_decisions": {cid: {"boundary_decision": final[cid]["boundary_decision"], "merged_existing_node_ids": final[cid]["merged_existing_node_ids"], "merged_candidate_ids": final[cid]["merged_candidate_ids"]} for cid in ordered},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("check",))
    parser.add_argument("--review-a", type=Path, default=Path("/tmp/expansion-v5-boundary-review-a.jsonl"))
    parser.add_argument("--review-b", type=Path, default=Path("/tmp/expansion-v5-boundary-review-b.jsonl"))
    parser.add_argument("--adjudicator", type=Path, default=Path("/tmp/expansion-v5-boundary-adjudicator.jsonl"))
    args = parser.parse_args()
    try:
        print(json.dumps(assess(args.review_a, args.review_b, args.adjudicator), ensure_ascii=False, indent=2))
        return 0
    except GraphValidationError as exc:
        parser.exit(1, f"expansion boundary QC failed: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
