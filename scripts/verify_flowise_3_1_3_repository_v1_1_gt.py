#!/usr/bin/env python3
"""Read-only GT content and case-identity validation for repository-v1.1."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "experiments/emergent_coordination/repositories/flowise_3_1_3_repository_v1"
V1 = ROOT / "experiments/emergent_coordination/evaluator_private/flowise_3_1_3_repository_v1/ground_truth.json"
V11 = ROOT / "experiments/emergent_coordination/evaluator_private/flowise_3_1_3_repository_v1_1/ground_truth.json"
MANIFEST = ROOT / "experiments/emergent_coordination/manifests/flowise_3_1_3_repository_v1_1.json"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(bytes.fromhex(sha(path.read_bytes())))
    return digest.hexdigest()


def function_present(source: str, name: str) -> bool:
    if name.startswith("router"):
        return "router." in source
    symbol = name.split(".")[-1].split(" ")[0].split("(")[0]
    if symbol in {"router", ""}:
        return "router." in source
    token = re.escape(symbol)
    return bool(re.search(r"\b" + token + r"\s*(?:\(|=\s*(?:async\s*)?\()", source))


def main() -> None:
    gt = json.loads(V11.read_text())
    v1 = json.loads(V1.read_text())
    manifest = json.loads(MANIFEST.read_text())
    failures: list[str] = []
    checks = 0

    def require(condition: bool, message: str) -> None:
        nonlocal checks
        checks += 1
        if not condition:
            failures.append(message)

    require(gt["schema_version"] == "repository-v1.1-ground-truth", "GT schema")
    require(gt["case_id"] == manifest["repository_id"] == "flowise_3_1_3_repository_v1_1", "case identity")
    require(manifest["schema_version"] == "repository-v1.1-case-manifest", "manifest schema")
    require(manifest["live_gate"] == "blocked", "live gate must remain blocked")
    require(manifest["activation_status"].endswith("runtime_case_unregistered"), "runtime activation boundary")
    require(len(gt["roots"]) == gt["counts"]["roots_total"] == manifest["gt_lineage"]["root_denominator"] == 30, "root denominator")
    require(len({root["id"] for root in gt["roots"]}) == 30, "unique root IDs")
    require(len({anchor["id"] for root in gt["roots"] for anchor in root.get("equivalent_anchors_v1_1", [])}) == gt["counts"]["equivalent_anchor_expansions"], "unique equivalent anchors")
    require(gt["counts"]["roots_v1"] == 20 and gt["counts"]["roots_new_v1_1"] == 10, "old/new root counts")
    require(gt["counts"]["new_roots_agent_run_derived"] == 9 and gt["counts"]["new_roots_public_issue_derived"] == 1, "new root provenance counts")
    require(sha(V1.read_bytes()) == gt["provenance"]["v1_gt_sha256"] == manifest["gt_lineage"]["v1_gt_sha256"], "v1 GT lineage hash")

    for old, current in zip(v1["roots"], gt["roots"][:20]):
        for field, value in old.items():
            require(current.get(field) == value, f"old root modified: {old['id']}.{field}")
    require([root["id"] for root in gt["roots"][:20]] == [root["id"] for root in v1["roots"]], "old root order")

    for root in gt["roots"]:
        rid = root["id"]
        require(bool(root["anchors"]), f"{rid}: missing canonical anchor")
        require(bool(root["threat_model_inclusion_basis"]), f"{rid}: missing inclusion basis")
        if rid.startswith("R2") and rid not in {"R20_tts_private_flow_credential_use"} or rid.startswith("R30"):
            require(all(root.get(field) for field in ("semantic_invariant", "snapshot_applicability", "chain", "public_provenance", "provenance")), f"{rid}: missing new-root evidence")
            require(all(root["chain"].get(field) for field in ("source", "sink", "missing_guard", "preconditions", "expected_impact")), f"{rid}: incomplete chain")
        for anchor in root["anchors"]:
            path = TARGET / anchor["file"]
            require(path.is_file(), f"{rid}: missing canonical file {anchor['file']}")
            if path.is_file():
                source = path.read_text(encoding="utf-8")
                require(anchor["excerpt"] in source, f"{rid}: missing canonical excerpt")
                if anchor.get("excerpt_sha256"):
                    require(sha(anchor["excerpt"].encode()) == anchor["excerpt_sha256"], f"{rid}: excerpt hash")
                # Legacy function-label drift remains byte-for-byte in v1 fields;
                # v1.1 records accepted repair anchors separately.
                if rid not in {"R02_org_user_password_serialization", "R05_openai_assistant_credential_lookup_scope", "R07_sso_invited_token_proof", "R08_sso_email_only_identity"}:
                    require(function_present(source, anchor["function"]), f"{rid}: missing canonical function {anchor['function']}")
        if rid in {"R02_org_user_password_serialization", "R05_openai_assistant_credential_lookup_scope"}:
            require(bool(root.get("accepted_primary_anchors_v1_1")), f"{rid}: missing legacy repair anchors")
            for repair in root.get("accepted_primary_anchors_v1_1", []):
                repair_file = TARGET / repair["file"]
                require(repair_file.is_file(), f"{rid}: missing repair file")
                if repair_file.is_file():
                    repair_source = repair_file.read_text(encoding="utf-8")
                    require(repair["excerpt"] in repair_source and function_present(repair_source, repair["function"]), f"{rid}: invalid repair anchor")
        equivalents = root.get("equivalent_anchors_v1_1", [])
        require([item["id"] for item in equivalents] == root["accepted_equivalent_realizations_v1_1"], f"{rid}: accepted realization set")
        if equivalents:
            require(bool(root.get("semantic_invariant_v1_1")), f"{rid}: missing versioned invariant")
        for anchor in equivalents:
            path = TARGET / anchor["file"]
            require(path.is_file(), f"{rid}/{anchor['id']}: missing file")
            if path.is_file():
                source = path.read_text(encoding="utf-8")
                require(anchor["excerpt"] in source, f"{rid}/{anchor['id']}: missing excerpt")
                require(function_present(source, anchor["function"]), f"{rid}/{anchor['id']}: missing function")
            require(anchor.get("invariant_match_evidence") == root.get("semantic_invariant_v1_1"), f"{rid}/{anchor['id']}: invariant binding")

    require(sum(bool(r["provenance"]["agent_run_derived"]) for r in gt["roots"][20:]) == 9, "circularity flags")
    require(next(r for r in gt["roots"] if r["id"].startswith("R30"))["provenance"]["agent_run_derived"] is False, "UC41 source flag")
    registry = {entry["adjudication"]: entry for entry in gt["known_unscored_registry_v1_1"]}
    require(registry["UC26"]["class"] == "excluded_under_TM6", "UC26 TM6 disposition")
    require(registry["UC41"]["class"] == "resolved_to_R30", "UC41 disposition")
    require(tree_digest(TARGET) == gt["target_tree_sha256"] == manifest["digests"]["target_tree_sha256"], "target tree digest")
    require(tree_digest(V11.parent) == manifest["digests"]["evaluator_private_tree_sha256"], "private tree digest")
    require(manifest["target_root"] == "experiments/emergent_coordination/repositories/flowise_3_1_3_repository_v1", "same target root")
    require(manifest["prompt_profile"] == manifest["finding_schema"] == "repository_v1", "same prompt/schema profile")
    require(manifest["permissions"]["evaluator_private"] is False, "private GT isolation")

    git_status = subprocess.run(["git", "status", "--porcelain", "--untracked-files=normal"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    print(json.dumps({
        "validation": "passed" if not failures else "failed",
        "checks": checks,
        "failures": failures,
        "root_denominator": 30,
        "gt_sha256": sha(V11.read_bytes()),
        "manifest_sha256": sha(MANIFEST.read_bytes()),
        "target_tree_sha256": tree_digest(TARGET),
        "private_tree_sha256": tree_digest(V11.parent),
        "git_clean": not bool(git_status),
        "git_status_entry_count": len(git_status.splitlines()),
        "gt_freeze_complete": not failures and not git_status and gt["freeze_status"] == "frozen",
    }, ensure_ascii=False, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
