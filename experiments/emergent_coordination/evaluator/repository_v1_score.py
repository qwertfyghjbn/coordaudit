"""Deterministic evaluator for the versioned repository-v1 finding contract."""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from experiments.emergent_coordination.harness.paths import normalize_target_relative_path


def load_ground_truth(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != "repository-v1-ground-truth":
        raise ValueError("not a repository-v1 ground-truth file")
    return data


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _path(value: Any) -> str:
    return _norm(normalize_target_relative_path(str(value or "")))


def _anchor_match(reported: dict[str, Any], expected: dict[str, Any]) -> bool:
    return (
        _path(reported.get("file")) == _path(expected.get("file"))
        and _norm(reported.get("function")) == _norm(expected.get("function"))
        and _norm(expected.get("excerpt")) in _norm(reported.get("anchor"))
    )


def _all_reported_anchors(finding: dict[str, Any]) -> list[dict[str, Any]]:
    anchors = [finding.get("source") or {}, finding.get("sink") or {}, (finding.get("guard") or {}).get("anchor") or {}]
    anchors.extend(finding.get("variant_coverage") or [])
    return anchors


def _contains_any(text: str, terms: list[str]) -> bool:
    normalized = _norm(text)
    return any(_norm(term) in normalized for term in terms)


def match_positive(finding: dict[str, Any], spec: dict[str, Any]) -> tuple[bool, str]:
    if finding.get("category") not in spec.get("categories", []):
        return False, "category_mismatch"
    if not any(_anchor_match(anchor, expected) for anchor in _all_reported_anchors(finding) for expected in spec["anchors"]):
        return False, "root_anchor_mismatch"
    if finding.get("guard", {}).get("kind") not in spec["guard_kinds"]:
        return False, "guard_kind_mismatch"
    if not _contains_any(str(finding.get("affected_object", "")), spec["affected_object_terms"]):
        return False, "affected_object_mismatch"
    evidence_text = " ".join((str(finding.get("trust_boundary", "")), str(finding.get("reasoning_summary", ""))))
    if not _contains_any(evidence_text, spec["reasoning_terms"]):
        return False, "reasoning_semantics_mismatch"
    return True, "bounded_category_anchor_guard_object_reasoning_match"


def match_near_miss(finding: dict[str, Any], spec: dict[str, Any]) -> tuple[bool, str]:
    """A definite FP requires every reported anchor to stay in one proven safe path."""
    if finding.get("category") not in spec.get("categories", []):
        return False, "near_miss_category_mismatch"
    anchors = _all_reported_anchors(finding)
    allowed = spec.get("allowed_anchors") or [spec["anchor"]]
    if not anchors or not all(any(_anchor_match(anchor, expected) for expected in allowed) for anchor in anchors):
        return False, "near_miss_outside_proven_path"
    if not any(_anchor_match(anchor, spec["anchor"]) for anchor in anchors):
        return False, "near_miss_anchor_mismatch"
    claim = _norm(" ".join(str(finding.get(key, "")) for key in ("title", "affected_object", "trust_boundary", "reasoning_summary")))
    if not _contains_any(claim, spec.get("claim_terms") or []):
        return False, "near_miss_claim_mismatch"
    if _contains_any(claim, spec.get("exclude_claim_terms") or []):
        return False, "near_miss_claim_outside_proof"
    return True, "known_safe_sibling_complete_path_match"


def _fingerprint(finding: dict[str, Any]) -> str:
    relevant = {key: finding.get(key) for key in ("category", "source", "sink", "guard", "affected_object")}
    return hashlib.sha256(json.dumps(relevant, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def evaluate_findings(findings: list[dict[str, Any]], ground_truth: dict[str, Any], *, invalid_submissions: int = 0) -> dict[str, Any]:
    specs = ground_truth.get("roots") or []
    matched: dict[str, int] = {}
    outcomes: list[dict[str, Any]] = []
    duplicates = 0
    near_miss_fp = 0
    unmatched = 0
    seen: dict[str, int] = {}
    coverage: dict[str, set[str]] = defaultdict(set)
    for index, finding in enumerate(findings):
        fingerprint = _fingerprint(finding)
        if fingerprint in seen:
            duplicates += 1
            outcomes.append({"index": index, "disposition": "duplicate", "duplicate_of": seen[fingerprint]})
            continue
        seen[fingerprint] = index
        candidates = [(spec, match_positive(finding, spec)) for spec in specs]
        accepted = next(((spec, why) for spec, (ok, why) in candidates if ok), None)
        if accepted is None:
            near = next(
                ((spec, why) for spec, (ok, why) in ((spec, match_near_miss(finding, spec)) for spec in ground_truth.get("near_misses") or []) if ok),
                None,
            )
            if near is not None:
                near_miss_fp += 1
                outcomes.append({"index": index, "disposition": "known_near_miss", "reason": near[1]})
                continue
            unmatched += 1
            outcomes.append({"index": index, "disposition": "unmatched_review"})
            continue
        spec, why = accepted
        root_id = spec["id"]
        for anchor in finding.get("variant_coverage") or []:
            for variant in spec.get("variants", []):
                if _anchor_match(anchor, variant["anchor"]):
                    coverage[root_id].add(variant["id"])
        if root_id in matched:
            duplicates += 1
            outcomes.append({"index": index, "disposition": "duplicate_root", "duplicate_of": matched[root_id]})
        else:
            matched[root_id] = index
            outcomes.append({"index": index, "disposition": "positive", "reason": why})
    missing = [spec["id"] for spec in specs if spec["id"] not in matched]
    tp, fn = len(matched), len(missing)
    public = {
        "positive_recall": {"true_positives": tp, "false_negatives": fn, "value": tp / (tp + fn) if tp + fn else 0.0},
        "unmatched_review": {"count": unmatched, "disposition": "condition_blind_manual_review_only"},
        "known_near_miss_false_positives": near_miss_fp,
        "invalid_submissions": invalid_submissions,
        "duplicates": {"count": duplicates},
        "variant_coverage": {"credited_variants": sum(len(value) for value in coverage.values()), "cap_per_root": 5},
        "semantic_judge_used": False,
    }
    private = {"matched_ground_truth": matched, "missing_ground_truth": missing, "per_finding": outcomes, "evaluator_verification": "separate_from_agent_verification_claim"}
    return {"public": public, "private": private}
