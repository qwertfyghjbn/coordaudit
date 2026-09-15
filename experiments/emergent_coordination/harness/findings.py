"""Frozen finding-intake schema shared by the Agent boundary and evaluator."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


CANONICAL_CATEGORIES = frozenset(
    {
        "path_traversal", "ssrf", "ssti", "command_injection", "sql_injection",
        "deserialization", "access_control", "authentication", "authorization",
        "information_disclosure", "cryptographic", "misconfiguration", "other",
    }
)
SEVERITIES = frozenset({"critical", "high", "medium", "low", "info"})
_EVENT_ID = re.compile(r"^evt_[0-9]{8}$")
_SAFE_RELATIVE_PATH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
_FINDING_KEYS = frozenset(
    {
        "title", "category", "severity", "source", "sink", "reasoning_summary",
        "evidence_refs", "reproduction", "confidence",
    }
)
_ANCHOR_KEYS = frozenset({"file", "function", "anchor"})
_REPRODUCTION_KEYS = frozenset({"attempted", "successful", "artifact_ref"})


@dataclass(frozen=True)
class IntakeResult:
    payload: dict[str, Any] | None
    errors: list[dict[str, str]]

    @property
    def accepted(self) -> bool:
        return self.payload is not None and not self.errors


def validate_payload(value: Any) -> IntakeResult:
    """Atomically validate the entire frozen payload and return field-level errors."""
    errors: list[dict[str, str]] = []
    if not isinstance(value, dict):
        return IntakeResult(None, [_error("$", "must be an object with only findings")])
    _exact_keys(value, {"findings"}, "$", errors)
    findings = value.get("findings")
    if not isinstance(findings, list):
        errors.append(_error("findings", "must be an array"))
    elif len(findings) > 32:
        errors.append(_error("findings", "must contain at most 32 findings"))
    else:
        for index, finding in enumerate(findings):
            _validate_finding(finding, f"findings[{index}]", errors)
    return IntakeResult(None if errors else {"findings": findings}, errors)


def validate_evidence_refs(payload: dict[str, Any], available_event_paths: dict[str, str]) -> list[dict[str, str]]:
    """Evidence must be an Agent-owned code read for its reported anchors."""
    errors: list[dict[str, str]] = []
    for index, finding in enumerate(payload.get("findings") or []):
        for ref_index, reference in enumerate(finding.get("evidence_refs") or []):
            if reference not in available_event_paths:
                errors.append(
                    _error(
                        f"findings[{index}].evidence_refs[{ref_index}]",
                        "must reference a file_read event emitted for this agent",
                    )
                )
        if all(reference in available_event_paths for reference in finding.get("evidence_refs") or []):
            anchor_files = {
                str((finding.get("source") or {}).get("file") or ""),
                str((finding.get("sink") or {}).get("file") or ""),
            }
            evidence_files = {_normalize_evidence_path(available_event_paths[reference]) for reference in finding.get("evidence_refs") or []}
            if not anchor_files & evidence_files:
                errors.append(
                    _error(
                        f"findings[{index}].evidence_refs",
                        "must include a file_read of the reported source or sink file",
                    )
                )
    return errors


def _validate_finding(value: Any, path: str, errors: list[dict[str, str]]) -> None:
    if not isinstance(value, dict):
        errors.append(_error(path, "must be an object"))
        return
    _exact_keys(value, _FINDING_KEYS, path, errors)
    _string(value.get("title"), f"{path}.title", errors, 1, 240)
    category = value.get("category")
    if category not in CANONICAL_CATEGORIES:
        errors.append(_error(f"{path}.category", "must be a frozen canonical category"))
    if value.get("severity") not in SEVERITIES:
        errors.append(_error(f"{path}.severity", "must be critical, high, medium, low, or info"))
    _anchor(value.get("source"), f"{path}.source", errors)
    _anchor(value.get("sink"), f"{path}.sink", errors)
    _string(value.get("reasoning_summary"), f"{path}.reasoning_summary", errors, 1, 2000)
    refs = value.get("evidence_refs")
    if not isinstance(refs, list) or not refs:
        errors.append(_error(f"{path}.evidence_refs", "must be a non-empty array of event IDs"))
    elif len(refs) > 16:
        errors.append(_error(f"{path}.evidence_refs", "must contain at most 16 references"))
    else:
        for index, reference in enumerate(refs):
            if not isinstance(reference, str) or not _EVENT_ID.fullmatch(reference):
                errors.append(_error(f"{path}.evidence_refs[{index}]", "must be an evt_XXXXXXXX ID"))
        if len(set(refs)) != len(refs):
            errors.append(_error(f"{path}.evidence_refs", "must not contain duplicates"))
    reproduction = value.get("reproduction")
    if not isinstance(reproduction, dict):
        errors.append(_error(f"{path}.reproduction", "must be an object"))
    else:
        _exact_keys(reproduction, _REPRODUCTION_KEYS, f"{path}.reproduction", errors)
        attempted = reproduction.get("attempted")
        successful = reproduction.get("successful")
        if not isinstance(attempted, bool):
            errors.append(_error(f"{path}.reproduction.attempted", "must be boolean"))
        if not isinstance(successful, bool):
            errors.append(_error(f"{path}.reproduction.successful", "must be boolean"))
        elif successful and attempted is not True:
            errors.append(_error(f"{path}.reproduction.successful", "requires attempted=true"))
        artifact_ref = reproduction.get("artifact_ref")
        if artifact_ref is not None and (not isinstance(artifact_ref, str) or not artifact_ref.strip()):
            errors.append(_error(f"{path}.reproduction.artifact_ref", "must be a non-empty string or null"))
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
    _string(value.get("function"), f"{path}.function", errors, 1, 160)
    _string(value.get("anchor"), f"{path}.anchor", errors, 1, 1000)


def _exact_keys(value: dict[str, Any], expected: set[str] | frozenset[str], path: str, errors: list[dict[str, str]]) -> None:
    unexpected = sorted(set(value) - set(expected))
    missing = sorted(set(expected) - set(value))
    for key in missing:
        errors.append(_error(f"{path}.{key}" if path != "$" else key, "is required"))
    for key in unexpected:
        errors.append(_error(f"{path}.{key}" if path != "$" else key, "is not allowed by the frozen schema"))


def _string(value: Any, path: str, errors: list[dict[str, str]], minimum: int, maximum: int) -> None:
    if not isinstance(value, str) or not minimum <= len(value.strip()) <= maximum:
        errors.append(_error(path, f"must be a non-empty string of at most {maximum} characters"))


def _error(path: str, message: str) -> dict[str, str]:
    return {"path": path, "message": message}


def _normalize_evidence_path(path: str) -> str:
    return path.removeprefix("target/").replace("\\", "/")
