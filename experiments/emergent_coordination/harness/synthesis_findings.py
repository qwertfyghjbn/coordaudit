"""Versioned repository-v1-synthesis-v1 finding contract for T-Pilot 2.

Extends the frozen repository-v1 intake with synthesis provenance:

* every final finding carries ``final_id`` and a non-empty ``derived_from``
  list of raw candidate ids — an empty list is rejected, so the finalizer
  can never introduce a finding with no raw source;
* every raw candidate receives exactly one explicit ``raw_decision``
  (retain / merge / correct / drop), so a dropped raw can never silently
  disappear.

Field rules for the base repository-v1 keys are reused verbatim from
``repository_v1_findings``; only the synthesis-specific keys and the
cross-consistency rules live here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from experiments.emergent_coordination.harness import repository_v1_findings as base

SCHEMA_VERSION = "repository-v1-synthesis-v1"
SYNTHESIS_ACTIONS = frozenset({"retain", "merge", "correct", "drop"})
_RAW_ID = re.compile(r"^raw_\d{2,}$")
_FINAL_ID = re.compile(r"^fin_\d{2,}$")
_EVENT_ID = re.compile(r"^evt_\d{8}$")
_TOP_KEYS = frozenset({"schema_version", "findings", "raw_decisions"})
_FINDING_KEYS = base._FINDING_KEYS | {"final_id", "derived_from"}
_DECISION_KEYS = frozenset({"raw_id", "action", "target_final_id", "merged_with", "evidence_refs", "rationale"})


@dataclass(frozen=True)
class IntakeResult:
    payload: dict[str, Any] | None
    errors: list[dict[str, str]]

    @property
    def accepted(self) -> bool:
        return self.payload is not None and not self.errors


def validate_synthesis_payload(
    value: Any,
    known_raw_ids: set[str] | frozenset[str],
    raw_findings: dict[str, dict[str, Any]] | None = None,
) -> IntakeResult:
    errors: list[dict[str, str]] = []
    if not isinstance(value, dict):
        return IntakeResult(None, [_error("$", "must be a repository-v1-synthesis-v1 object")])
    _exact_keys(value, _TOP_KEYS, "$", errors)
    if value.get("schema_version") != SCHEMA_VERSION:
        errors.append(_error("schema_version", f"must equal {SCHEMA_VERSION!r}"))
    findings = value.get("findings")
    final_ids: set[str] = set()
    final_by_id: dict[str, dict[str, Any]] = {}
    derived_owner: dict[str, list[str]] = {}
    if not isinstance(findings, list):
        errors.append(_error("findings", "must be an array"))
    elif len(findings) > 32:
        errors.append(_error("findings", "must contain at most 32 findings"))
    else:
        for index, finding in enumerate(findings):
            path = f"findings[{index}]"
            if not isinstance(finding, dict):
                errors.append(_error(path, "must be an object"))
                continue
            _exact_keys(finding, _FINDING_KEYS, path, errors)
            # Base repository-v1 field rules, reused verbatim.
            base._validate_finding({key: item for key, item in finding.items() if key in base._FINDING_KEYS}, path, errors)
            final_id = finding.get("final_id")
            if not isinstance(final_id, str) or not _FINAL_ID.fullmatch(final_id):
                errors.append(_error(f"{path}.final_id", "must be a fin_XX id"))
            elif final_id in final_ids:
                errors.append(_error(f"{path}.final_id", "must be unique across findings"))
            else:
                final_ids.add(final_id)
                final_by_id[final_id] = finding
            derived = finding.get("derived_from")
            if not isinstance(derived, list) or not derived:
                errors.append(_error(f"{path}.derived_from", "must be a non-empty array of raw ids"))
            elif len(derived) > 32:
                errors.append(_error(f"{path}.derived_from", "must contain at most 32 raw ids"))
            else:
                seen: set[str] = set()
                for member_index, member in enumerate(derived):
                    if not isinstance(member, str) or not _RAW_ID.fullmatch(member):
                        errors.append(_error(f"{path}.derived_from[{member_index}]", "must be a raw_XX id"))
                    elif member in seen:
                        errors.append(_error(f"{path}.derived_from", "must not contain duplicates"))
                    else:
                        seen.add(member)
                        derived_owner.setdefault(member, []).append(final_id)
    decisions = value.get("raw_decisions")
    decided: dict[str, dict[str, Any]] = {}
    if not isinstance(decisions, list):
        errors.append(_error("raw_decisions", "must be an array"))
    else:
        for index, decision in enumerate(decisions):
            path = f"raw_decisions[{index}]"
            if not isinstance(decision, dict):
                errors.append(_error(path, "must be an object"))
                continue
            _exact_keys(decision, _DECISION_KEYS, path, errors)
            raw_id = decision.get("raw_id")
            if not isinstance(raw_id, str) or not _RAW_ID.fullmatch(raw_id):
                errors.append(_error(f"{path}.raw_id", "must be a raw_XX id"))
            elif raw_id in decided:
                errors.append(_error(f"{path}.raw_id", f"duplicate decision for {raw_id}"))
            else:
                decided[raw_id] = decision
            action = decision.get("action")
            if action not in SYNTHESIS_ACTIONS:
                errors.append(_error(f"{path}.action", "must be retain, merge, correct, or drop"))
            target = decision.get("target_final_id")
            if action == "drop":
                if target is not None:
                    errors.append(_error(f"{path}.target_final_id", "must be null for a drop decision"))
            elif not isinstance(target, str) or not _FINAL_ID.fullmatch(target):
                errors.append(_error(f"{path}.target_final_id", f"must reference a final finding for {action}"))
            merged_with = decision.get("merged_with")
            if action == "merge":
                if not isinstance(merged_with, list) or not merged_with:
                    errors.append(_error(f"{path}.merged_with", "must be a non-empty array of other raw ids for a merge"))
                else:
                    for member_index, member in enumerate(merged_with):
                        if not isinstance(member, str) or not _RAW_ID.fullmatch(member):
                            errors.append(_error(f"{path}.merged_with[{member_index}]", "must be a raw_XX id"))
                        elif member == raw_id:
                            errors.append(_error(f"{path}.merged_with", "must not include the decision's own raw id"))
            elif merged_with not in (None, []):
                errors.append(_error(f"{path}.merged_with", f"must be null or empty for {action}"))
            refs = decision.get("evidence_refs")
            if not isinstance(refs, list):
                errors.append(_error(f"{path}.evidence_refs", "must be an array of event ids"))
            elif len(refs) > 16:
                errors.append(_error(f"{path}.evidence_refs", "must contain at most 16 references"))
            else:
                if not refs and action != "drop":
                    errors.append(_error(f"{path}.evidence_refs", f"must not be empty for {action}"))
                if len(set(refs)) != len(refs):
                    errors.append(_error(f"{path}.evidence_refs", "must not contain duplicates"))
                for ref_index, reference in enumerate(refs):
                    if not isinstance(reference, str) or not _EVENT_ID.fullmatch(reference):
                        errors.append(_error(f"{path}.evidence_refs[{ref_index}]", "must be an evt_XXXXXXXX id"))
            rationale = decision.get("rationale")
            if not isinstance(rationale, str) or not 1 <= len(rationale.strip()) <= 2000:
                errors.append(_error(f"{path}.rationale", "must be a non-empty string of at most 2000 characters"))
    if isinstance(findings, list) and isinstance(decisions, list):
        for raw_id in sorted(known_raw_ids - set(decided)):
            errors.append(_error("raw_decisions", f"missing decision for {raw_id}"))
        for raw_id in sorted(set(decided) - set(known_raw_ids)):
            errors.append(_error("raw_decisions", f"unknown raw id {raw_id}"))
        for member in sorted(set(derived_owner) - set(known_raw_ids)):
            errors.append(_error("findings", f"derived_from references unknown raw id {member}"))
        for raw_id, decision in sorted(decided.items()):
            if raw_id not in known_raw_ids:
                continue
            action = decision.get("action")
            targets = derived_owner.get(raw_id, [])
            if action == "drop":
                if targets:
                    errors.append(_error("findings", f"dropped raw {raw_id} appears in derived_from of {targets}"))
                continue
            if not targets:
                errors.append(_error("findings", f"raw {raw_id} has action {action} but no finding derives from it"))
                continue
            target = decision.get("target_final_id")
            if isinstance(target, str) and target not in targets:
                errors.append(
                    _error(
                        "raw_decisions",
                        f"decision for {raw_id} targets {target} but the raw is derived into {targets}",
                    )
                )
            if action == "merge":
                merged_with = decision.get("merged_with")
                if isinstance(merged_with, list) and isinstance(target, str):
                    for member in merged_with:
                        if isinstance(member, str) and target not in derived_owner.get(member, []):
                            errors.append(
                                _error(
                                    "raw_decisions",
                                    f"merge member {member} is not derived into target {target}",
                                )
                            )
        for final_id, finding in final_by_id.items():
            members = finding.get("derived_from")
            if not isinstance(members, list) or not members:
                continue
            for raw_id in members:
                if raw_id not in known_raw_ids:
                    continue
                if len(derived_owner.get(raw_id, [])) != 1:
                    errors.append(_error("findings", f"raw {raw_id} must derive into exactly one final finding"))
                decision = decided.get(raw_id)
                if not isinstance(decision, dict) or decision.get("target_final_id") != final_id:
                    continue
                if len(members) > 1:
                    if decision.get("action") != "merge":
                        errors.append(_error("raw_decisions", f"raw {raw_id} in merged {final_id} requires merge action"))
                    merged_members = decision.get("merged_with")
                    if not isinstance(merged_members, list) or any(not isinstance(item, str) for item in merged_members) or set(merged_members) != set(members) - {raw_id}:
                        errors.append(_error("raw_decisions", f"raw {raw_id} merged_with must list all other members of {final_id}"))
                elif decision.get("action") == "merge":
                    errors.append(_error("raw_decisions", f"single-source {final_id} cannot use merge action"))
                if raw_findings is not None and len(members) == 1 and raw_id in raw_findings:
                    base_finding = {key: finding.get(key) for key in base._FINDING_KEYS}
                    changed = base_finding != raw_findings[raw_id]
                    if decision.get("action") == "retain" and changed:
                        errors.append(_error("raw_decisions", f"retain {raw_id} must preserve the raw finding fields"))
                    if decision.get("action") == "correct" and not changed:
                        errors.append(_error("raw_decisions", f"correct {raw_id} requires a finding field change"))
    return IntakeResult(None if errors else {"schema_version": SCHEMA_VERSION, "findings": findings, "raw_decisions": decisions}, errors)


def _exact_keys(value: dict[str, Any], expected: frozenset[str], path: str, errors: list[dict[str, str]]) -> None:
    for key in sorted(expected - set(value)):
        errors.append(_error(f"{path}.{key}" if path != "$" else key, "is required"))
    for key in sorted(set(value) - expected):
        errors.append(_error(f"{path}.{key}" if path != "$" else key, "is not allowed by the synthesis schema"))


def _error(path: str, message: str) -> dict[str, str]:
    return {"path": path, "message": message}
