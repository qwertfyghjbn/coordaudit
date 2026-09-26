#!/usr/bin/env python3
"""Gate blind sampled reviews and compute a stratified opportunity estimate."""

from __future__ import annotations

import argparse
import collections
import json
import math
from pathlib import Path

from experiments.emergent_coordination.harness.cases import load_case
from scripts.hidden_opportunity_graph import ACTIONABLE_TYPES, _validate_edge
from scripts.sample_hidden_opportunity_density import OUT, VERSION, json_bytes, jsonl_bytes, load_json, load_jsonl, sha

TAXONOMY = ("none", "thematic-only", "direct relation", "actionable cross-check", "strong dependency")
REVIEW_KEYS = {"reviewer_id", "source_node", "target_node", "opportunity_type", "mechanisms",
               "source_artifact", "target_claim", "expected_effect", "bounded_check", "evidence",
               "rationale", "confidence", "uncertainty_note"}
PACKET = OUT / "packet"
REVIEWS = OUT / "reviews"
TARGET = "experiments/emergent_coordination/repositories/flowise_3_1_3_repository_v1"


def frozen_inputs() -> tuple[list[dict], dict, dict]:
    from scripts.sample_hidden_opportunity_density import render
    expected = render()
    assert all((OUT / name).read_bytes() == data for name, data in expected.items()), "sample changed"
    sample = load_jsonl(OUT / "sampled_pairs.jsonl")
    prereg = load_json(OUT / "sampling_prereg.json")
    packet = load_json(PACKET / "packet_manifest.json")
    assert packet["sample_manifest_sha256"] == prereg["sample_manifest_sha256"]
    assert all(sha((PACKET / name).read_bytes()) == digest for name, digest in packet["packet_sha256"].items())
    assert len(sample) == 100
    return sample, prereg, packet


def validate_rows(path: Path, sample: list[dict], identity: str) -> dict[tuple[str, str], dict]:
    assert path.is_file() and not path.is_symlink(), f"missing {path}"
    rows = load_jsonl(path)
    expected = {(r["source_node"], r["target_node"]): r for r in sample}
    assert len(rows) == len(expected), f"{path.name}: expected {len(expected)} rows, got {len(rows)}"
    mapped = {}
    target_root = load_case("flowise_3_1_3_repository_v1").target_root
    for index, row in enumerate(rows, 1):
        assert set(row) == REVIEW_KEYS, f"{path.name}:{index}: schema keys"
        pair = (row["source_node"], row["target_node"])
        assert pair in expected and pair not in mapped, f"{path.name}:{index}: unexpected/duplicate pair"
        assert row["reviewer_id"] == identity, f"{path.name}:{index}: reviewer identity"
        assert row["opportunity_type"] in TAXONOMY, f"{path.name}:{index}: category"
        edge = {k: v for k, v in row.items() if k != "reviewer_id"}
        edge.update({"edge_id": expected[pair]["pair_id"], "direction": "source_to_target",
                     "adjudication_status": "proposed", "reviewer_ids": [identity]})
        _validate_edge(edge, f"{path.name}:{index}", target_root,
                       {f"F{i:03d}" for i in range(1, 28)}, VERSION)
        if row["opportunity_type"] not in ACTIONABLE_TYPES:
            assert not row["expected_effect"] and not row["source_artifact"] and not row["target_claim"] and not row["bounded_check"], f"{path.name}:{index}: non-actionable fields"
        mapped[pair] = row
    assert set(mapped) == set(expected), f"{path.name}: missing pairs"
    return mapped


def validate_access(path: Path, identity: str) -> dict:
    assert path.is_file() and not path.is_symlink(), f"missing {path}"
    log = load_json(path)
    assert set(log) == {"reviewer_id", "files_read"} and log["reviewer_id"] == identity
    files = log["files_read"]
    assert isinstance(files, list) and all(isinstance(x, str) for x in files)
    assert len(files) == len(set(files)), f"{path.name}: duplicate files"
    packet_allowed = {str((PACKET / name).relative_to(Path.cwd())) for name in
                      ("reviewer_rubric.json", "reviewer_bundle.json", "review_form_template.jsonl", "packet_manifest.json")}
    own_allowed = {str((REVIEWS / f"reviewer_{identity[-1]}.jsonl").relative_to(Path.cwd())),
                   str(path.relative_to(Path.cwd()))}
    violations = [p for p in files if p not in packet_allowed | own_allowed and not p.startswith(TARGET + "/")]
    assert not violations, f"{path.name}: access violations {violations[:5]}"
    assert packet_allowed <= set(files), f"{path.name}: packet access log incomplete"
    return {"reviewer_id": identity, "declared_file_count": len(files), "scope_violations": violations,
            "access_log_sha256": sha(path.read_bytes())}


