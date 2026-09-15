from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
EXPERIMENT_ROOT = PROJECT_ROOT / "experiments" / "emergent_coordination"
REPO_ROOT = PROJECT_ROOT
TARGET_ROOT = EXPERIMENT_ROOT / "repositories" / "repository_pilot_v0"
EVALUATOR_PRIVATE = EXPERIMENT_ROOT / "evaluator_private" / "repository_pilot_v0"
GROUND_TRUTH_PATH = EVALUATOR_PRIVATE / "ground_truth.json"
PROVENANCE_PATH = EVALUATOR_PRIVATE / "provenance.json"
MANIFEST_PATH = EXPERIMENT_ROOT / "manifests" / "repository_pilot_v0.json"
DEFAULT_RUNS_DIR = EXPERIMENT_ROOT / "runs"


def agent_id_for(index: int) -> str:
    if index < 1:
        raise ValueError("agent index is 1-based")
    return f"agent_{index:03d}"
