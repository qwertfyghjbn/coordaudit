#!/usr/bin/env python3
"""Freeze the 462-pair expansion directed-pair universe without any edge labels."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from datetime import date
from pathlib import Path
from typing import Any

from scripts.hidden_opportunity_graph import (
    CASE_ID,
    PILOT_B_GRAPH_DIR,
    GraphValidationError,
    _read_json,
    _read_jsonl,
    _require,
    validate_graph,
)


PAIR_UNIVERSE_VERSION = "expansion-pair-universe-v1"
GRAPH_DIR = PILOT_B_GRAPH_DIR
CASE_DIR = PILOT_B_GRAPH_DIR.parent
NODE_SET_VERSION = "expansion-node-set-v2"
NODE_SET_DIR = CASE_DIR / NODE_SET_VERSION
OUT_DIR = CASE_DIR / PAIR_UNIVERSE_VERSION
PAIR_CLASSES = ("old_to_new", "new_to_old", "new_to_new")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def jbytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def jlbytes(values: list[dict[str, Any]]) -> bytes:
    return b"".join((json.dumps(v, ensure_ascii=False, sort_keys=True) + "\n").encode() for v in values)


def load_frozen_basis() -> tuple[dict[str, Any], dict[str, Any], list[str], set[str], set[tuple[str, str]]]:
    _require(validate_graph(PILOT_B_GRAPH_DIR)["status"] == "valid_frozen", "graph-v2 is not a frozen base graph")
    base_manifest = _read_json(GRAPH_DIR / "graph_manifest.json")
    node_set_manifest = _read_json(NODE_SET_DIR / "node_set_manifest.json")
    _require(node_set_manifest["node_set_version"] == NODE_SET_VERSION
             and node_set_manifest["status"] == "frozen_nodes_only"
             and node_set_manifest["final_node_count"] == 27
             and node_set_manifest["new_node_count"] == 11
             and node_set_manifest["base_node_count"] == 16
             and node_set_manifest["edge_status"] == "not_started",
             "current expansion node set is not the frozen 27-node v2 set")
    nodes_path = NODE_SET_DIR / "nodes_frozen.jsonl"
    _require(digest(nodes_path.read_bytes()) == node_set_manifest["nodes_sha256"],
             "frozen expansion nodes changed")
    node_ids = [node["node_id"] for node in _read_jsonl(nodes_path)]
    old_ids = {node["node_id"] for node in _read_jsonl(GRAPH_DIR / "nodes.jsonl")}
    _require(len(node_ids) == 27 == len(set(node_ids)) and old_ids <= set(node_ids) and len(old_ids) == 16,
             "27-node frozen set identity mismatch")
    existing_pairs = {(edge["edge_id"].split(":")[1], edge["edge_id"].split(":")[2])
                      for edge in _read_jsonl(GRAPH_DIR / "edges.jsonl")}
    _require(len(existing_pairs) == 240
             and all(source != target for source, target in existing_pairs)
             and all(source in old_ids and target in old_ids for source, target in existing_pairs),
             "graph-v2 old-old directed pairs are not the frozen 16x15 set")
    return node_set_manifest, base_manifest, node_ids, old_ids, existing_pairs


def pair_class_of(source: str, target: str, old_ids: set[str]) -> str:
    if source in old_ids:
        return "old_to_new" if target not in old_ids else "old_to_old"
    return "new_to_old" if target in old_ids else "new_to_new"


def build_universe(node_ids: list[str], old_ids: set[str],
                   existing_pairs: set[tuple[str, str]]) -> list[dict[str, Any]]:
    universe = []
    for source, target in itertools.permutations(sorted(node_ids), 2):
        if (source, target) in existing_pairs:
            continue
        _require(pair_class_of(source, target, old_ids) != "old_to_old",
                 "old-old pair leaked past the graph-v2 exclusion")
        universe.append({
            "pair_id": f"{PAIR_UNIVERSE_VERSION}:{source}:{target}",
            "source_node": source,
            "target_node": target,
            "pair_class": pair_class_of(source, target, old_ids),
            "node_set_version": NODE_SET_VERSION,
        })
    return universe


def validate_universe(universe: list[dict[str, Any]], node_ids: list[str], old_ids: set[str],
                      existing_pairs: set[tuple[str, str]]) -> dict[str, Any]:
    pair_ids = [row["pair_id"] for row in universe]
    pairs = [(row["source_node"], row["target_node"]) for row in universe]
    expected = set(itertools.permutations(node_ids, 2)) - existing_pairs
    counts = {name: sum(row["pair_class"] == name for row in universe) for name in PAIR_CLASSES}
    checks = {
        "total_is_462": len(universe) == 462,
        "old_to_new_is_176": counts["old_to_new"] == 176,
        "new_to_old_is_176": counts["new_to_old"] == 176,
        "new_to_new_is_110": counts["new_to_new"] == 110,
        "duplicates_are_0": len(set(pair_ids)) == len(pair_ids),
        "self_edges_are_0": all(source != target for source, target in pairs),
        "overlap_with_existing_240_is_0": len(set(pairs) & existing_pairs) == 0,
        "missing_are_0": len(expected - set(pairs)) == 0,
        "no_extra_beyond_702_minus_240": len(set(pairs) - expected) == 0,
        "pair_ids_match_pattern": all(row["pair_id"] == f"{PAIR_UNIVERSE_VERSION}:{row['source_node']}:{row['target_node']}"
                                      for row in universe),
        "all_endpoints_in_frozen_27": all(row["source_node"] in set(node_ids)
                                          and row["target_node"] in set(node_ids) for row in universe),
    }
    return {
        "validator": "expansion-pair-universe-deterministic-validator-v1",
        "checks": checks,
        "counts": {"total": len(universe), **counts,
                   "full_universe_27x26": 702, "existing_old_old": len(existing_pairs),
                   "new_pairs": 702 - len(existing_pairs)},
        "all_passed": all(checks.values()),
    }


def render(freeze_date: str) -> tuple[dict[str, bytes], dict[str, Any]]:
    node_set_manifest, base_manifest, node_ids, old_ids, existing_pairs = load_frozen_basis()
    universe = build_universe(node_ids, old_ids, existing_pairs)
    validation = validate_universe(universe, node_ids, old_ids, existing_pairs)
    _require(validation["all_passed"], "pair universe validation failed; refusing to freeze")
    input_lock = _read_json(GRAPH_DIR / "input_lock.json")
    pairs_data = jlbytes(universe)
    validation = {**validation, "pair_universe_manifest_status": "frozen_pairs_only_unannotated"}
    validation_data = jbytes(validation)
    manifest = {
        "schema_version": 1,
        "pair_universe_version": PAIR_UNIVERSE_VERSION,
        "case_id": CASE_ID,
        "status": "frozen_pairs_only_unannotated",
        "freeze_date": freeze_date,
        "label_policy": "no_opportunity_labels_included",
        "base_graph_version": base_manifest["graph_version"],
        "base_graph_manifest_sha256": digest((GRAPH_DIR / "graph_manifest.json").read_bytes()),
        "annotation_protocol_version": input_lock["annotation_protocol_version"],
        "graph_schema_version": input_lock["graph_schema_version"],
        "node_set_version": node_set_manifest["node_set_version"],
        "node_set_manifest_sha256": digest((NODE_SET_DIR / "node_set_manifest.json").read_bytes()),
        "node_set_nodes_sha256": node_set_manifest["nodes_sha256"],
        "target_sha256": base_manifest["target_sha256"],
        "gt_generation": base_manifest["gt_generation"],
        "gt_sha256": base_manifest["gt_sha256"],
        "base_node_count": 16,
        "new_node_count": 11,
        "final_node_count": 27,
        "base_directed_pair_count": 240,
        "full_directed_pair_count": 702,
        "new_directed_pair_count": 462,
        "pair_class_counts": validation["counts"],
        "pair_class_definitions": {
            "old_to_new": "source in base 16-node graph-v2 set, target in 11 new expansion nodes",
            "new_to_old": "source in 11 new expansion nodes, target in base 16-node graph-v2 set",
            "new_to_new": "both endpoints in 11 new expansion nodes",
        },
        "pair_identity_rule": ("pair_id = pair_universe_version:source_node:target_node; derived only from the "
                               "frozen 27-node set and the graph-v2 240 old-old pairs; independent of seed, agent, "
                               "run, and historical findings"),
        "pairs_sha256": digest(pairs_data),
        "validator_result_sha256": digest(validation_data),
    }
    outputs = {
        "pair_universe.jsonl": pairs_data,
        "pair_universe_validation.json": validation_data,
        "pair_universe_manifest.json": jbytes(manifest),
    }
    return outputs, manifest


def freeze() -> dict[str, Any]:
    _require(not OUT_DIR.is_symlink(), "unsafe pair-universe directory")
    OUT_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    OUT_DIR.chmod(0o700)
    outputs, _ = render(date.today().isoformat())
    for name, content in outputs.items():
        path = OUT_DIR / name
        _require(not path.is_symlink() and (not path.exists() or path.read_bytes() == content),
                 f"frozen pair-universe artifact changed; create a new version: {name}")
    for name, content in outputs.items():
        path = OUT_DIR / name
        if not path.exists():
            path.write_bytes(content)
        path.chmod(0o600)
    return verify()


def verify() -> dict[str, Any]:
    manifest_path = OUT_DIR / "pair_universe_manifest.json"
    _require(manifest_path.is_file() and not manifest_path.is_symlink(), "pair-universe manifest missing")
    recorded = _read_json(manifest_path)
    outputs, manifest = render(recorded["freeze_date"])
    for name, content in outputs.items():
        path = OUT_DIR / name
        _require(path.is_file() and not path.is_symlink() and path.read_bytes() == content,
                 f"frozen pair-universe artifact mismatch: {name}")
    _require(recorded == manifest, "pair-universe manifest mismatch")
    return {
        "status": "verified_frozen_pairs_only_unannotated",
        "pair_universe_version": PAIR_UNIVERSE_VERSION,
        "pair_universe_manifest_sha256": digest(outputs["pair_universe_manifest.json"]),
        "pairs_sha256": manifest["pairs_sha256"],
        "node_set_manifest_sha256": manifest["node_set_manifest_sha256"],
        "new_directed_pair_count": manifest["new_directed_pair_count"],
        "pair_class_counts": manifest["pair_class_counts"],
        "validator_all_passed": json.loads(outputs["pair_universe_validation.json"])["all_passed"],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "verify"))
    args = parser.parse_args()
    try:
        result = freeze() if args.command == "freeze" else verify()
    except GraphValidationError as exc:
        parser.exit(1, f"expansion pair-universe freeze failed: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