def write_once(path: Path, data: bytes) -> None:
    if path.exists():
        assert path.read_bytes() == data, f"frozen artifact differs: {path}"
    else:
        path.write_bytes(data)


def exact_finite_population_interval(N: int, n: int, y: int, tail: float) -> tuple[int, int]:
    """Invert hypergeometric tails for a conservative interval on integer K."""
    denominator = math.comb(N, n)

    def pmf(K: int, x: int) -> float:
        if x < max(0, n-(N-K)) or x > min(n, K):
            return 0.0
        return math.comb(K, x) * math.comb(N-K, n-x) / denominator

    lower = next(K for K in range(N+1) if sum(pmf(K, x) for x in range(y, n+1)) >= tail)
    upper = max(K for K in range(N+1) if sum(pmf(K, x) for x in range(y+1)) >= tail)
    return lower, upper


def check() -> dict:
    sample, prereg, packet = frozen_inputs()
    a_path, b_path = REVIEWS / "reviewer_a.jsonl", REVIEWS / "reviewer_b.jsonl"
    if not a_path.exists() or not b_path.exists():
        return {"status": "pending_independent_reviews", "reviewer_a_exists": a_path.exists(), "reviewer_b_exists": b_path.exists()}
    a = validate_rows(a_path, sample, "sampled-density-reviewer-a")
    b = validate_rows(b_path, sample, "sampled-density-reviewer-b")
    accesses = [validate_access(REVIEWS / f"reviewer_{side}_access.json", f"sampled-density-reviewer-{side}") for side in "ab"]
    ordered = [(r["source_node"], r["target_node"]) for r in sample]
    binary = sum((a[p]["opportunity_type"] in ACTIONABLE_TYPES) == (b[p]["opportunity_type"] in ACTIONABLE_TYPES) for p in ordered)
    exact = sum(a[p]["opportunity_type"] == b[p]["opportunity_type"] for p in ordered)
    threshold = math.ceil(0.9 * len(sample))
    disagreements = [p for p in ordered if a[p]["opportunity_type"] != b[p]["opportunity_type"]]
    boundary = [p for p in ordered if (a[p]["opportunity_type"] in ACTIONABLE_TYPES) != (b[p]["opportunity_type"] in ACTIONABLE_TYPES)]
    uncertain = [p for p in ordered if a[p]["uncertainty_note"] or b[p]["uncertainty_note"]]
    needed = [p for p in ordered if p in set(disagreements) | set(uncertain)]
    confusion = {x: {y: sum(a[p]["opportunity_type"] == x and b[p]["opportunity_type"] == y for p in ordered)
                     for y in TAXONOMY} for x in TAXONOMY}
    qc = {
        "status": "pending_disagreement_only_adjudication" if binary >= threshold and needed else
                  "ready_to_estimate" if binary >= threshold else "taxonomy_reliability_failure_stop",
        "sample_size": len(sample), "binary_agreement_count": binary, "binary_agreement_rate": binary / len(sample),
        "binary_threshold_count": threshold, "binary_threshold_met": binary >= threshold,
        "exact_five_class_agreement_count": exact, "exact_five_class_agreement_rate": exact / len(sample),
        "five_class_confusion_rows_a_cols_b": confusion,
        "reviewer_marginals": {side: dict(collections.Counter(rows[p]["opportunity_type"] for p in ordered)) for side, rows in (("a", a), ("b", b))},
        "disagreement_types": {
            "binary_boundary": len(boundary),
            "same_binary_different_five_class": len(disagreements) - len(boundary),
            "actionable_subtype": sum(a[p]["opportunity_type"] in ACTIONABLE_TYPES and b[p]["opportunity_type"] in ACTIONABLE_TYPES and a[p]["opportunity_type"] != b[p]["opportunity_type"] for p in ordered),
            "non_actionable_subtype": sum(a[p]["opportunity_type"] not in ACTIONABLE_TYPES and b[p]["opportunity_type"] not in ACTIONABLE_TYPES and a[p]["opportunity_type"] != b[p]["opportunity_type"] for p in ordered),
            "uncertain_boundary_notes": len(uncertain),
        },
        "disagreement_pair_ids": [next(r["pair_id"] for r in sample if (r["source_node"], r["target_node"]) == p) for p in disagreements],
        "boundary_disagreement_pair_ids": [next(r["pair_id"] for r in sample if (r["source_node"], r["target_node"]) == p) for p in boundary],
        "review_sha256": {"a": sha(a_path.read_bytes()), "b": sha(b_path.read_bytes())},
        "access_logs": accesses,
        "packet_manifest_sha256": sha((PACKET / "packet_manifest.json").read_bytes()),
        "sample_manifest_sha256": prereg["sample_manifest_sha256"],
        "access_log_limit": "Reviewer file access is self-reported; this QC verifies declared scope and evidence in frozen target, not OS-level file-open telemetry.",
    }
    write_once(OUT / "qc_report.json", json_bytes(qc))
    if binary >= threshold and needed:
        by_pair = {(r["source_node"], r["target_node"]): r for r in sample}
        adj = {
            "status": "disagreement_only_input",
            "qc_report_sha256": sha((OUT / "qc_report.json").read_bytes()),
            "packet_manifest_sha256": qc["packet_manifest_sha256"],
            "pairs": [{"sample": by_pair[p], "reviewer_a": a[p], "reviewer_b": b[p]} for p in needed],
        }
        write_once(OUT / "adjudication_input.json", json_bytes(adj))
    return qc


