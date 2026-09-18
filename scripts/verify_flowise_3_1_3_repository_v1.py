#!/usr/bin/env python3
"""Fail-closed integrity verifier for the Flowise repository-v1 candidate.

It is control-plane-only: it reads the case target and evaluator-private
assets, emits aggregate verification facts, and never starts an Agent.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.emergent_coordination.harness.block_runner import tree_digest
from experiments.emergent_coordination.harness.cases import load_case
from experiments.emergent_coordination.harness.prompts import base_prompt
from experiments.emergent_coordination.harness.tools.specs import tools_for_mode


CASE_ID = "flowise_3_1_3_repository_v1"
_MODES = ("single", "parallel", "raw_blackboard", "structured_team", "manager_worker")


def _tool_surface(finding_schema: str) -> dict[str, Any]:
    """Canonical per-mode tool surface for the case digest.

    manager_worker exposes role-restricted surfaces (tools_for_mode requires
    an explicit role for it), so its canonical entry carries both the
    manager and the worker surface; any change on either side is visible in
    the digest.
    """
    surface: dict[str, Any] = {
        mode: tools_for_mode(mode, finding_schema)
        for mode in _MODES
        if mode != "manager_worker"
    }
    surface["manager_worker"] = {
        role: tools_for_mode("manager_worker", finding_schema, role=role)
        for role in ("manager", "worker")
    }
    return surface
_LEAK_NEEDLES = (
    "ghsa-",
    "cve-",
    "ground_truth",
    "evaluator_private",
    "09f099dbfda179e439ec677d06ad737375899eef",
    "a65f81bb43ef66d3ce734bf0dff4223ae8041c95",
    CASE_ID,
    "/home/lqs/coordaudit",
    "provenance",
)


class VerificationError(RuntimeError):
    pass


def verify() -> dict[str, Any]:
    case = load_case(CASE_ID)
    private = case.evaluator_private_root
    manifest_digests = case.manifest["digests"]
    common, schema = base_prompt(case.prompt_profile)
    canonical = lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    actual_digests = {
        "target_tree_sha256": tree_digest(case.target_root),
        "evaluator_private_tree_sha256": tree_digest(private),
        "base_prompt_sha256": hashlib.sha256((common + "\n" + schema).encode()).hexdigest(),
        "finding_schema_sha256": hashlib.sha256(
            Path("experiments/emergent_coordination/harness/repository_v1_findings.py").read_bytes()
        ).hexdigest(),
        "tool_surface_sha256": hashlib.sha256(canonical(_tool_surface(case.finding_schema)).encode()).hexdigest(),
    }
    _require(actual_digests == manifest_digests, "manifest digest mismatch")
    _require(not (case.target_root / ".git").exists(), "target contains .git")
    _require(not _target_leak_hits(case.target_root), "target leakage scan failed")

    census = _read_json(private / "census.json")
    ground_truth = _read_json(case.ground_truth_path)
    inventory = _read_json(private / "advisory_inventory.json")
    known_unscored = _read_json(private / "known_unscored.json")
    unresolved = _read_json(private / "unresolved.json")
    qualification = _read_json(private / "near_miss_qualification.json")

    roots = census["scored_roots"]
    gt_roots = ground_truth["roots"]
    counts = census["counts"]
    _require(len(inventory["inventory"]) == 21, "advisory inventory count is not 21")
    _require(all("in_review" not in str(entry.get("disposition", "")) for entry in inventory["inventory"]), "advisory remains in review")
    _require(len(roots) == counts["scored_roots"] == 20, "scored root count mismatch")
    _require(sum(root["class"] == "A" for root in roots) == counts["static_primary_A"] == 15, "A count mismatch")
    _require(sum(root["class"] == "B" for root in roots) == counts["static_plus_targeted_B"] == 5, "B count mismatch")
    _require(len(known_unscored["entries"]) == counts["known_unscored_C"] == 2, "C count mismatch")
    _require(len(unresolved["entries"]) == counts["unresolved"] == 2, "unresolved count mismatch")
    _require(sum("scope_excluded" in entry["disposition"] for entry in inventory["inventory"]) == counts["scope_excluded"] == 1, "scope exclusion count mismatch")
    _require({root["id"] for root in roots} == {root["id"] for root in gt_roots}, "census/ground-truth root IDs differ")
    _require(len(gt_roots) == 20, "ground truth root count mismatch")
    _require(len(ground_truth["near_misses"]) == 5, "near-miss count mismatch")
    _require(len(qualification["decisions"]) == 20, "near-miss qualification count mismatch")
    _require(sum(item["status"] == "qualified" for item in qualification["decisions"]) == 7, "qualified near-miss root count mismatch")
    _require(sum(item["status"] == "excluded" for item in qualification["decisions"]) == 13, "excluded near-miss root count mismatch")
    _require(not _contains_tbd(gt_roots), "scored ground truth contains TBD")

    for root in gt_roots:
        _require(root["anchors"], f"{root['id']} has no primary anchor")
        for anchor in [*root["anchors"], *(item["anchor"] for item in root.get("variants", []))]:
            source = case.target_root / anchor["file"]
            _require(source.is_file(), f"anchor file missing for {root['id']}")
            _require(anchor["excerpt"] in source.read_text(encoding="utf-8"), f"anchor excerpt missing for {root['id']}")
            _require(
                hashlib.sha256(anchor["excerpt"].encode()).hexdigest() == anchor["excerpt_sha256"],
                f"anchor excerpt hash mismatch for {root['id']}",
            )

    dep = _read_json(private / "dependency_materialization.json")
    _require(
        dep["target_binding"]["target_tree_sha256"] == manifest_digests["target_tree_sha256"],
        "dependency environment is not bound to the frozen target tree",
    )
    _require(
        hashlib.sha256((case.target_root / "pnpm-lock.yaml").read_bytes()).hexdigest()
        == dep["target_binding"]["pnpm_lockfile"]["sha256"],
        "dependency environment is bound to a different lockfile",
    )
    env_root = ROOT / dep["environment_root"]
    if env_root.is_dir():
        _require(
            _dependency_tree_digest(env_root / "workspace" / "node_modules") == dep["node_modules_tree_sha256"],
            "materialized node_modules digest mismatch",
        )
        _require(
            _dependency_tree_digest(env_root / "node-runtime") == dep["node_runtime"]["runtime_tree_sha256"],
            "materialized node runtime digest mismatch",
        )
        _require(
            _dependency_tree_digest(env_root / "pnpm") == dep["pnpm"]["toolchain_tree_sha256"],
            "materialized pnpm toolchain digest mismatch",
        )
        dependency_environment = "verified"
    else:
        dependency_environment = "not_materialized"

    result = {
        "case_id": CASE_ID,
        "status": "passed",
        "target_tree_sha256": actual_digests["target_tree_sha256"],
        "evaluator_private_tree_sha256": actual_digests["evaluator_private_tree_sha256"],
        "dependency_environment": dependency_environment,
        "counts": {
            "advisory_manifestations": 21,
            "scored_roots": 20,
            "A": 15,
            "B": 5,
            "C_known_unscored": 2,
            "scope_excluded": 1,
            "unresolved": 2,
            "known_near_misses": 5,
        },
        "leakage_scan": "passed",
        "live_gate": case.manifest["live_gate"],
    }
    result["verification_result_sha256"] = hashlib.sha256(canonical(result).encode()).hexdigest()
    return result


def _dependency_tree_digest(root: Path) -> str:
    """Content digest over regular files only, never following symlinks.

    Mirrors the materializer's digest so pnpm's .pnpm virtual-store links
    never affect the result.  Must stay in sync with
    scripts/materialize_flowise_3_1_3_repository_v1_dependency_env.py.
    """
    import os

    digest = hashlib.sha256()
    base = str(root)
    for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
        dirnames.sort()
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            if os.path.islink(full) or not os.path.isfile(full):
                continue
            relative = os.path.normpath(os.path.relpath(full, base))
            digest.update(relative.encode("utf-8"))
            digest.update(b"\0")
            file_digest = hashlib.sha256()
            with open(full, "rb") as handle:
                for chunk in iter(lambda: handle.read(1 << 20), b""):
                    file_digest.update(chunk)
            digest.update(file_digest.digest())
    return digest.hexdigest()


def _target_leak_hits(target: Path) -> list[str]:
    hits: list[str] = []
    for path in target.rglob("*"):
        if path.is_file():
            content = path.read_text(encoding="utf-8", errors="ignore").lower()
            hits.extend(f"{path.relative_to(target)}:{needle}" for needle in _LEAK_NEEDLES if needle in content)
    return hits


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _contains_tbd(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_contains_tbd(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_tbd(item) for item in value)
    return isinstance(value, str) and "tbd" in value.lower()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


if __name__ == "__main__":
    try:
        print(json.dumps(verify(), ensure_ascii=False, sort_keys=True))
    except VerificationError as exc:
        print(json.dumps({"case_id": CASE_ID, "status": "failed", "error": str(exc)}, ensure_ascii=False))
        raise SystemExit(1)
