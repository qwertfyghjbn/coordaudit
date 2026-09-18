"""Deterministic, bounded evaluator for the frozen repository-pilot-v0 oracle."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from experiments.emergent_coordination.harness.paths import normalize_target_relative_path


def load_ground_truth(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _file_match(value: str, expected: str) -> bool:
    return _norm(normalize_target_relative_path(value)) == _norm(normalize_target_relative_path(expected))


def _anchor_match(reported: dict[str, Any], expected: dict[str, Any]) -> bool:
    """Match the hidden canonical file/function/snippet triple without aliases."""
    return (
        _file_match(reported.get("file", ""), expected.get("file", ""))
        and _norm(reported.get("function")) == _norm(expected.get("function"))
        and _norm(expected.get("code_snippet")) in _norm(reported.get("anchor"))
    )


def _fingerprint(finding: dict[str, Any]) -> str:
    def anchor(part: dict[str, Any]) -> str:
        return "|".join(_norm(part.get(key)) for key in ("file", "function", "anchor"))

    return "|".join((_norm(finding.get("category")), anchor(finding.get("source") or {}), anchor(finding.get("sink") or {})))


def match_positive(finding: dict[str, Any], spec: dict[str, Any]) -> tuple[bool, str]:
    if finding.get("category") != spec.get("category"):
        return False, "canonical_category_mismatch"
    required = spec.get("required_semantics") or {}
    if not _anchor_match(finding.get("source") or {}, required.get("source") or {}):
        return False, "canonical_source_anchor_mismatch"
    if not _anchor_match(finding.get("sink") or {}, required.get("sink") or {}):
        return False, "canonical_sink_anchor_mismatch"
    return True, "canonical_category_source_sink_match"


def match_near_miss(finding: dict[str, Any], spec: dict[str, Any]) -> tuple[bool, str]:
    if finding.get("category") != spec.get("category"):
        return False, "canonical_category_mismatch"
    rules = spec.get("match") or {}
    forbidden = rules.get("exclude_if_files") or []
    referenced_files = {finding.get("source", {}).get("file", ""), finding.get("sink", {}).get("file", "")}
    if any(_file_match(candidate, excluded) for candidate in referenced_files for excluded in forbidden):
        return False, "positive_target_file_excluded"
    required_files = rules.get("required_files_any") or []
    if any(_file_match(candidate, required) for candidate in referenced_files for required in required_files):
        return True, "known_near_miss_anchor_match"
    return False, "near_miss_anchor_mismatch"


def evaluate_findings(
    findings: list[dict[str, Any]], ground_truth: dict[str, Any], *, invalid_submissions: int = 0
) -> dict[str, Any]:
    """Return public aggregate metrics and evaluator-private verification details.

    The closed-world precision lower bound treats unmatched reports as false
    positives; the labeled-only upper bound treats them as unresolved. Neither
    is presented as an assumption-free precision value.
    """
    positives = ground_truth.get("findings") or []
    near_misses = ground_truth.get("near_misses") or []
    matched_gt: dict[str, int] = {}
    duplicate_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen_fingerprints: dict[str, int] = {}
    outcomes: list[dict[str, Any]] = []
    near_miss_fp = 0
    unmatched = 0
    duplicate_count = 0
    agent_attempted = 0
    agent_successful = 0

    for index, finding in enumerate(findings):
        reproduction = finding.get("reproduction") or {}
        agent_attempted += int(reproduction.get("attempted") is True)
        agent_successful += int(reproduction.get("successful") is True)
        fingerprint = _fingerprint(finding)
        provenance = {
            "index": index,
            "submitted_by": finding.get("submitted_by"),
            "evidence_refs": list(finding.get("evidence_refs") or []),
        }
        duplicate_groups[fingerprint].append(provenance)
        if fingerprint in seen_fingerprints:
            duplicate_count += 1
            outcomes.append({"index": index, "disposition": "duplicate", "duplicate_of": seen_fingerprints[fingerprint]})
            continue
        seen_fingerprints[fingerprint] = index

        assigned: str | None = None
        explanation = "unmatched_review"
        disposition = "unmatched_review"
        for spec in positives:
            ok, why = match_positive(finding, spec)
            if ok:
                assigned = str(spec["id"])
                explanation = why
                disposition = "positive"
                break
        if assigned is None:
            for spec in near_misses:
                ok, why = match_near_miss(finding, spec)
                if ok:
                    assigned = str(spec["id"])
                    explanation = why
                    disposition = "known_near_miss"
                    break

        if disposition == "positive":
            if assigned in matched_gt:
                duplicate_count += 1
                outcomes.append({"index": index, "disposition": "duplicate", "duplicate_of": matched_gt[assigned]})
            else:
                matched_gt[assigned] = index
                outcomes.append({"index": index, "disposition": "positive"})
        elif disposition == "known_near_miss":
            near_miss_fp += 1
            outcomes.append({"index": index, "disposition": "known_near_miss"})
        else:
            unmatched += 1
            outcomes.append({"index": index, "disposition": "unmatched_review"})

    tp = len(matched_gt)
    fn_ids = [str(spec["id"]) for spec in positives if str(spec["id"]) not in matched_gt]
    fn = len(fn_ids)
    recall = tp / (tp + fn) if tp + fn else 0.0
    lower_denominator = tp + near_miss_fp + unmatched
    upper_denominator = tp + near_miss_fp
    public = {
        "positive_recall": {"true_positives": tp, "false_negatives": fn, "value": recall},
        "known_near_miss_false_positives": near_miss_fp,
        "unmatched_review": {"count": unmatched, "disposition": "condition_blind_manual_review_only"},
        "invalid_submissions": invalid_submissions,
        "duplicates": {"count": duplicate_count},
        "precision_bounds": {
            "closed_world_lower_bound": tp / lower_denominator if lower_denominator else 0.0,
            "labeled_only_upper_bound": tp / upper_denominator if upper_denominator else 0.0,
        },
        "agent_reproduction_claims": {"attempted": agent_attempted, "successful": agent_successful},
        "evaluator_verified_findings": tp,
        "semantic_judge_used": False,
    }
    private = {
        "matched_ground_truth": matched_gt,
        "missing_ground_truth": fn_ids,
        "per_finding": [
            {
                "index": index,
                "assigned": next(
                    (
                        spec["id"]
                        for spec in positives
                        if match_positive(finding, spec)[0]
                    ),
                    next((spec["id"] for spec in near_misses if match_near_miss(finding, spec)[0]), None),
                ),
                "outcome": outcomes[index] if index < len(outcomes) else None,
                "fingerprint": _fingerprint(finding),
                "submitted_by": finding.get("submitted_by"),
                "evidence_refs": list(finding.get("evidence_refs") or []),
                "agent_reproduction": finding.get("reproduction"),
            }
            for index, finding in enumerate(findings)
        ],
        "duplicate_provenance": {fingerprint: entries for fingerprint, entries in duplicate_groups.items() if len(entries) > 1},
        "oracle": {"repository_id": ground_truth.get("repository_id"), "version": ground_truth.get("version")},
    }
    return {"public": public, "private": private}