def estimate() -> dict:
    qc = check()
    assert qc["binary_threshold_met"], "primary QC failed: no estimate permitted"
    sample = load_jsonl(OUT / "sampled_pairs.jsonl")
    a = validate_rows(REVIEWS / "reviewer_a.jsonl", sample, "sampled-density-reviewer-a")
    b = validate_rows(REVIEWS / "reviewer_b.jsonl", sample, "sampled-density-reviewer-b")
    adj_path = OUT / "reviews/adjudicator.jsonl"
    adj = {}
    if (OUT / "adjudication_input.json").exists():
        input_pairs = {(x["sample"]["source_node"], x["sample"]["target_node"]) for x in load_json(OUT / "adjudication_input.json")["pairs"]}
        assert adj_path.exists(), "adjudication pending"
        rows = load_jsonl(adj_path)
        assert len(rows) == len(input_pairs)
        for row in rows:
            p = (row["source_node"], row["target_node"])
            assert p in input_pairs and p not in adj and row["opportunity_type"] in TAXONOMY
            assert set(row) == (REVIEW_KEYS - {"reviewer_id"}) | {"adjudicator_id"}
            assert row["adjudicator_id"] == "sampled-density-adjudicator"
            edge = {k: v for k, v in row.items() if k != "adjudicator_id"}
            edge.update({"edge_id": f"{VERSION}:{p[0]}:{p[1]}", "direction": "source_to_target",
                         "adjudication_status": "proposed", "reviewer_ids": [row["adjudicator_id"]]})
            _validate_edge(edge, f"adjudicator.jsonl:{len(adj)+1}",
                           load_case("flowise_3_1_3_repository_v1").target_root,
                           {f"F{i:03d}" for i in range(1, 28)}, VERSION)
            if row["opportunity_type"] not in ACTIONABLE_TYPES:
                assert not row["expected_effect"] and not row["source_artifact"] and not row["target_claim"] and not row["bounded_check"]
            adj[p] = row
        assert set(adj) == input_pairs
        access_path = REVIEWS / "adjudicator_access.json"
        assert access_path.is_file(), "missing adjudicator access log"
        access = load_json(access_path)
        assert set(access) == {"reviewer_id", "files_read"} and access["reviewer_id"] == "sampled-density-adjudicator"
        allowed = {str((PACKET / name).relative_to(Path.cwd())) for name in
                   ("reviewer_rubric.json", "reviewer_bundle.json", "review_form_template.jsonl", "packet_manifest.json")}
        allowed |= {str((OUT / "adjudication_input.json").relative_to(Path.cwd())),
                    str(adj_path.relative_to(Path.cwd())), str(access_path.relative_to(Path.cwd()))}
        assert all(p in allowed or p.startswith(TARGET + "/") for p in access["files_read"]), "adjudicator access scope violation"
        assert str((OUT / "adjudication_input.json").relative_to(Path.cwd())) in access["files_read"]
    final = []
    for r in sample:
        p = (r["source_node"], r["target_node"])
        chosen = adj.get(p, a[p])
        assert p in adj or a[p]["opportunity_type"] == b[p]["opportunity_type"] and not a[p]["uncertainty_note"] and not b[p]["uncertainty_note"]
        final.append({"pair_id": r["pair_id"], "source_node": p[0], "target_node": p[1],
                      "stratum": r["stratum"], "opportunity_type": chosen["opportunity_type"],
                      "actionable": chosen["opportunity_type"] in ACTIONABLE_TYPES,
                      "uncertain": bool(chosen["uncertainty_note"]),
                      "label_origin": "adjudicated" if p in adj else "raw_agreement"})
    write_once(OUT / "final_sample_labels.jsonl", jsonl_bytes(final))
    strata = {}
    estimate_value = variance = lower = upper = 0.0
    exact_count_lower = exact_count_upper = 0
    for name in ("old_to_old", "old_to_new", "new_to_old", "new_to_new"):
        subset = [x for x in final if x["stratum"] == name]
        original = [x for x in sample if x["stratum"] == name]
        N, n = original[0]["stratum_population"], len(subset)
        y = sum(x["actionable"] for x in subset)
        u = sum(x["uncertain"] for x in subset)
        p = y / n
        W = N / 702
        var_h = W * W * (1 - n / N) * (p * (1-p) / (n-1))
        estimate_value += W*p
        variance += var_h
        lower += W*(y - sum(x["actionable"] and x["uncertain"] for x in subset))/n
        upper += W*(y + sum(not x["actionable"] and x["uncertain"] for x in subset))/n
        strata[name] = {"population": N, "sample": n, "actionable_count": y, "uncertain_count": u,
                        "density": p, "population_weight": W, "sampling_weight": N/n,
                        "estimated_actionable_count": N*p}
        kl, ku = exact_finite_population_interval(N, n, y, 0.05 / (2*4))
        exact_count_lower += kl
        exact_count_upper += ku
        strata[name]["exact_finite_population_98_75_count_interval"] = [kl, ku]
    se = math.sqrt(variance)
    result = {
        "status": "sampled_density_estimate", "not_exact_full_graph_density": True,
        "sampled_actionable_count": sum(x["actionable"] for x in final),
        "raw_numerator": sum(x["actionable"] for x in final), "raw_denominator": len(final),
        "raw_unweighted_fraction_descriptive_only": sum(x["actionable"] for x in final)/len(final),
        "weighted_actionable_density": estimate_value,
        "design_based_standard_error": se,
        "design_based_normal_95_interval": [max(0.0, estimate_value-1.96*se), min(1.0, estimate_value+1.96*se)],
        "interval_caveat": "Finite-population stratified normal approximation; sparse positives can make coverage imperfect.",
        "conservative_simultaneous_hypergeometric_95_density_interval": [exact_count_lower/702, exact_count_upper/702],
        "conservative_simultaneous_hypergeometric_95_count_interval": [exact_count_lower, exact_count_upper],
        "exact_interval_method": "Invert each stratum's finite-population hypergeometric tails at 0.05/(2*4), then sum integer success-count bounds; Bonferroni gives at least 95% simultaneous coverage, often wide.",
        "estimated_benchmark_actionable_pair_count": 702*estimate_value,
        "estimated_count_95_interval": [702*max(0.0, estimate_value-1.96*se), 702*min(1.0, estimate_value+1.96*se)],
        "uncertain_pair_count": sum(x["uncertain"] for x in final),
        "uncertainty_sensitivity_density_bounds": [lower, upper],
        "uncertainty_sensitivity_count_bounds": [702*lower, 702*upper],
        "strata": strata,
        "qc_report_sha256": sha((OUT / "qc_report.json").read_bytes()),
        "final_sample_labels_sha256": sha((OUT / "final_sample_labels.jsonl").read_bytes()),
    }
    write_once(OUT / "density_estimate.json", json_bytes(result))
    frozen_names = [
        "sampling_prereg.json", "sampled_pairs.jsonl", "smoke_qc.json", "packet/packet_manifest.json",
        "packet/reviewer_rubric.json", "packet/reviewer_bundle.json", "packet/review_form_template.jsonl",
        "reviews/reviewer_a.jsonl", "reviews/reviewer_b.jsonl", "reviews/reviewer_a_access.json",
        "reviews/reviewer_b_access.json", "qc_report.json", "final_sample_labels.jsonl", "density_estimate.json",
    ]
    if adj_path.exists():
        frozen_names.extend(("adjudication_input.json", "reviews/adjudicator.jsonl", "reviews/adjudicator_access.json"))
    freeze = {
        "status": "frozen_sampled_estimate", "version": VERSION,
        "input_hashes": {name: sha((OUT / name).read_bytes()) for name in frozen_names},
        "adjudication_sha256": sha(adj_path.read_bytes()) if adj_path.exists() else None,
        "adjudicator_access_sha256": sha((REVIEWS / "adjudicator_access.json").read_bytes()) if adj_path.exists() else None,
    }
    write_once(OUT / "sample_freeze.json", json_bytes(freeze))
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=("check", "estimate"))
    args = ap.parse_args()
    print(json.dumps(check() if args.command == "check" else estimate(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
