#!/usr/bin/env python3
"""Freeze a label-blind stratified sample from the 27-node directed universe."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "artifacts/hidden_opportunity_graph/flowise_3_1_3_repository_v1"
OUT = CASE / "sampled-opportunity-density-v1"
VERSION = "sampled-opportunity-density-v1"
SEED = "repository-v1-hog-density-20260926-v1"
ALLOC = {"old_to_old": 34, "old_to_new": 25, "new_to_old": 25, "new_to_new": 16}
POP = {"old_to_old": 240, "old_to_new": 176, "new_to_old": 176, "new_to_new": 110}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def jsonl_bytes(rows: list[dict]) -> bytes:
    return b"".join((json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode() for row in rows)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def render() -> dict[str, bytes]:
    node_path = CASE / "expansion-node-set-v2/nodes_frozen.jsonl"
    node_manifest_path = CASE / "expansion-node-set-v2/node_set_manifest.json"
    universe_path = CASE / "expansion-pair-universe-v1/pair_universe.jsonl"
    universe_manifest_path = CASE / "expansion-pair-universe-v1/pair_universe_manifest.json"
    graph_manifest_path = CASE / "graph-v2/graph_manifest.json"
    nodes = load_jsonl(node_path)
    nm = load_json(node_manifest_path)
    um = load_json(universe_manifest_path)
    assert len(nodes) == 27 and nm["status"] == "frozen_nodes_only"
    assert um["full_directed_pair_count"] == 702 and um["new_directed_pair_count"] == 462
    assert nm["node_set_version"] == um["node_set_version"] == "expansion-node-set-v2"
    assert sha(node_path.read_bytes()) == nm["nodes_sha256"]
    assert sha(universe_path.read_bytes()) == um["pairs_sha256"]
    old = [node["node_id"] for node in nodes[:16]]
    new = [node["node_id"] for node in nodes[16:]]
    assert len(set(old + new)) == 27 and um["base_node_count"] == len(old)
    graph_nodes = load_jsonl(CASE / "graph-v2/nodes.jsonl")
    assert len(graph_nodes) == 16 and {node["node_id"] for node in graph_nodes} == set(old)
    strata: dict[str, list[tuple[str, str]]] = {
        "old_to_old": [(a, b) for a in old for b in old if a != b],
        "old_to_new": [(a, b) for a in old for b in new],
        "new_to_old": [(a, b) for a in new for b in old],
        "new_to_new": [(a, b) for a in new for b in new if a != b],
    }
    expansion = load_jsonl(universe_path)
    expanded = {(r["source_node"], r["target_node"]) for r in expansion}
    assert len(expanded) == 462
    assert expanded == set().union(*(set(strata[k]) for k in ("old_to_new", "new_to_old", "new_to_new")))
    assert {k: len(v) for k, v in strata.items()} == POP
    assert len(set().union(*(set(v) for v in strata.values()))) == 702

    sample = []
    for stratum, pairs in strata.items():
        ranked = sorted(pairs, key=lambda p: (sha(f"{SEED}|{stratum}|{p[0]}|{p[1]}".encode()), p))
        for a, b in ranked[:ALLOC[stratum]]:
            sample.append({
                "pair_id": f"{VERSION}:{a}:{b}", "source_node": a, "target_node": b,
                "stratum": stratum, "stratum_population": POP[stratum], "stratum_sample": ALLOC[stratum],
                "inclusion_probability": ALLOC[stratum] / POP[stratum],
                "sampling_weight": POP[stratum] / ALLOC[stratum],
                "selection_sha256": sha(f"{SEED}|{stratum}|{a}|{b}".encode()),
            })
    assert len(sample) == 100 and len({r["pair_id"] for r in sample}) == 100
    sample_data = jsonl_bytes(sample)
    prereg = {
        "version": VERSION, "status": "preregistered_before_sample_reviews",
        "estimand": "27-node repository-v1 directed-pair actionable structural opportunity density",
        "actionable_types": ["actionable cross-check", "strong dependency"],
        "denominator": 702, "sample_size": 100, "seed": SEED,
        "sampling_rule": "Within each fixed stratum, rank every directed pair by SHA-256(seed|stratum|source_node|target_node), tie-break lexically, and take the first n without replacement.",
        "strata": {k: {"population": POP[k], "sample": ALLOC[k], "inclusion_probability": ALLOC[k] / POP[k]} for k in POP},
        "allocation_reason": "Approximately proportional allocation, 100/702 sampling fraction; at a 5-10% prevalence, binomial-scale 95% uncertainty is roughly plus/minus 4-6 percentage points before finite-population correction. Keeps two independent reviews near 200 records.",
        "history_policy": "Selection uses node IDs, frozen old/new membership and frozen pair universe only; no edge labels, T4 behavior, collaboration outcomes, or Batch-03 failed records.",
        "prior_label_policy": "All selected pairs receive new independent blind reviews, including any Pilot or Batch-01 overlap. Prior labels are excluded from reviewer bundles and estimator.",
        "primary_qc": "At least ceil(0.90*100)=90 raw binary agreements before adjudication. If it fails, stop primary estimation and report taxonomy reliability failure.",
        "secondary_qc": "Report exact five-class agreement, five-class confusion matrix, reviewer marginals and disagreement types; five-class disagreement is not a primary gate.",
        "adjudication": "Only sampled pairs with reviewer disagreement or actionable-boundary uncertainty, and only after binary QC passes; preserve raw records.",
        "estimator": "sum_h (N_h/702)*(y_h/n_h); estimated count=702*density. Use final adjudicated binary labels for disagreements and agreed raw labels otherwise.",
        "variance": "sum_h (N_h/702)^2*(1-n_h/N_h)*s_h^2/n_h, with s_h^2=n_h*p_h*(1-p_h)/(n_h-1); report a 95% design-based normal interval clipped to [0,1], noting low-count limitations.",
        "sensitivity": "For unresolved actionable-boundary uncertain sampled pairs, recalculate weighted density with all uncertain set to 0 and all set to 1.",
        "node_set_manifest_sha256": sha(node_manifest_path.read_bytes()),
        "node_set_nodes_sha256": sha(node_path.read_bytes()),
        "pair_universe_manifest_sha256": sha(universe_manifest_path.read_bytes()),
        "pair_universe_pairs_sha256": sha(universe_path.read_bytes()),
        "base_graph_manifest_sha256": sha(graph_manifest_path.read_bytes()),
        "sample_manifest_sha256": sha(sample_data),
    }
    return {"sampling_prereg.json": json_bytes(prereg), "sampled_pairs.jsonl": sample_data}


def main() -> None:
    outputs = render()
    OUT.mkdir(parents=True, exist_ok=True)
    for name, data in outputs.items():
        path = OUT / name
        if path.exists():
            assert path.read_bytes() == data, f"frozen artifact changed: {path}"
        else:
            path.write_bytes(data)
    print(json.dumps({"status": "verified_frozen_sample", "sample_size": 100,
                      "sample_manifest_sha256": sha(outputs["sampled_pairs.jsonl"])}, indent=2))


if __name__ == "__main__":
    main()
