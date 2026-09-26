#!/usr/bin/env python3
"""Produce post-estimate robustness diagnostics without changing the preregistered estimator."""

from __future__ import annotations

import json

from scripts.sample_hidden_opportunity_density import CASE, OUT, ROOT, json_bytes, load_json, load_jsonl, sha

ACTIONABLE = {"actionable cross-check", "strong dependency"}


def main() -> None:
    estimate = load_json(OUT / "density_estimate.json")
    qc = load_json(OUT / "qc_report.json")
    sample = load_jsonl(OUT / "sampled_pairs.jsonl")
    final = load_jsonl(OUT / "final_sample_labels.jsonl")
    weights = {row["pair_id"]: row["sampling_weight"] for row in sample}
    disputed = set(qc["boundary_disagreement_pair_ids"])
    boundary_negative = sum(row["actionable"] and row["pair_id"] not in disputed and weights[row["pair_id"]]
                            for row in final) / 702
    boundary_positive = sum((row["actionable"] or row["pair_id"] in disputed) * weights[row["pair_id"]]
                            for row in final) / 702
    prior = {}
    for version, path in (
        ("graph-v2", CASE / "graph-v2/edges.jsonl"),
        ("batch-01", CASE / "expansion-edge-batches-v1/batch-01/final_labels.jsonl"),
    ):
        labels = {(x["source_node"], x["target_node"]): x["opportunity_type"] for x in load_jsonl(path)}
        overlap = [x for x in final if (x["source_node"], x["target_node"]) in labels]
        prior[version] = {
            "overlap_count": len(overlap),
            "exact_five_class_match_count": sum(x["opportunity_type"] == labels[(x["source_node"], x["target_node"])] for x in overlap),
            "actionable_binary_match_count": sum(x["actionable"] == (labels[(x["source_node"], x["target_node"])] in ACTIONABLE) for x in overlap),
            "binary_conflicts": [x["pair_id"] for x in overlap if x["actionable"] != (labels[(x["source_node"], x["target_node"])] in ACTIONABLE)],
        }
    old_map = {(x["source_node"], x["target_node"]): x["opportunity_type"] in ACTIONABLE
               for path in (CASE / "graph-v2/edges.jsonl", CASE / "expansion-edge-batches-v1/batch-01/final_labels.jsonl")
               for x in load_jsonl(path)}
    old_replacement = sum(old_map.get((x["source_node"], x["target_node"]), x["actionable"]) * weights[x["pair_id"]]
                          for x in final) / 702
    pa = sum(x in ACTIONABLE for x, count in qc["reviewer_marginals"]["a"].items() for _ in range(count)) / 100
    pb = sum(x in ACTIONABLE for x, count in qc["reviewer_marginals"]["b"].items() for _ in range(count)) / 100
    both_positive = (100*pa + 100*pb - qc["disagreement_types"]["binary_boundary"]) / 2
    expected = pa*pb + (1-pa)*(1-pb)
    report = {
        "status": "post_estimate_robustness_only",
        "primary_estimate_unchanged": estimate["weighted_actionable_density"],
        "raw_binary_positive_agreement": 2*both_positive/(100*pa+100*pb),
        "raw_binary_cohen_kappa": (qc["binary_agreement_rate"]-expected)/(1-expected),
        "boundary_disagreement_pair_count": len(disputed),
        "boundary_disagreement_all_negative_density": boundary_negative,
        "boundary_disagreement_all_positive_density": boundary_positive,
        "boundary_sensitivity_note": "Posthoc sensitivity to the three raw actionable-boundary disputes; adjudicated labels remain the primary estimate.",
        "historical_frozen_label_overlap": prior,
        "historical_overlap_replacement_density_exploratory_only": old_replacement,
        "historical_overlap_note": "Checked only after sample adjudication. Prior frozen labels were excluded from selection, blind bundles, QC gate and primary estimator. This is a cross-round stability diagnostic, not a replacement estimate.",
        "qc_report_sha256": sha((OUT / "qc_report.json").read_bytes()),
        "density_estimate_sha256": sha((OUT / "density_estimate.json").read_bytes()),
    }
    path = OUT / "posthoc_robustness.json"
    data = json_bytes(report)
    if path.exists():
        assert path.read_bytes() == data, "posthoc robustness changed"
    else:
        path.write_bytes(data)
    design_doc = ROOT / "docs/research/flowise-3.1.3-repository-v1-sampled-opportunity-density-design-20260926.md"
    result_doc = ROOT / "docs/research/flowise-3.1.3-repository-v1-sampled-opportunity-density-result-20260926.md"
    freeze = {
        "status": "frozen_sampled_density_interpretation",
        "sample_freeze_sha256": sha((OUT / "sample_freeze.json").read_bytes()),
        "posthoc_robustness_sha256": sha(path.read_bytes()),
        "design_report_sha256": sha(design_doc.read_bytes()),
        "limited_interpretation_report_sha256": sha(result_doc.read_bytes()),
        "scope": "estimated benchmark density only; no exact full graph or architecture utilization",
    }
    freeze_path = OUT / "interpretation_freeze.json"
    freeze_data = json_bytes(freeze)
    if freeze_path.exists():
        assert freeze_path.read_bytes() == freeze_data, "interpretation freeze changed"
    else:
        freeze_path.write_bytes(freeze_data)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
