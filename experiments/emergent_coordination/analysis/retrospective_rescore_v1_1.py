"""Read-only historical Flowise v1 -> versioned repository-v1.1 rescore.

Outputs are generated outside run trees. This program never writes to a run,
the frozen GT, evaluator-v1, or an existing retrospective artifact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from experiments.emergent_coordination.evaluator.repository_v1_score import (
    evaluate_findings as evaluate_v1,
    load_ground_truth as load_v1_gt,
)
from experiments.emergent_coordination.evaluator.repository_v1_1_score import (
    CASE_ID,
    EVALUATOR_GENERATION,
    GT_SHA256,
    ROOT_COUNT,
    _fingerprint,
    evaluate_findings,
    load_ground_truth,
)
from experiments.emergent_coordination.harness.paths import REPO_ROOT


RUNS = REPO_ROOT / "experiments/emergent_coordination/runs"
OLD_GT = REPO_ROOT / "experiments/emergent_coordination/evaluator_private/flowise_3_1_3_repository_v1/ground_truth.json"
NEW_GT = REPO_ROOT / "experiments/emergent_coordination/evaluator_private/flowise_3_1_3_repository_v1_1/ground_truth.json"
LEDGER = REPO_ROOT / "artifacts/gt_audit/unmatched_candidate_ledger.json"
VERDICTS = REPO_ROOT / "artifacts/gt_audit/adjudication_consolidated.json"
OUTPUT = REPO_ROOT / "artifacts/retrospective/flowise_repository_v1_1_evaluator_v2_20260921"
OLD_CASE = "flowise_3_1_3_repository_v1"

# The first nine roots were admitted from historical run candidates. This
# mapping is a provenance join, not a scoring shortcut: only evaluator-v2 can
# confer formal canonical/equivalent TP.
NEW_ROOT_SOURCE_CLUSTERS = {
    "UC01": "R21_oauth2_unauth_credential_mutation",
    "UC02": "R22_feedback_unauth_cross_flow_access",
    "UC04": "R23_get_upload_file_unauth_cross_tenant_read",
    "UC08": "R24_dataset_rows_unscoped_delete",
    "UC19": "R25_user_create_zero_permission",
    "UC23": "R26_apikey_raw_secret_exposure",
    "UC27": "R27_documentstore_upsert_zero_permission",
    "UC28": "R28_documentstore_query_unscoped",
    "UC36": "R29_nvidia_nim_zero_permission_routes",
}


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _condition(mode: str) -> str:
    mapping = {"single": "S", "parallel": "P", "raw_blackboard": "B", "structured_team": "T", "manager_worker": "M"}
    if mode not in mapping:
        raise ValueError(f"unknown historical condition: {mode}")
    return mapping[mode]


def _sources(gt: dict[str, Any], ledger: dict[str, Any]) -> tuple[dict[str, list[dict[str, str]]], dict[str, list[str]], dict[str, list[str]]]:
    """Join UC provenance to source runs and approved equivalent anchors."""
    roots = {root["id"]: root for root in gt["roots"]}
    for cluster, root_id in NEW_ROOT_SOURCE_CLUSTERS.items():
        if not roots[root_id].get("provenance", {}).get("agent_run_derived"):
            raise ValueError(f"missing frozen agent_run_derived marker for {cluster}")
    equivalents: dict[str, list[str]] = defaultdict(list)
    cluster_roots: dict[str, list[str]] = defaultdict(list)
    for cluster, root_id in NEW_ROOT_SOURCE_CLUSTERS.items():
        cluster_roots[cluster].append(root_id)
    for root in gt["roots"]:
        for anchor in root.get("equivalent_anchors_v1_1") or []:
            for token in str(anchor.get("adjudication", "")).replace("/", " ").split():
                if token.startswith("UC") and token[2:].isdigit():
                    equivalents[token].append(anchor["id"])
                    if root["id"] not in cluster_roots[token]:
                        cluster_roots[token].append(root["id"])
    by_run: dict[str, list[dict[str, str]]] = defaultdict(list)
    for cluster in ledger["clusters"]:
        uc = cluster["cluster_id"]
        for occurrence in cluster["occurrences"]:
            if uc in NEW_ROOT_SOURCE_CLUSTERS or uc in equivalents:
                by_run[occurrence["run"]].append({
                    "cluster_id": uc,
                    "root_id": NEW_ROOT_SOURCE_CLUSTERS.get(uc, ""),
                    "equivalent_anchor_ids": equivalents.get(uc, []),
                })
    return by_run, equivalents, cluster_roots


def build() -> dict[str, bytes]:
    """Perform complete preflight and return deterministic, not-yet-written files."""
    gt = load_ground_truth(NEW_GT)
    old_gt = load_v1_gt(OLD_GT)
    ledger = _read(LEDGER)
    verdicts = {row["cluster_id"]: row for row in _read(VERDICTS)["verdicts"]}
    if ledger.get("case") != OLD_CASE or ledger.get("unmatched_records_total") != 94:
        raise ValueError("historical unmatched ledger identity/count drift")
    source_runs, equivalents, cluster_roots = _sources(gt, ledger)
    occurrences: dict[str, dict[int, str]] = defaultdict(dict)
    for cluster in ledger["clusters"]:
        uc = cluster["cluster_id"]
        if uc not in verdicts:
            raise ValueError(f"missing condition-blind adjudication: {uc}")
        for row in cluster["occurrences"]:
            index = int(row["finding_index"])
            run = row["run"]
            if index in occurrences[run]:
                raise ValueError(f"finding assigned to multiple clusters: {run}:{index}")
            occurrences[run][index] = uc
    if sum(map(len, occurrences.values())) != 94:
        raise ValueError("historical occurrence join did not preserve 94 findings")

    paths = sorted(RUNS.rglob("run_manifest.json"))
    outputs: dict[str, bytes] = {}
    per_run: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    transition = Counter()
    transition_by_cluster: dict[str, Counter[str]] = defaultdict(Counter)
    condition_scores: dict[str, list[dict[str, Any]]] = defaultdict(list)
    source_overlap: dict[str, dict[str, Any]] = {}
    input_hashes: dict[str, dict[str, str]] = {}
    run_id_paths: dict[str, list[str]] = defaultdict(list)
    old_unmatched_total = 0
    drift_hits = Counter()

    for manifest_path in paths:
        manifest = _read(manifest_path)
        if manifest.get("repository") != OLD_CASE:
            continue
        run_dir = manifest_path.parent
        rel = run_dir.relative_to(RUNS).as_posix()
        files = {name: run_dir / name for name in (
            "run_manifest.json", "merged_findings.json", "evaluation.json", "evaluator_private/verification.json"
        )}
        absent = [name for name, path in files.items() if not path.is_file()]
        if absent:
            if rel in ledger.get("flowise_runs", []) or rel in occurrences:
                raise ValueError(f"ledger source run is incomplete: {rel}: {absent}")
            excluded.append({"run": rel, "reason": "incomplete_original_run", "missing": ", ".join(absent)})
            continue
        run_id = str(manifest.get("run_id", ""))
        if not run_id:
            raise ValueError(f"missing run_id: {rel}")
        # Some distinct historical block directories reused a short run_id.
        # Keep the immutable relative path as the disambiguating identity.
        run_id_paths[run_id].append(rel)
        if manifest.get("evaluator_generation", "repository_v1") != "repository_v1":
            raise ValueError(f"historical run is not evaluator-v1: {rel}")
        findings = _read(files["merged_findings.json"]).get("findings")
        original = _read(files["evaluation.json"])
        original_private = _read(files["evaluator_private/verification.json"])
        if not isinstance(findings, list) or len(original_private.get("per_finding", [])) != len(findings):
            raise ValueError(f"historical findings/verifications misalign: {rel}")
        # Replay evaluator-v1 in memory to prove both original artifacts are
        # authentic to these inputs, without changing either result.
        replay = evaluate_v1(findings, old_gt, invalid_submissions=original.get("invalid_submissions", 0))
        if replay["public"] != original or replay["private"]["per_finding"] != original_private["per_finding"]:
            raise ValueError(f"original evaluator-v1 score cannot be reproduced: {rel}")

        decisions: dict[str, dict[str, Any]] = {}
        for index, uc in sorted(occurrences.get(rel, {}).items()):
            if index >= len(findings) or original_private["per_finding"][index].get("disposition") != "unmatched_review":
                raise ValueError(f"adjudication occurrence is not old unmatched: {rel}:{index}")
            verdict = verdicts[uc]
            status = verdict["final_classification"]
            if status in {"false_positive", "inconclusive", "validated_novel_tp_conditional"}:
                classification = "inconclusive" if status == "validated_novel_tp_conditional" else status
                fingerprint = _fingerprint(findings[index])
                decision = {
                    "classification": classification,
                    "reviewer": "condition-blind 2026-09-21 adjudication",
                    "provenance": f"artifacts/gt_audit/adjudication_consolidated.json#{uc}",
                }
                if fingerprint in decisions and decisions[fingerprint] != decision:
                    raise ValueError(f"conflicting verdicts for one deterministic fingerprint: {rel}:{index}")
                decisions[fingerprint] = decision
            elif status in {"validated_novel_tp", "canonical_tp_overlap"}:
                root_ids = sorted(cluster_roots.get(uc, []))
                if not root_ids:
                    raise ValueError(f"adjudicated positive lacks frozen GT identity: {uc}")
                fingerprint = _fingerprint(findings[index])
                decision = {
                    "classification": "gt_overlap_uncredited",
                    "root_ids": root_ids,
                    "reviewer": "condition-blind 2026-09-21 adjudication",
                    "provenance": f"artifacts/gt_audit/adjudication_consolidated.json#{uc}",
                }
                if fingerprint in decisions and decisions[fingerprint] != decision:
                    raise ValueError(f"conflicting verdicts for one deterministic fingerprint: {rel}:{index}")
                decisions[fingerprint] = decision
            else:
                raise ValueError(f"unhandled adjudication status: {uc}: {status}")
        scored = evaluate_findings(findings, gt, invalid_submissions=original.get("invalid_submissions", 0), adjudications=decisions)
        repeat = evaluate_findings(findings, gt, invalid_submissions=original.get("invalid_submissions", 0), adjudications=decisions)
        if scored != repeat:
            raise ValueError(f"evaluator-v2 non-determinism: {rel}")
        public = scored["public"]
        private = scored["private"]
        canonical = public["canonical_score"]
        novel = public["novel_finding_view"]
        if canonical["root_denominator"] != ROOT_COUNT or canonical["true_positives"] + canonical["false_negatives"] != ROOT_COUNT:
            raise ValueError(f"canonical denominator drift: {rel}")
        if len(private["matched_ground_truth"]) != canonical["true_positives"]:
            raise ValueError(f"root uniqueness drift: {rel}")
        if canonical["canonical_tp"] + canonical["equivalent_tp"] != canonical["true_positives"]:
            raise ValueError(f"match provenance count drift: {rel}")
        own_sources = source_runs.get(rel, [])
        matched_derived_roots = sorted(
            root_id for root_id in private["matched_ground_truth"]
            if next(root for root in gt["roots"] if root["id"] == root_id).get("provenance", {}).get("agent_run_derived")
        )
        discovery_roots = sorted({item["root_id"] for item in own_sources if item["root_id"]})
        discovery_equivalents = sorted({anchor for item in own_sources for anchor in item["equivalent_anchor_ids"]})
        circularity = {
            "present": bool(own_sources or matched_derived_roots),
            "discovery_source": bool(own_sources),
            "discovery_cluster_ids": sorted({item["cluster_id"] for item in own_sources}),
            "discovery_root_ids": discovery_roots,
            "discovery_equivalent_anchor_ids": discovery_equivalents,
            "matched_agent_run_derived_root_ids": matched_derived_roots,
            "independent_generalization_evidence": False,
        }
        source_overlap[rel] = circularity

        per_finding = []
        for index, (prior, current) in enumerate(zip(original_private["per_finding"], private["per_finding"])):
            row = {"index": index, "original_disposition": prior["disposition"], "retrospective_classification": current["classification"]}
            if "root_id" in current:
                row["root_id"] = current["root_id"]
            if "anchor_id" in current:
                row["anchor_id"] = current["anchor_id"]
            if index in occurrences.get(rel, {}):
                row["historical_cluster_id"] = occurrences[rel][index]
            if prior["disposition"] == "unmatched_review":
                old_unmatched_total += 1
                transition[current["classification"]] += 1
                if current["classification"] in {"canonical_tp", "equivalent_tp"} and current.get("root_id") in {
                    "R02_org_user_password_serialization", "R05_generic_variable_resolution",
                    "R07_sso_invited_token_proof", "R08_sso_email_only_identity",
                }:
                    drift_hits[current["root_id"]] += 1
                if "historical_cluster_id" in row:
                    transition_by_cluster[row["historical_cluster_id"]][current["classification"]] += 1
            per_finding.append(row)

        original_recall = original["positive_recall"]
        item = {
            "run_id": run_id,
            "run_path": rel,
            "condition": _condition(str(manifest["mode"])),
            "seed": manifest.get("seed"),
            "original": {
                "evaluator_generation": "repository_v1",
                "true_positives": original_recall["true_positives"],
                "false_negatives": original_recall["false_negatives"],
                "unmatched": original["unmatched_review"]["count"],
                "score_artifact": (files["evaluation.json"].relative_to(REPO_ROOT)).as_posix(),
                "score_artifact_sha256": _sha(files["evaluation.json"]),
                "verification_artifact": (files["evaluator_private/verification.json"].relative_to(REPO_ROOT)).as_posix(),
                "verification_artifact_sha256": _sha(files["evaluator_private/verification.json"]),
            },
            "retrospective": {
                "evaluator_generation": EVALUATOR_GENERATION,
                "ground_truth_sha256": GT_SHA256,
                "root_denominator": ROOT_COUNT,
                "canonical_tp": canonical["canonical_tp"],
                "equivalent_tp": canonical["equivalent_tp"],
                "false_negatives": canonical["false_negatives"],
                "validated_novel_tp": novel["validated_novel_tp"],
                "false_positive": novel["false_positive"],
                "inconclusive": novel["inconclusive"],
                "unmatched_unreviewed": novel["unmatched_unreviewed"],
                "duplicate_findings": canonical["duplicates"],
                "known_gt_overlap_uncredited": canonical["known_gt_overlap_uncredited"],
                "matched_roots": private["matched_ground_truth"],
                "missing_roots": private["missing_ground_truth"],
            },
            "agent_run_derived_gt_overlap": circularity,
            "per_finding_transition": per_finding,
            "input_sha256": {name: _sha(path) for name, path in files.items()},
        }
        artifact_rel = f"runs/{rel}/retrospective.json"
        outputs[artifact_rel] = _json_bytes(item)
        per_run.append({"run_id": run_id, "run_path": rel, "artifact": artifact_rel, "condition": item["condition"], "seed": item["seed"], "original": item["original"], "retrospective": {key: value for key, value in item["retrospective"].items() if key not in {"matched_roots", "missing_roots"}}, "agent_run_derived_gt_overlap": circularity["present"]})
        condition_scores[item["condition"]].append({"run_path": rel, "original_tp": original_recall["true_positives"], "retrospective_tp": canonical["true_positives"], "original_denominator": 20, "retrospective_denominator": ROOT_COUNT})
        input_hashes[rel] = item["input_sha256"]

    if set(ledger["flowise_runs"]) - set(input_hashes):
        raise ValueError("not every ledger run was rescored")
    if old_unmatched_total < 94 or sum(transition.values()) != old_unmatched_total:
        raise ValueError("old unmatched transition count drift")
    summary = {
        "schema_version": "repository-v1.1-retrospective-v2",
        "case_id": CASE_ID,
        "evaluator_generation": EVALUATOR_GENERATION,
        "ground_truth_sha256": GT_SHA256,
        "old_case_id": OLD_CASE,
        "run_count": len(per_run),
        "reused_historical_run_ids": {key: value for key, value in sorted(run_id_paths.items()) if len(value) > 1},
        "excluded_runs": excluded,
        "historical_adjudication_source_runs": ledger["flowise_run_count"],
        "historical_adjudicated_unmatched_findings": 94,
        "old_unmatched_findings_all_rescored_runs": old_unmatched_total,
        "run_index": per_run,
        "condition_descriptives": {key: condition_scores[key] for key in sorted(condition_scores)},
        "interpretation": "Retrospective descriptive adjudication only; no topology ranking or independent generalization claim.",
    }
    matrix = {
        "schema_version": "repository-v1-to-v1.1-transition-matrix",
        "unit": "individual original evaluator-v1 unmatched finding, including duplicate-root administrative outcomes",
        "all_old_unmatched": dict(sorted(transition.items())),
        "historical_adjudication_clusters": {key: dict(sorted(value.items())) for key, value in sorted(transition_by_cluster.items())},
        "anchor_drift": {
            "frozen_repair_roots": ["R02_org_user_password_serialization", "R05_generic_variable_resolution", "R07_sso_invited_token_proof", "R08_sso_email_only_identity"],
            "observed_old_unmatched_to_formal_tp": {root: drift_hits[root] for root in (
                "R02_org_user_password_serialization", "R05_generic_variable_resolution",
                "R07_sso_invited_token_proof", "R08_sso_email_only_identity"
            )},
        },
        "note": "Canonical/equivalent TP require deterministic frozen-anchor constraints; cluster adjudication alone cannot promote an unmatched finding to formal TP.",
    }
    circularity_summary = {
        "schema_version": "repository-v1.1-retrospective-circularity",
        "runs_with_overlap": sum(value["present"] for value in source_overlap.values()),
        "runs_that_contributed_gt_additions": sum(value["discovery_source"] for value in source_overlap.values()),
        "by_run": dict(sorted(source_overlap.items())),
        "rule": "Any retrospective score, especially a GT-discovery source run, is not independent benchmark generalization evidence.",
    }
    outputs["summary.json"] = _json_bytes(summary)
    outputs["transition_matrix.json"] = _json_bytes(matrix)
    outputs["circularity_summary.json"] = _json_bytes(circularity_summary)
    manifest = {
        "schema_version": "repository-v1.1-retrospective-manifest",
        "case_id": CASE_ID,
        "gt_sha256": GT_SHA256,
        "evaluator_v2_source_sha256": _sha(REPO_ROOT / "experiments/emergent_coordination/evaluator/repository_v1_1_score.py"),
        "evaluator_v1_source_sha256": _sha(REPO_ROOT / "experiments/emergent_coordination/evaluator/repository_v1_score.py"),
        "rescore_program_sha256": _sha(Path(__file__)),
        "unmatched_ledger_sha256": _sha(LEDGER),
        "adjudication_ledger_sha256": _sha(VERDICTS),
        "input_sha256": dict(sorted(input_hashes.items())),
        "output_sha256": {name: hashlib.sha256(content).hexdigest() for name, content in sorted(outputs.items())},
        "run_count": len(per_run),
        "root_denominator": ROOT_COUNT,
        "retrospective_only": True,
    }
    outputs["manifest.json"] = _json_bytes(manifest)
    return outputs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("check", "write", "verify"))
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    output = args.output.resolve()
    if output == RUNS or RUNS in output.parents:
        raise SystemExit("refusing to write retrospective files within historical runs")
    files = build()
    if args.action == "check":
        print(f"preflight passed: {len(files) - 4} runs; {len(files)} deterministic output files")
        return
    if args.action == "write":
        if output.exists():
            raise SystemExit("refusing to overwrite existing retrospective artifact")
        output.mkdir(parents=True, exist_ok=False)
        for relative, content in sorted(files.items()):
            destination = output / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
        print(f"wrote {len(files)} files to {output}")
        return
    if not output.is_dir():
        raise SystemExit("retrospective artifact does not exist")
    actual = {path.relative_to(output).as_posix(): path.read_bytes() for path in output.rglob("*") if path.is_file()}
    if actual != files:
        raise SystemExit("retrospective output or historical input drift detected")
    print(f"verified {len(files)} immutable files and all historical input hashes")


if __name__ == "__main__":
    main()
