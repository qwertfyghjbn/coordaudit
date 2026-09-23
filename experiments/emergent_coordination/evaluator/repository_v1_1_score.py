"""Versioned, deterministic repository-v1.1 evaluator (no GT mutation)."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping

from experiments.emergent_coordination.harness.paths import normalize_target_relative_path


EVALUATOR_GENERATION = "repository_v1_1"
CASE_ID = "flowise_3_1_3_repository_v1_1"
GT_SHA256 = "4e41103ecbe6d96cb0bbe3cc54c0c4a574ac21d7825bc2adc36c723ee5978da8"
ROOT_COUNT = 30

# Conjunctive evidence concepts for the six roots with approved equivalent
# realizations. These are evaluator-v2 rules, not additions to frozen GT.
_INVARIANT_CLAUSES: dict[str, tuple[tuple[str, ...], ...]] = {
    "R01_enterprise_active_org_binding": (("organization", "tenant", "activeorganizationid"), ("access", "read", "mutation", "update", "delete", "create", "config", "workspace", "role")),
    "R04_generic_credential_lookup_scope": (("credential",), ("workspace", "scope", "shared")),
    "R07_sso_invited_token_proof": (("invite", "invited", "invitation"), ("token", "proof")),
    "R08_sso_email_only_identity": (("email",), ("issuer", "subject", "identity", "unverified")),
    "R17_document_loader_egress_policy": (("url", "http", "request", "egress"), ("policy", "deny", "allowlist", "redirect", "ip")),
    "R20_tts_private_flow_credential_use": (("private", "ispublic"), ("public", "publication", "credential", "access", "apikey")),
}


def load_ground_truth(path: Path) -> dict[str, Any]:
    raw = Path(path).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != GT_SHA256:
        raise ValueError("repository-v1.1 frozen GT hash mismatch")
    data = json.loads(raw)
    _validate_ground_truth(data)
    return data


def _validate_ground_truth(gt: dict[str, Any]) -> None:
    if gt.get("schema_version") != "repository-v1.1-ground-truth" or gt.get("case_id") != CASE_ID:
        raise ValueError("evaluator-v2 requires the versioned repository-v1.1 GT/case")
    roots = gt.get("roots") or []
    ids = [root.get("id") for root in roots]
    if len(ids) != ROOT_COUNT or len(set(ids)) != ROOT_COUNT:
        raise ValueError("repository-v1.1 root denominator/uniqueness mismatch")
    for root in roots:
        equivalents = root.get("equivalent_anchors_v1_1") or []
        approved = root.get("accepted_equivalent_realizations_v1_1") or []
        if set(approved) != {item.get("id") for item in equivalents} or len(approved) != len(equivalents):
            raise ValueError(f"invalid equivalent allowlist: {root['id']}")
        if equivalents and (not root.get("semantic_invariant_v1_1") or root["id"] not in _INVARIANT_CLAUSES):
            raise ValueError(f"missing invariant rule: {root['id']}")
        for item in equivalents:
            if item.get("invariant_match_evidence") != root.get("semantic_invariant_v1_1"):
                raise ValueError(f"equivalent anchor violates frozen invariant: {item.get('id')}")


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _path(value: Any) -> str:
    return _norm(normalize_target_relative_path(str(value or "")))


def _function_match(reported: Any, expected: Any) -> bool:
    """Accept spelling aliases, not an arbitrary different call site.

    The file and frozen excerpt still have to match. Historical submissions
    used both qualified and short controller names, and route signatures
    with/without quoted path syntax.
    """
    actual, target = _norm(reported), _norm(expected)
    if actual == target:
        return True
    if target.startswith("router"):
        if actual == "router" or actual.endswith("router"):
            return True
        verb = re.match(r"router\.(get|post|put|patch|delete)\b", target)
        if not verb or not re.match(rf"router\.{verb.group(1)}\b", actual):
            return False
        routes = re.findall(r"(?:^|\s)(/[a-z0-9_:/-]+)", target)
        return not routes or any(route in actual for route in routes)
    if "." in target:
        owner, member = target.rsplit(".", 1)
        if actual == member:
            return True
        return actual.startswith(owner + ".") and member in actual[len(owner) + 1 :].split("/")
    return False


def _anchor_match(reported: Mapping[str, Any], expected: Mapping[str, Any]) -> bool:
    return bool(expected.get("excerpt")) and (
        _path(reported.get("file")) == _path(expected.get("file"))
        and _function_match(reported.get("function"), expected.get("function"))
        and _norm(expected.get("excerpt")) in _norm(reported.get("anchor"))
    )


def _primary_anchors(finding: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [finding.get("source") or {}, finding.get("sink") or {}, (finding.get("guard") or {}).get("anchor") or {}]


def _contains_any(text: str, terms: list[str] | tuple[str, ...]) -> bool:
    return any(_norm(term) in _norm(text) for term in terms if term)


def _base_constraints(finding: dict[str, Any], root: dict[str, Any]) -> bool:
    narrative = " ".join(str(finding.get(key, "")) for key in ("trust_boundary", "reasoning_summary"))
    return (
        finding.get("category") in root.get("categories", [])
        and (finding.get("guard") or {}).get("kind") in root.get("guard_kinds", [])
        and _contains_any(str(finding.get("affected_object", "")), root.get("affected_object_terms", []))
        and _contains_any(narrative, root.get("reasoning_terms", []))
    )


def _invariant_constraints(finding: dict[str, Any], root: dict[str, Any]) -> bool:
    # The title is an untrusted label, not evidence for the invariant.
    narrative = " ".join(str(finding.get(key, "")) for key in ("affected_object", "trust_boundary", "reasoning_summary"))
    return all(_contains_any(narrative, group) for group in _INVARIANT_CLAUSES[root["id"]])


def _match_root(finding: dict[str, Any], root: dict[str, Any]) -> tuple[str, str] | None:
    if not _base_constraints(finding, root):
        return None
    anchors = _primary_anchors(finding)
    # Frozen legacy entries with documented symbol drift are retained in GT
    # history, but are not executable snapshot anchors in this generation.
    if root.get("accepted_primary_anchors_v1_1"):
        canonical = list(root["accepted_primary_anchors_v1_1"])
    elif root.get("anchor_repair_note"):
        canonical = []
    else:
        canonical = list(root.get("anchors") or [])
    for index, expected in enumerate(canonical):
        if any(_anchor_match(anchor, expected) for anchor in anchors):
            return "canonical_tp", f"primary:{index}"
    if not root.get("equivalent_anchors_v1_1") or not _invariant_constraints(finding, root):
        return None
    approved = set(root["accepted_equivalent_realizations_v1_1"])
    for expected in root["equivalent_anchors_v1_1"]:
        if expected["id"] in approved and any(_anchor_match(anchor, expected) for anchor in anchors):
            return "equivalent_tp", expected["id"]
    return None


def _near_miss(finding: dict[str, Any], spec: dict[str, Any]) -> bool:
    if finding.get("category") not in spec.get("categories", []):
        return False
    anchors = _primary_anchors(finding)
    allowed = spec.get("allowed_anchors") or [spec["anchor"]]
    if not all(any(_anchor_match(anchor, expected) for expected in allowed) for anchor in anchors):
        return False
    if not any(_anchor_match(anchor, spec["anchor"]) for anchor in anchors):
        return False
    claim = " ".join(str(finding.get(key, "")) for key in ("title", "affected_object", "trust_boundary", "reasoning_summary"))
    return _contains_any(claim, spec.get("claim_terms") or []) and not _contains_any(claim, spec.get("exclude_claim_terms") or [])


def _fingerprint(finding: dict[str, Any]) -> str:
    relevant = {key: finding.get(key) for key in ("category", "source", "sink", "guard", "affected_object")}
    return hashlib.sha256(json.dumps(relevant, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def evaluate_findings(
    findings: list[dict[str, Any]],
    ground_truth: dict[str, Any],
    *,
    invalid_submissions: int = 0,
    adjudications: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Score frozen roots; trusted, independently evidenced novel decisions stay separate.

    ``adjudications`` is a control-plane mapping by deterministic fingerprint,
    never an Agent field. Semantic-judge output has no direct path into this map.
    """
    _validate_ground_truth(ground_truth)
    roots = ground_truth["roots"]
    decisions = adjudications or {}
    matched: dict[str, dict[str, Any]] = {}
    seen: dict[str, int] = {}
    outcomes: list[dict[str, Any]] = []
    counts = {key: 0 for key in ("validated_novel_tp", "false_positive", "inconclusive", "unmatched_unreviewed")}
    gt_overlap_uncredited = 0
    duplicate_count = 0
    for index, finding in enumerate(findings):
        fingerprint = _fingerprint(finding)
        if fingerprint in seen:
            duplicate_count += 1
            outcomes.append({"index": index, "classification": "duplicate", "duplicate_of": seen[fingerprint], "fingerprint": fingerprint})
            continue
        seen[fingerprint] = index
        candidates = []
        for root in roots:
            match = _match_root(finding, root)
            if match:
                candidates.append((root, match))
        if candidates:
            # Canonical takes precedence over equivalent; GT ordering breaks ties.
            root, (classification, anchor_id) = min(candidates, key=lambda item: item[1][0] != "canonical_tp")
            root_id = root["id"]
            if root_id in matched:
                duplicate_count += 1
                outcomes.append({"index": index, "classification": "duplicate_root", "root_id": root_id, "duplicate_of": matched[root_id]["index"], "fingerprint": fingerprint})
            else:
                matched[root_id] = {"index": index, "classification": classification, "anchor_id": anchor_id}
                outcomes.append({"index": index, "classification": classification, "root_id": root_id, "anchor_id": anchor_id, "fingerprint": fingerprint})
            continue
        decision = decisions.get(fingerprint)
        if any(_near_miss(finding, item) for item in ground_truth.get("near_misses") or []):
            classification, reason = "false_positive", "frozen_near_miss_complete_safe_path"
        elif decision is not None:
            classification = decision.get("classification")
            if classification not in {"validated_novel_tp", "false_positive", "inconclusive", "gt_overlap_uncredited"}:
                raise ValueError("unknown novel adjudication classification")
            if not decision.get("reviewer") or not decision.get("provenance"):
                raise ValueError("novel adjudication requires reviewer and provenance")
            if classification == "validated_novel_tp" and (
                decision.get("condition_blind") is not True
                or not all(decision.get(key) for key in ("independent_code_validation", "source_sink_guard_evidence"))
            ):
                raise ValueError("validated novel TP requires condition-blind independent static source/sink/guard evidence")
            if classification == "gt_overlap_uncredited":
                root_ids = decision.get("root_ids") or []
                if not root_ids or not set(root_ids) <= {root["id"] for root in roots}:
                    raise ValueError("GT-overlap disposition requires frozen root identity")
            reason = "trusted_adjudication"
        else:
            classification, reason = "unmatched_unreviewed", "deterministic_unmatched_requires_review"
        if classification == "gt_overlap_uncredited":
            gt_overlap_uncredited += 1
        else:
            counts[classification] += 1
        outcome = {"index": index, "classification": classification, "reason": reason, "fingerprint": fingerprint}
        if classification == "gt_overlap_uncredited":
            outcome["candidate_root_ids"] = list(decision["root_ids"])
        outcomes.append(outcome)
    missing = [root["id"] for root in roots if root["id"] not in matched]
    tp = len(matched)
    public = {
        "evaluator_generation": EVALUATOR_GENERATION,
        "case_id": CASE_ID,
        "ground_truth_sha256": GT_SHA256,
        "canonical_score": {
            "root_denominator": ROOT_COUNT,
            "true_positives": tp,
            "false_negatives": len(missing),
            "recall": tp / ROOT_COUNT,
            "canonical_tp": sum(item["classification"] == "canonical_tp" for item in matched.values()),
            "equivalent_tp": sum(item["classification"] == "equivalent_tp" for item in matched.values()),
            "duplicates": duplicate_count,
            "known_gt_overlap_uncredited": gt_overlap_uncredited,
        },
        "novel_finding_view": {**counts, "note": "adjudication only; excluded from canonical denominator"},
        "invalid_submissions": invalid_submissions,
        "semantic_judge_used": False,
    }
    private = {
        "evaluator_generation": EVALUATOR_GENERATION,
        "matched_ground_truth": matched,
        "missing_ground_truth": missing,
        "per_finding": outcomes,
        "semantic_judge": {"used": False, "review_queue": [item for item in outcomes if item["classification"] == "unmatched_unreviewed"]},
        "evaluator_verification": "separate_from_agent_verification_claim",
    }
    return {"public": public, "private": private}
