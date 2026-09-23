"""Trusted case selection for repository audit experiments.

The resolver deliberately accepts case IDs rather than arbitrary manifest or
filesystem paths.  Agent-visible execution receives only the selected target;
the corresponding evaluator-private tree remains in the trusted control plane.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from experiments.emergent_coordination.harness.paths import EXPERIMENT_ROOT


class CaseSelectionError(ValueError):
    """The requested case is unknown or its trusted manifest is malformed."""


_MANIFESTS = {
    "repo_pilot_v0": "repository_pilot_v0.json",
    "flowise_3_1_3_repository_v1": "flowise_3_1_3_repository_v1.json",
    "flowise_3_1_3_repository_v1_1": "flowise_3_1_3_repository_v1_1.json",
}


@dataclass(frozen=True)
class CaseDefinition:
    case_id: str
    manifest_path: Path
    target_root: Path
    evaluator_private_root: Path
    ground_truth_path: Path
    provenance_path: Path | None
    prompt_profile: str
    finding_schema: str
    evaluator: str
    manifest: dict[str, Any]


def available_case_ids() -> tuple[str, ...]:
    return tuple(_MANIFESTS)


def load_case(case_id: str = "repo_pilot_v0") -> CaseDefinition:
    manifest_name = _MANIFESTS.get(case_id)
    if manifest_name is None:
        raise CaseSelectionError(f"unknown case ID: {case_id}")
    manifest_path = EXPERIMENT_ROOT / "manifests" / manifest_name
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        if raw["repository_id"] != case_id:
            raise CaseSelectionError("manifest repository_id does not match requested case")
        target_root = _under_experiment_root(raw["target_root"])
        private_root = _under_experiment_root(raw["evaluator_private"])
        ground_truth = private_root / str(raw["ground_truth_file"])
        provenance_file = raw.get("provenance_file")
        provenance = private_root / str(provenance_file) if provenance_file else None
        prompt_profile = str(raw["prompt_profile"])
        finding_schema = str(raw["finding_schema"])
        evaluator = str(raw["evaluator"])
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise CaseSelectionError(f"invalid case manifest {manifest_name}: {exc}") from exc
    if not target_root.is_dir() or not private_root.is_dir() or not ground_truth.is_file():
        raise CaseSelectionError("case target or trusted evaluator asset is missing")
    if provenance is not None and not provenance.is_file():
        raise CaseSelectionError("case provenance asset is missing")
    if prompt_profile not in {"repository_pilot_v0", "repository_v1"}:
        raise CaseSelectionError("unsupported prompt profile")
    if finding_schema not in {"repository_pilot_v0", "repository_v1"}:
        raise CaseSelectionError("unsupported finding schema")
    if evaluator not in {"repository_pilot_v0", "repository_v1", "repository_v1_1"}:
        raise CaseSelectionError("unsupported evaluator")
    if evaluator == "repository_v1_1":
        if case_id != "flowise_3_1_3_repository_v1_1" or raw.get("schema_version") != "repository-v1.1-case-manifest":
            raise CaseSelectionError("repository-v1.1 evaluator requires its versioned case manifest")
        from experiments.emergent_coordination.evaluator.repository_v1_1_score import load_ground_truth

        try:
            load_ground_truth(ground_truth)
        except (OSError, ValueError) as exc:
            raise CaseSelectionError(f"invalid repository-v1.1 trusted GT: {exc}") from exc
    return CaseDefinition(
        case_id=case_id,
        manifest_path=manifest_path,
        target_root=target_root,
        evaluator_private_root=private_root,
        ground_truth_path=ground_truth,
        provenance_path=provenance,
        prompt_profile=prompt_profile,
        finding_schema=finding_schema,
        evaluator=evaluator,
        manifest=raw,
    )


def _under_experiment_root(value: object) -> Path:
    root = EXPERIMENT_ROOT.resolve()
    candidate = (EXPERIMENT_ROOT.parents[1] / str(value)).resolve()
    if root not in candidate.parents and candidate != root:
        raise CaseSelectionError("manifest path escapes experiments/emergent_coordination")
    return candidate
