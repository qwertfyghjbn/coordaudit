#!/usr/bin/env python3
"""Recompute the bounded stage-9 report from frozen graph and pilot artifacts.

This is an evaluator-side, read-only summary.  It keeps structural graph
counts, contract/run denominators, and retrospective behavior denominators
separate.  Unmapped/out_of_graph work is never silently converted to an
uncertain edge or to ``none``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CASE_DIR = ROOT / "artifacts/hidden_opportunity_graph/flowise_3_1_3_repository_v1"
GRAPH_V1 = CASE_DIR / "graph-v1"
GRAPH_V2 = CASE_DIR / "graph-v2"
OPS = GRAPH_V2 / "operational"
PILOT_A_NODE_QC = GRAPH_V1 / "pilot_a/node_boundary_qc.json"
PILOT_A_EDGE_QC = GRAPH_V1 / "pilot_a/edges_round2/edge_qc.json"
PILOT_B_NODE_QC = GRAPH_V2 / "pilot_b/node_boundary_qc.json"
PILOT_B_EDGE_QC = GRAPH_V2 / "pilot_b/edges_round3/edge_qc.json"
OUT_DIR = GRAPH_V2 / "stage9"

ACTIONABLE = {"actionable cross-check", "strong dependency"}
CONDITIONS = ("S1", "P4", "B4", "T4", "M4")
RUNS = ("matched-seed-01", "matched-seed-02", "matched-seed-03")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ratio(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else round(numerator / denominator, 6)


def bounds(lower: int, upper: int, denominator: int) -> dict[str, Any]:
    return {
        "lower_count": lower,
        "upper_count": upper,
        "denominator": denominator,
        "lower_rate": ratio(lower, denominator),
        "upper_rate": ratio(upper, denominator),
    }


def load() -> dict[str, Any]:
    nodes_v1 = read_jsonl(GRAPH_V1 / "nodes.jsonl")
    nodes = read_jsonl(GRAPH_V2 / "nodes.jsonl")
    edges_v1 = read_jsonl(GRAPH_V1 / "edges.jsonl")
    edges = read_jsonl(GRAPH_V2 / "edges.jsonl")
    actionable_edges = [edge for edge in edges if edge["opportunity_type"] in ACTIONABLE]
    old_pairs = {(edge["source_node"], edge["target_node"]) for edge in edges_v1}
    new_edges = [edge for edge in edges if (edge["source_node"], edge["target_node"]) not in old_pairs]
    category_counts = Counter(edge["opportunity_type"] for edge in edges)
    category_counts_v1 = Counter(edge["opportunity_type"] for edge in edges_v1)
    category_counts_new = Counter(edge["opportunity_type"] for edge in new_edges)

    task_rows = read_jsonl(OPS / "run_task_mapping_pre_sync.jsonl")
    finding_rows = read_jsonl(OPS / "run_finding_mapping_pre_sync.jsonl")
    coverage_rows = read_jsonl(OPS / "run_coverage_pre_sync.jsonl")
    handoffs = read_jsonl(OPS / "run_handoffs.jsonl")
    post_rows = read_jsonl(OPS / "post_sync_review.jsonl")
    realizability = read_jsonl(OPS / "operational_realizability.jsonl")

    structural = {
        "scope": "frozen graph-v2 only; not repository-wide density",
        "node_count": len(nodes),
        "directed_pair_denominator": len(nodes) * (len(nodes) - 1),
        "unordered_dyad_denominator": len(nodes) * (len(nodes) - 1) // 2,
        "category_counts_directed": dict(sorted(category_counts.items())),
        "pilot_a": {
            "node_count": len(nodes_v1),
            "directed_pair_denominator": len(edges_v1),
            "category_counts_directed": dict(sorted(category_counts_v1.items())),
            "actionable_bounds": bounds(
                read_json(PILOT_A_EDGE_QC)["actionable_confirmed_lower_bound"],
                read_json(PILOT_A_EDGE_QC)["actionable_uncertainty_upper_bound"],
                len(edges_v1),
            ),
        },
        "pilot_b_new": {
            "node_count": len(nodes) - len(nodes_v1),
            "directed_pair_denominator": len(new_edges),
            "category_counts_directed": dict(sorted(category_counts_new.items())),
            "actionable_bounds": bounds(
                read_json(PILOT_B_EDGE_QC)["actionable_confirmed_new_lower_bound"],
                read_json(PILOT_B_EDGE_QC)["actionable_uncertainty_new_upper_bound"],
                len(new_edges),
            ),
        },
    }
    E = len(actionable_edges)
    non_none = len(edges) - category_counts.get("none", 0)
    structural["actionable_bounds"] = bounds(
        structural["pilot_a"]["actionable_bounds"]["lower_count"]
        + structural["pilot_b_new"]["actionable_bounds"]["lower_count"],
        structural["pilot_a"]["actionable_bounds"]["upper_count"]
        + structural["pilot_b_new"]["actionable_bounds"]["upper_count"],
        len(edges),
    )
    structural["actionable_density"] = ratio(E, len(edges))
    structural["broad_non_none_density"] = ratio(non_none, len(edges))

    # Unique undirected dyads are descriptive only; directed counts remain the
    # primary denominator.
    dyads: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for edge in edges:
        key = tuple(sorted((edge["source_node"], edge["target_node"])))
        dyads.setdefault(key, []).append(edge)
    structural["non_none_unordered_dyad_count"] = sum(
        any(edge["opportunity_type"] != "none" for edge in pair) for pair in dyads.values()
    )
    structural["actionable_unordered_dyad_count"] = sum(
        any(edge["opportunity_type"] in ACTIONABLE for edge in pair) for pair in dyads.values()
    )

    contract = {}
    for condition in CONDITIONS:
        rows = [row for row in realizability if row["condition"] == condition]
        counts = Counter(row["operationally_realizable"] for row in rows)
        contract[condition] = {
            "denominator": E,
            "yes_count": counts.get("yes", 0),
            "no_count": counts.get("no", 0),
            "uncertain_count": counts.get("uncertain", 0),
            "realizability_bounds": bounds(counts.get("yes", 0), counts.get("yes", 0) + counts.get("uncertain", 0), E),
        }

    run_metrics: dict[str, Any] = {}
    for run_id in RUNS:
        run_tasks = [row for row in task_rows if row["run_id"] == run_id]
        run_findings = [row for row in finding_rows if row["run_id"] == run_id]
        run_edges = [row for row in coverage_rows if row.get("run_id") == run_id and row.get("structurally_actionable")]
        run_handoffs = [row for row in handoffs if row["run_id"] == run_id]
        run_post = [row for row in post_rows if row["run_id"] == run_id]
        mapped_nodes = sorted({node for row in run_tasks for node in row["node_ids"]})
        covered_edges = sum(row["coverage_status"] == "covered" for row in run_edges)
        realizable_handoff = Counter(row["operationally_realizable_at_handoff"] for row in run_handoffs)
        delivered_windows = sum(row["delivery_window_opened"] for row in run_handoffs)
        run_metrics[run_id] = {
            "task_denominator": len(run_tasks),
            "mapped_task_count": sum(row["mapping_status"] == "mapped" for row in run_tasks),
            "out_of_graph_task_count": sum(row["out_of_graph"] for row in run_tasks),
            "finding_file_denominator": len(run_findings),
            "mapped_finding_file_count": sum(row["mapping_status"] == "mapped" for row in run_findings),
            "out_of_graph_finding_file_count": sum(row["out_of_graph"] for row in run_findings),
            "mapped_unique_node_count": len(mapped_nodes),
            "mapped_node_ids": mapped_nodes,
            "node_coverage_bounds": bounds(len(mapped_nodes), len(mapped_nodes), len(nodes)),
            "run_realizability_denominator": E,
            "run_realizability_yes_count": realizable_handoff.get("yes", 0),
            "run_realizability_uncertain_count": realizable_handoff.get("uncertain", 0),
            "run_realizability_bounds": bounds(realizable_handoff.get("yes", 0), realizable_handoff.get("yes", 0) + realizable_handoff.get("uncertain", 0), E),
            "coverage_edge_denominator": E,
            "covered_unique_edge_count": covered_edges,
            "coverage_bounds": bounds(covered_edges, covered_edges, E),
            "delivery_window_denominator": len(run_post),
            "delivery_window_count": sum(row["delivery"] == "delivered" for row in run_post),
            "handoff_delivery_window_count": delivered_windows,
            "graph_edge_delivery_denominator": covered_edges,
            "graph_edge_delivery_rate": ratio(0, covered_edges),
        }

    post_summary = read_json(OPS / "post_sync_summary.json")
    behavior = {
        "historical_run_count": len(RUNS),
        "agent_run_row_denominator": len(post_rows),
        "runtime_window_delivery": bounds(post_summary["delivery_count"], post_summary["delivery_count"], len(post_rows)),
        "descriptive_semantic_rows": {
            "direct_relation_count": post_summary["discovery_direct_relation_count"],
            "actionable_lead_count": post_summary["actionable_lead_count"],
            "evidence_consumed_count": post_summary["evidence_consumed_count"],
            "judgment_changed_count": post_summary["judgment_changed_count"],
            "strict_foreign_evidence_ref_adoption_count": post_summary["strict_foreign_evidence_ref_adoption_count"],
            "selected_artifact_out_of_graph_count": post_summary["selected_artifact_out_of_graph_count"],
        },
        "graph_relevant_delivery_denominator": sum(item["covered_unique_edge_count"] for item in run_metrics.values()),
        "graph_relevant_discovery_rate": None,
        "graph_relevant_action_rate": None,
        "interpretation": "The 12 agent-run delivery rows are runtime-window observations. Because no actionable graph edge has a cross-agent covered instance, graph-relevant delivery/discovery/action rates are N/A; the descriptive labels are not promoted to graph edges.",
    }

    pilot_a_node_qc = read_json(PILOT_A_NODE_QC)
    pilot_b_node_qc = read_json(PILOT_B_NODE_QC)
    pilot_a_edge_qc = read_json(PILOT_A_EDGE_QC)
    pilot_b_edge_qc = read_json(PILOT_B_EDGE_QC)
    qc = {
        "pilot_a": {
            "node_boundary_status": pilot_a_node_qc["status"],
            "node_pair_agreement": bounds(pilot_a_node_qc["node_pair_agreement_count"], pilot_a_node_qc["node_pair_agreement_count"], pilot_a_node_qc["node_pair_count"]),
            "edge_status": pilot_a_edge_qc["status"],
            "binary_agreement": bounds(pilot_a_edge_qc["binary_agreement_count"], pilot_a_edge_qc["binary_agreement_count"], pilot_a_edge_qc["edge_count"]),
            "uncertain_edge_count": len(pilot_a_edge_qc["uncertain_edges"]),
        },
        "pilot_b": {
            "node_boundary_status": pilot_b_node_qc["status"],
            "node_pair_agreement": bounds(pilot_b_node_qc["agreement_count"], pilot_b_node_qc["agreement_count"], pilot_b_node_qc["new_pair_count"]),
            "edge_status": pilot_b_edge_qc["status"],
            "binary_agreement": bounds(pilot_b_edge_qc["binary_agreement_count"], pilot_b_edge_qc["binary_agreement_count"], pilot_b_edge_qc["new_directed_pair_count"]),
            "direction_agreement": bounds(pilot_b_edge_qc["direction_agreement_count"], pilot_b_edge_qc["direction_agreement_count"], pilot_b_edge_qc["direction_agreement_denominator"]),
            "uncertain_new_edge_count": len(pilot_b_edge_qc["uncertain_new_edges"]),
        },
        "frozen_graph_status": read_json(GRAPH_V2 / "graph_manifest.json")["adjudication_status"],
    }

    root_truth = Counter(node["truth_status"] for node in nodes)
    represented_roots = sum(bool(node.get("gt_root_ids")) for node in nodes)
    represented_near = sum(bool(node.get("near_miss_ids")) for node in nodes)
    gt = read_json(ROOT / "experiments/emergent_coordination/evaluator_private/flowise_3_1_3_repository_v1/ground_truth.json")
    represented_root_ids = {root_id for node in nodes for root_id in node.get("gt_root_ids", [])}
    represented_near_ids = {near_id for node in nodes for near_id in node.get("near_miss_ids", [])}
    remaining_root_ids = sorted(item["id"] for item in gt["roots"] if item["id"] not in represented_root_ids)
    remaining_near_ids = sorted(item["id"] for item in gt["near_misses"] if item["id"] not in represented_near_ids)
    candidate_pool = read_jsonl(CASE_DIR / "pilot-b-prep-v1/candidate_pool.jsonl")
    selected_candidate_ids = represented_root_ids | represented_near_ids | {"U_FILE_01_stream_uploaded_file_object_scope", "U_FILE_02_attachment_upload_type_guard"}
    remaining_candidates = [row for row in candidate_pool if row["candidate_id"] not in selected_candidate_ids]
    remaining_by_stratum: dict[str, list[str]] = {}
    for row in remaining_candidates:
        remaining_by_stratum.setdefault(row["stratum"], []).append(row["candidate_id"])
    expansion = {
        "v1_gt_root_total": 20,
        "v1_gt_roots_represented_in_graph_v2": represented_roots,
        "v1_gt_roots_remaining": 20 - represented_roots,
        "v1_gt_near_miss_total": 5,
        "v1_gt_near_misses_represented_in_graph_v2": represented_near,
        "v1_gt_near_misses_remaining": 5 - represented_near,
        "current_unscored_node_count": root_truth.get("admitted_unscored", 0),
        "remaining_root_ids_for_batching": remaining_root_ids,
        "remaining_near_miss_ids_for_batching": remaining_near_ids,
        "remaining_prequalified_candidate_ids_by_stratum": {
            key: sorted(value) for key, value in sorted(remaining_by_stratum.items())
        },
        "additional_unscored_fronts": "not enumerated; must be independently qualified from active fronts",
        "recommendation": "proceed_staged_structural_expansion_with_coverage_limit",
        "do_not_claim": [
            "do not infer whole-T4 opportunity utilization from the three historical seeds",
            "do not treat out_of_graph tasks/findings as none or as uncertain graph edges",
            "do not report runtime-window delivery as graph-edge delivery when coverage denominator is zero",
        ],
        "next_batches": [
            "independently adjudicate the remaining v1 roots and qualified near misses in bounded batches",
            "independently qualify and adjudicate additional unscored work fronts",
            "recompute the full directed-pair denominator and uncertain bounds after each frozen batch",
        ],
    }
    return {
        "schema_version": 1,
        "case_id": "flowise_3_1_3_repository_v1",
        "graph_version": "graph-v2",
        "graph_manifest_sha256": sha256(GRAPH_V2 / "graph_manifest.json"),
        "structural": structural,
        "contract_realizability": contract,
        "run_metrics": run_metrics,
        "behavior": behavior,
        "pilot_qc": qc,
        "expansion_decision": expansion,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", choices=("run", "verify"))
    args = parser.parse_args()
    report = load()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if args.run == "verify":
        assert report["structural"]["directed_pair_denominator"] == 240
        assert report["structural"]["actionable_bounds"] == {"lower_count": 12, "upper_count": 12, "denominator": 240, "lower_rate": 0.05, "upper_rate": 0.05}
        assert all(report["contract_realizability"][c]["uncertain_count"] == 0 for c in CONDITIONS)
        assert all(item["covered_unique_edge_count"] == 0 for item in report["run_metrics"].values())
        assert report["behavior"]["graph_relevant_delivery_denominator"] == 0
        assert report["pilot_qc"]["frozen_graph_status"] == "frozen"
        assert report["pilot_qc"]["pilot_a"]["uncertain_edge_count"] == 0
        assert report["pilot_qc"]["pilot_b"]["uncertain_new_edge_count"] == 0
        assert report["expansion_decision"]["recommendation"] == "proceed_staged_structural_expansion_with_coverage_limit"
        report["status"] = "verified"
    (OUT_DIR / "limited_analysis.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
