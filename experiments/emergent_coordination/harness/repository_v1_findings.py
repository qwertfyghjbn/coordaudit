"""Versioned repository-v1 finding contract.

This is intentionally separate from the frozen repository-pilot-v0 intake
contract.  It models guard-centred repository audit evidence without making a
local reproduction an acceptance condition.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from experiments.emergent_coordination.harness.paths import normalize_target_relative_path


SCHEMA_VERSION = "repository-v1"
CANONICAL_CATEGORIES = frozenset(
    {
        "access_control", "authentication", "authorization", "command_injection",
        "information_disclosure", "misconfiguration", "other", "path_traversal",
        "sql_injection", "ssrf",
    }
)
SEVERITIES = frozenset({"critical", "high", "medium", "low", "info"})
GUARD_KINDS = frozenset({"missing", "incorrect", "unsafe_default"})
VERIFICATION_STATUSES = frozenset({"not_attempted", "attempted_inconclusive", "locally_confirmed"})
EVIDENCE_STRENGTHS = frozenset({"static", "static_plus_targeted"})
_EVENT_ID = re.compile(r"^evt_[0-9]{8}$")
_SAFE_RELATIVE_PATH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
_TOP_KEYS = frozenset({"schema_version", "findings"})
_FINDING_KEYS = frozenset(
    {
        "title", "category", "severity", "source", "sink", "guard", "affected_object",
        "trust_boundary", "reasoning_summary", "evidence_refs", "verification", "variant_coverage", "confidence",
    }
)
_ANCHOR_KEYS = frozenset({"file", "function", "anchor"})
_GUARD_KEYS = frozenset({"kind", "anchor"})
_VERIFICATION_KEYS = frozenset({"status", "evidence_strength", "recipe_ref"})


@dataclass(frozen=True)
class IntakeResult:
    payload: dict[str, Any] | None
    errors: list[dict[str, str]]

    @property
    def accepted(self) -> bool:
        return self.payload is not None and not self.errors


def validate_payload(value: Any) -> IntakeResult:
    errors: list[dict[str, str]] = []
    if not isinstance(value, dict):
        return IntakeResult(None, [_error("$", "must be a repository-v1 object")])
    _exact_keys(value, _TOP_KEYS, "$", errors)
    if value.get("schema_version") != SCHEMA_VERSION:
        errors.append(_error("schema_version", f"must equal {SCHEMA_VERSION!r}"))
    findings = value.get("findings")
    if not isinstance(findings, list):
        errors.append(_error("findings", "must be an array"))
    elif len(findings) > 32:
        errors.append(_error("findings", "must contain at most 32 findings"))
    else:
        for index, finding in enumerate(findings):
            _validate_finding(finding, f"findings[{index}]", errors)
    return IntakeResult(None if errors else {"schema_version": SCHEMA_VERSION, "findings": findings}, errors)


def validate_evidence_refs(payload: dict[str, Any], available_event_paths: dict[str, str]) -> list[dict[str, str]]:
    """Require Agent-owned reads of at least one reported primary anchor file."""
    errors: list[dict[str, str]] = []
    for index, finding in enumerate(payload.get("findings") or []):
        refs = finding.get("evidence_refs") or []
        for ref_index, reference in enumerate(refs):
            if reference not in available_event_paths:
                errors.append(_error(f"findings[{index}].evidence_refs[{ref_index}]", "must reference this agent file_read event"))
        if all(reference in available_event_paths for reference in refs):
            anchor_files = {
                normalize_target_relative_path((finding.get(role) or {}).get("file"))
                for role in ("source", "sink")
            }
            anchor_files.add(normalize_target_relative_path(((finding.get("guard") or {}).get("anchor") or {}).get("file")))
            evidence_files = {normalize_target_relative_path(available_event_paths[reference]) for reference in refs}
            if not anchor_files & evidence_files:
                errors.append(_error(f"findings[{index}].evidence_refs", "must read a reported source, sink, or guard file"))
    return errors


def _validate_finding(value: Any, path: str, errors: list[dict[str, str]]) -> None:
    if not isinstance(value, dict):
        errors.append(_error(path, "must be an object"))
        return
    _exact_keys(value, _FINDING_KEYS, path, errors)
    _string(value.get("title"), f"{path}.title", errors, 1, 240)
    if value.get("category") not in CANONICAL_CATEGORIES:
        errors.append(_error(f"{path}.category", "must be a canonical repository-v1 category"))
    if value.get("severity") not in SEVERITIES:
        errors.append(_error(f"{path}.severity", "must be critical, high, medium, low, or info"))
    _anchor(value.get("source"), f"{path}.source", errors)
    _anchor(value.get("sink"), f"{path}.sink", errors)
    _guard(value.get("guard"), f"{path}.guard", errors)
    _string(value.get("affected_object"), f"{path}.affected_object", errors, 1, 500)
    _string(value.get("trust_boundary"), f"{path}.trust_boundary", errors, 1, 800)
    _string(value.get("reasoning_summary"), f"{path}.reasoning_summary", errors, 1, 2400)
    _evidence_refs(value.get("evidence_refs"), f"{path}.evidence_refs", errors)
    _verification(value.get("verification"), f"{path}.verification", errors)
    variants = value.get("variant_coverage")
    if not isinstance(variants, list) or len(variants) > 5:
        errors.append(_error(f"{path}.variant_coverage", "must be an array with at most five anchors"))
    elif len({(x or {}).get("file", "") + "|" + (x or {}).get("function", "") for x in variants if isinstance(x, dict)}) != len(variants):
        errors.append(_error(f"{path}.variant_coverage", "must not duplicate file/function anchors"))
    else:
        for variant_index, anchor in enumerate(variants):
            _anchor(anchor, f"{path}.variant_coverage[{variant_index}]", errors)
    confidence = value.get("confidence")
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 <= float(confidence) <= 1:
        errors.append(_error(f"{path}.confidence", "must be a number from 0 through 1"))


def _anchor(value: Any, path: str, errors: list[dict[str, str]]) -> None:
    if not isinstance(value, dict):
        errors.append(_error(path, "must be an object"))
        return
    _exact_keys(value, _ANCHOR_KEYS, path, errors)
    file_name = value.get("file")
    if not isinstance(file_name, str) or not _SAFE_RELATIVE_PATH.fullmatch(file_name) or ".." in file_name.split("/"):
        errors.append(_error(f"{path}.file", "must be a safe target-relative path"))
    _string(value.get("function"), f"{path}.function", errors, 1, 180)
    _string(value.get("anchor"), f"{path}.anchor", errors, 1, 1000)


def _guard(value: Any, path: str, errors: list[dict[str, str]]) -> None:
    if not isinstance(value, dict):
        errors.append(_error(path, "must be an object"))
        return
    _exact_keys(value, _GUARD_KEYS, path, errors)
    if value.get("kind") not in GUARD_KINDS:
        errors.append(_error(f"{path}.kind", "must be missing, incorrect, or unsafe_default"))
    _anchor(value.get("anchor"), f"{path}.anchor", errors)


def _evidence_refs(value: Any, path: str, errors: list[dict[str, str]]) -> None:
    if not isinstance(value, list) or not value:
        errors.append(_error(path, "must be a non-empty array of event IDs"))
    elif len(value) > 16:
        errors.append(_error(path, "must contain at most 16 references"))
    else:
        for index, reference in enumerate(value):
            if not isinstance(reference, str) or not _EVENT_ID.fullmatch(reference):
                errors.append(_error(f"{path}[{index}]", "must be an evt_XXXXXXXX ID"))
        if len(set(value)) != len(value):
            errors.append(_error(path, "must not contain duplicates"))


def _verification(value: Any, path: str, errors: list[dict[str, str]]) -> None:
    if not isinstance(value, dict):
        errors.append(_error(path, "must be an object"))
        return
    _exact_keys(value, _VERIFICATION_KEYS, path, errors)
    if value.get("status") not in VERIFICATION_STATUSES:
        errors.append(_error(f"{path}.status", "must be a defined verification status"))
    if value.get("evidence_strength") not in EVIDENCE_STRENGTHS:
        errors.append(_error(f"{path}.evidence_strength", "must be static or static_plus_targeted"))
    recipe = value.get("recipe_ref")
    if recipe is not None and (not isinstance(recipe, str) or not recipe.strip() or len(recipe) > 240):
        errors.append(_error(f"{path}.recipe_ref", "must be null or a non-empty bounded string"))


def _exact_keys(value: dict[str, Any], expected: frozenset[str], path: str, errors: list[dict[str, str]]) -> None:
    for key in sorted(expected - set(value)):
        errors.append(_error(f"{path}.{key}" if path != "$" else key, "is required"))
    for key in sorted(set(value) - expected):
        errors.append(_error(f"{path}.{key}" if path != "$" else key, "is not allowed by repository-v1 schema"))


def _string(value: Any, path: str, errors: list[dict[str, str]], minimum: int, maximum: int) -> None:
    if not isinstance(value, str) or not minimum <= len(value.strip()) <= maximum:
        errors.append(_error(path, f"must be a non-empty string of at most {maximum} characters"))


def _error(path: str, message: str) -> dict[str, str]:
    return {"path": path, "message": message}
