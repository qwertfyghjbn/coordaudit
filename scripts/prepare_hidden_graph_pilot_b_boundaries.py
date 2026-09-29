"""在独立资格 QC 后，构造 Pilot B 选择和 split/merge 盲标包。"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path
from typing import Any

from experiments.emergent_coordination.harness.cases import load_case
from scripts.check_hidden_graph_pilot_b_candidates import assess as assess_candidates
from scripts.hidden_opportunity_graph import (
    CASE_ID,
    PILOT_B_GRAPH_DIR,
    PILOT_B_GRAPH_VERSION,
    PRIVATE_GRAPH_DIR,
    GraphValidationError,
    _read_json,
    _read_jsonl,
    _require,
    _validate_node,
    validate_graph,
)
from scripts.prepare_hidden_graph_pilot_b_candidates import STRATA
from scripts.prepare_hidden_graph_pilot_b_candidates_round2 import ROUND2_DIR


BOUNDARY_DIR = PILOT_B_GRAPH_DIR / "pilot_b"
QUALIFICATION_DIR = ROUND2_DIR
PACKET_VERSION = "pilot-b-selected-node-boundaries-v1"
SELECTED_KEYS = {"candidate_id", "distinct_mechanism", "selection_rationale", "potential_artifact"}
EXCLUDED_KEYS = {"candidate_id", "distinct_mechanism", "reason"}


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _jsonl_bytes(values: list[dict[str, Any]]) -> bytes:
    return b"".join((json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8") for value in values)


def _selection(report: dict[str, Any], candidates: dict[str, dict[str, Any]],
               final: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    path = QUALIFICATION_DIR / "selection_spec.json"
    _require(path.is_file() and not path.is_symlink(), "missing private Pilot B selection spec")
    spec = _read_json(path)
    _require(set(spec) == {"selection_version", "selected", "excluded_admitted", "empty_strata"}
             and spec["selection_version"] == "pilot-b-selection-v1", "Pilot B selection schema mismatch")
    selected = spec["selected"]
    excluded = spec["excluded_admitted"]
    empty = spec["empty_strata"]
    _require(isinstance(selected, list) and 1 <= len(selected) <= 10, "Pilot B must select 1–10 nodes")
    _require(isinstance(excluded, list) and isinstance(empty, list), "invalid Pilot B selection lists")
    admitted = set(report["admitted_candidate_ids"])
    chosen = set()
    counts = {stratum: 0 for stratum in STRATA}
    mechanisms = {stratum: set() for stratum in STRATA}
    for item in selected:
        _require(isinstance(item, dict) and set(item) == SELECTED_KEYS, "selected Pilot B node schema mismatch")
        identifier = item["candidate_id"]
        _require(isinstance(identifier, str) and identifier in admitted and identifier not in chosen,
                 "selected Pilot B item is duplicate or ineligible")
        for key in SELECTED_KEYS - {"candidate_id"}:
            _require(isinstance(item[key], str) and item[key].strip(), f"selected Pilot B node lacks {key}")
        stratum = candidates[identifier]["stratum"]
        counts[stratum] += 1
        _require(counts[stratum] <= 2 and item["distinct_mechanism"] not in mechanisms[stratum],
                 f"Pilot B layer duplicates its mechanism or exceeds two: {stratum}")
        mechanisms[stratum].add(item["distinct_mechanism"])
        chosen.add(identifier)
    excluded_ids = set()
    assigned_mechanisms = {item["candidate_id"]: item["distinct_mechanism"] for item in selected}
    for item in excluded:
        _require(isinstance(item, dict) and set(item) == EXCLUDED_KEYS, "excluded Pilot B node schema mismatch")
        identifier = item["candidate_id"]
        _require(isinstance(identifier, str) and identifier in admitted - chosen and identifier not in excluded_ids
                 and isinstance(item["distinct_mechanism"], str) and item["distinct_mechanism"].strip()
                 and isinstance(item["reason"], str) and item["reason"].strip(),
                 "admitted-but-unselected Pilot B item lacks reason")
        excluded_ids.add(identifier)
        assigned_mechanisms[identifier] = item["distinct_mechanism"]
    _require(chosen | excluded_ids == admitted, "Pilot B selection omits an admitted candidate")
    expected_empty = {stratum for stratum in STRATA
                      if not any(candidates[item]["stratum"] == stratum for item in admitted)}
    _require(set(empty) == expected_empty and len(empty) == len(expected_empty),
             "Pilot B empty-layer declaration does not match qualification results")
    _require(all(counts[stratum] >= 1 for stratum in STRATA if stratum not in expected_empty),
             "qualified Pilot B layer was left empty")
    key = lambda item: (
        STRATA.index(candidates[item["candidate_id"]]["stratum"]),
        candidates[item["candidate_id"]]["anchor"]["path"],
        candidates[item["candidate_id"]]["anchor"]["symbol"],
        final[item["candidate_id"]]["invariant"],
    )
    _require(selected == sorted(selected, key=key), "selected Pilot B nodes must use stable source ordering")
    expected = []
    for stratum in STRATA:
        seen = set()
        in_stratum = sorted((item for item in admitted if candidates[item]["stratum"] == stratum),
                            key=lambda item: (candidates[item]["anchor"]["path"],
                                              candidates[item]["anchor"]["symbol"], final[item]["invariant"], item))
        for identifier in in_stratum:
            mechanism = assigned_mechanisms[identifier]
            if mechanism not in seen:
                seen.add(mechanism)
                if len(seen) <= 2:
                    expected.append(identifier)
    _require([item["candidate_id"] for item in selected] == expected,
             "Pilot B selection must take the first two distinct source mechanisms in fixed source order")
    return selected


def render() -> dict[str, bytes]:
    _require(validate_graph(PRIVATE_GRAPH_DIR)["status"] == "valid_frozen", "Pilot A graph is not frozen")
    _require(validate_graph(PILOT_B_GRAPH_DIR)["status"] == "valid_draft", "Pilot B graph is not a draft")
    report, sources = assess_candidates(QUALIFICATION_DIR)
    _require(report["status"] == "ready_for_boundary_and_selection_qc", "Pilot B candidate QC has not passed")
    candidates, final = sources["candidates"], sources["final"]
    selected = _selection(report, candidates, final)
    gt = _read_json(load_case(CASE_ID).ground_truth_path)
    roots = {item["id"] for item in gt["roots"]}
    near = {item["id"] for item in gt["near_misses"]}
    target = load_case(CASE_ID).target_root
    pilot_a = _read_jsonl(PRIVATE_GRAPH_DIR / "nodes.jsonl")
    _require([item["node_id"] for item in pilot_a] == [f"F{i:03d}" for i in range(1, 7)],
             "Pilot A node identities changed")
    new_nodes = []
    for ordinal, choice in enumerate(selected, 7):
        identifier = choice["candidate_id"]
        review = final[identifier]
        kind = candidates[identifier]["source_kind"]
        status = {"scored_root": "scored_positive", "qualified_near_miss": "qualified_near_miss",
                  "bounded_unscored_question": "admitted_unscored"}[kind]
        refs = review["evidence_refs"]
        node = {
            "node_id": f"F{ordinal:03d}",
            "security_question": review["security_question"],
            "code_scope": list(dict.fromkeys(ref["path"] for ref in refs)),
            "invariant": review["invariant"],
            "boundary_rationale": "候选资格已审；待 selected-pair 双人 split/merge QC。" + choice["selection_rationale"],
            "potential_artifact": choice["potential_artifact"],
            "evidence_refs": refs,
            "truth_status": status,
            "gt_root_ids": [identifier] if kind == "scored_root" else [],
            "near_miss_ids": [identifier] if kind == "qualified_near_miss" else [],
            "adjudication_status": "proposed",
        }
        _validate_node(node, f"Pilot B selected node {identifier}", target, roots, near)
        new_nodes.append(node)
    all_nodes = pilot_a + new_nodes
    candidate_by_node = {node["node_id"]: identifier["candidate_id"] for node, identifier in zip(new_nodes, selected)}
    pairs = []
    for left, right in itertools.combinations(all_nodes, 2):
        if left["node_id"] in candidate_by_node or right["node_id"] in candidate_by_node:
            pairs.append({
                "candidate_a": left["node_id"], "candidate_b": right["node_id"],
                "security_question_a": left["security_question"],
                "security_question_b": right["security_question"],
            })
    expected_pairs = len(new_nodes) * 6 + len(new_nodes) * (len(new_nodes) - 1) // 2
    _require(len(pairs) == expected_pairs, "Pilot B split/merge pair universe incomplete")
    bundle = {
        "packet_version": PACKET_VERSION,
        "case_id": CASE_ID,
        "graph_version": PILOT_B_GRAPH_VERSION,
        "pilot_a_graph_manifest_sha256": _digest((PRIVATE_GRAPH_DIR / "graph_manifest.json").read_bytes()),
        "candidate_packet_sha256": report["packet_manifest_sha256"],
        "selection_spec_sha256": _digest((QUALIFICATION_DIR / "selection_spec.json").read_bytes()),
        "review_file_sha256": report["review_file_sha256"],
        "adjudication_file_sha256": report["adjudication_file_sha256"],
        "review_instructions": (
            "独立逐对判断所选 Pilot B 节点与 Pilot A/其他 Pilot B 节点能否 split。"
            "写不同 security question、可独立变化的真值和必要源码链；共享文件、类别或 GT root 身份不决定边界。"
            "不要查看其他人的边界标注、首轮选择意见、历史 T4 或 condition 表现。"
        ),
        "pilot_a_nodes": pilot_a,
        "selected_pilot_b_nodes_proposed": new_nodes,
        "unordered_pairs": pairs,
    }
    anchors = {node["node_id"]: node["evidence_refs"][0] for node in all_nodes}
    form = [{
        "reviewer_id": "", "candidate_a": pair["candidate_a"], "candidate_b": pair["candidate_b"],
        "security_question_a": pair["security_question_a"],
        "security_question_b": pair["security_question_b"],
        "decision": "", "counterfactual": "", "rationale": "",
        "evidence_refs": [
            {**{key: anchors[pair["candidate_a"]][key] for key in ("path", "line", "symbol", "excerpt", "excerpt_sha256")},
             "role": "candidate_a"},
            {**{key: anchors[pair["candidate_b"]][key] for key in ("path", "line", "symbol", "excerpt", "excerpt_sha256")},
             "role": "candidate_b"},
        ],
    } for pair in pairs]
    payloads = {
        "selected_nodes_proposed.jsonl": _jsonl_bytes(new_nodes),
        "boundary_reviewer_bundle.json": _json_bytes(bundle),
        "boundary_review_form_template.jsonl": _jsonl_bytes(form),
    }
    payloads["boundary_packet_manifest.json"] = _json_bytes({
        "packet_version": PACKET_VERSION,
        "case_id": CASE_ID,
        "graph_version": PILOT_B_GRAPH_VERSION,
        "pilot_a_graph_manifest_sha256": bundle["pilot_a_graph_manifest_sha256"],
        "candidate_packet_sha256": bundle["candidate_packet_sha256"],
        "selection_spec_sha256": bundle["selection_spec_sha256"],
        "review_file_sha256": bundle["review_file_sha256"],
        "adjudication_file_sha256": bundle["adjudication_file_sha256"],
        "builder_sha256": _digest(Path(__file__).read_bytes()),
        "selected_nodes_proposed_sha256": _digest(payloads["selected_nodes_proposed.jsonl"]),
        "boundary_reviewer_bundle_sha256": _digest(payloads["boundary_reviewer_bundle.json"]),
        "boundary_review_form_template_sha256": _digest(payloads["boundary_review_form_template.jsonl"]),
        "selected_node_count": len(new_nodes),
        "unordered_pair_count": len(pairs),
        "annotation_status": "ungraded_selected_node_boundaries",
    })
    return payloads


def build() -> dict[str, Any]:
    _require(not BOUNDARY_DIR.is_symlink(), "unsafe Pilot B boundary directory")
    BOUNDARY_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    BOUNDARY_DIR.chmod(0o700)
    payloads = render()
    for name, data in payloads.items():
        path = BOUNDARY_DIR / name
        _require(not path.is_symlink() and (not path.exists() or path.read_bytes() == data),
                 f"Pilot B boundary packet changed; create a new packet version: {name}")
        path.write_bytes(data)
        path.chmod(0o600)
    return verify()


def verify() -> dict[str, Any]:
    payloads = render()
    for name, data in payloads.items():
        path = BOUNDARY_DIR / name
        _require(path.is_file() and not path.is_symlink() and path.read_bytes() == data,
                 f"Pilot B boundary packet missing or changed: {name}")
    manifest = _read_json(BOUNDARY_DIR / "boundary_packet_manifest.json")
    return {
        "status": "verified_ungraded_boundary_packet",
        "selected_node_count": manifest["selected_node_count"],
        "unordered_pair_count": manifest["unordered_pair_count"],
        "boundary_packet_manifest_sha256": _digest(payloads["boundary_packet_manifest.json"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "verify"))
    args = parser.parse_args()
    try:
        result = build() if args.command == "build" else verify()
    except GraphValidationError as exc:
        parser.exit(1, f"Pilot B boundary packet error: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
