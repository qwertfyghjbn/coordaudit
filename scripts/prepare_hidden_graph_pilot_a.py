"""在 evaluator-side 私有目录生成并核验 Pilot A 节点证据包与单人边界初判。"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path
from typing import Any

from scripts.hidden_opportunity_graph import (
    CASE_ID,
    PILOT_A_CANDIDATES,
    PRIVATE_GRAPH_DIR,
    GraphValidationError,
    _read_json,
    _require,
    _target_file,
    validate_graph,
)
from experiments.emergent_coordination.harness.cases import load_case


PILOT_DIR = PRIVATE_GRAPH_DIR / "pilot_a"
PACKET_VERSION = "pilot-a-node-packet-v1"


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _jsonl_bytes(records: list[dict[str, Any]]) -> bytes:
    return b"".join((json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8") for item in records)


def _evidence(target: Path, descriptor: dict[str, Any]) -> dict[str, Any]:
    _require(set(descriptor) == {"path", "line", "symbol", "role", "meaning", "expected"},
             "evidence descriptor has missing or unexpected fields")
    path = descriptor["path"]
    _require(isinstance(path, str) and isinstance(descriptor["line"], int) and descriptor["line"] > 0,
             "invalid evidence location")
    for key in ("symbol", "role", "meaning", "expected"):
        _require(isinstance(descriptor[key], str) and descriptor[key].strip(), f"empty evidence descriptor: {key}")
    source = _target_file(target, path, "Pilot A evidence")
    lines = source.read_text(encoding="utf-8").splitlines()
    _require(descriptor["line"] <= len(lines), f"line outside target file: {path}:{descriptor['line']}")
    excerpt = lines[descriptor["line"] - 1].strip()
    _require(bool(excerpt) and descriptor["expected"] in excerpt,
             f"expected text missing at {path}:{descriptor['line']}")
    return {
        "path": path,
        "line": descriptor["line"],
        "symbol": descriptor["symbol"],
        "role": descriptor["role"],
        "meaning": descriptor["meaning"],
        "excerpt": excerpt,
        "excerpt_sha256": _digest(excerpt.encode("utf-8")),
    }


def _gt_anchor(target: Path, candidate_id: str, gt: dict[str, Any], expected_line: int) -> dict[str, Any]:
    indexed = {item["id"]: item for item in [*gt["roots"], *gt["near_misses"]]}
    _require(candidate_id in indexed, f"candidate not in v1 GT: {candidate_id}")
    entry = indexed[candidate_id]
    anchor = entry["anchors"][0] if "anchors" in entry else entry["anchor"]
    source = _target_file(target, anchor["file"], "GT anchor")
    lines = source.read_text(encoding="utf-8").splitlines()
    excerpt = anchor["excerpt"]
    _require(type(expected_line) is int and 1 <= expected_line <= len(lines) and excerpt in lines[expected_line - 1],
             f"GT excerpt not found at locked line: {candidate_id}:{expected_line}")
    digest = _digest(excerpt.encode("utf-8"))
    if "excerpt_sha256" in anchor:
        _require(digest == anchor["excerpt_sha256"], f"GT excerpt hash mismatch: {candidate_id}")
    return {
        "path": anchor["file"],
        "line": expected_line,
        "symbol": anchor["function"],
        "role": "gt_anchor",
        "meaning": "冻结 v1 GT 或 qualified near miss 的定位锚；不单独证明整条安全链。",
        "excerpt": excerpt,
        "excerpt_sha256": digest,
    }


def render(directory: Path = PILOT_DIR) -> dict[str, bytes]:
    _require(not directory.is_symlink(), "Pilot A directory must not be a symlink")
    directory = directory.resolve()
    validate_graph(directory.parent)
    case = load_case(CASE_ID)
    lock = _read_json(directory.parent / "input_lock.json")
    source_path = directory / "source_spec.json"
    _require(source_path.is_file() and not source_path.is_symlink(), "missing private Pilot A source spec")
    spec = _read_json(source_path)
    _require(spec.get("packet_version") == PACKET_VERSION, "Pilot A packet version mismatch")
    raw_candidates = spec.get("candidates")
    raw_pairs = spec.get("boundary_preliminary")
    _require(isinstance(raw_candidates, list) and isinstance(raw_pairs, list), "invalid Pilot A spec lists")
    _require([item.get("candidate_id") for item in raw_candidates] == PILOT_A_CANDIDATES,
             "Pilot A candidates do not match input lock order")
    gt = _read_json(case.ground_truth_path)
    siblings = _read_json(case.evaluator_private_root / "safe_siblings.json")
    sibling_index = {item["id"]: item for item in siblings["entries"]}
    packets: list[dict[str, Any]] = []
    for item in raw_candidates:
        required = {
            "candidate_id", "gt_status", "security_question", "decision_to_reach", "source",
            "affected_object", "invariant", "minimal_artifact", "positive_outcome", "negative_outcome",
            "scope_limits", "open_questions", "safe_sibling_ids", "safe_sibling_anchor_lines",
            "gt_anchor_line", "chain"
        }
        _require(set(item) == required, f"candidate spec fields invalid: {item.get('candidate_id')}")
        _require(item["gt_status"] in {"scored_positive", "qualified_near_miss"}, "invalid GT status")
        root_ids = {entry["id"] for entry in gt["roots"]}
        _require(item["gt_status"] == ("scored_positive" if item["candidate_id"] in root_ids else "qualified_near_miss"),
                 "candidate GT status mismatch")
        for key in required - {
            "candidate_id", "gt_status", "chain", "scope_limits", "open_questions", "safe_sibling_ids",
            "safe_sibling_anchor_lines", "gt_anchor_line"
        }:
            _require(isinstance(item[key], str) and item[key].strip(), f"empty candidate field: {key}")
        _require(isinstance(item["chain"], list) and len(item["chain"]) >= 3, "candidate chain too short")
        evidence = [_gt_anchor(case.target_root, item["candidate_id"], gt, item["gt_anchor_line"])]
        evidence.extend(_evidence(case.target_root, descriptor) for descriptor in item["chain"])
        contrasts = []
        _require(isinstance(item["safe_sibling_ids"], list) and len(item["safe_sibling_ids"]) == len(set(item["safe_sibling_ids"])),
                 "invalid safe sibling IDs")
        _require(isinstance(item["safe_sibling_anchor_lines"], dict)
                 and set(item["safe_sibling_anchor_lines"]) == set(item["safe_sibling_ids"]),
                 "safe sibling anchor line set mismatch")
        for sibling_id in item["safe_sibling_ids"]:
            _require(sibling_id in sibling_index, f"unknown safe sibling: {sibling_id}")
            sibling = sibling_index[sibling_id]
            source = _target_file(case.target_root, sibling["path"], "safe sibling anchor")
            lines = source.read_text(encoding="utf-8").splitlines()
            sibling_line = item["safe_sibling_anchor_lines"][sibling_id]
            _require(type(sibling_line) is int and 1 <= sibling_line <= len(lines)
                     and sibling["excerpt"] in lines[sibling_line - 1],
                     f"safe sibling excerpt missing at locked line: {sibling_id}:{sibling_line}")
            contrast_evidence = {
                "path": sibling["path"],
                "line": sibling_line,
                "symbol": sibling["symbol"],
                "role": "narrow_safe_contrast",
                "meaning": sibling["security_basis"],
                "excerpt": sibling["excerpt"],
                "excerpt_sha256": _digest(sibling["excerpt"].encode("utf-8")),
            }
            evidence.append(contrast_evidence)
            contrasts.append({"id": sibling_id, "qualification": sibling["qualification"], "scope": sibling["security_basis"]})
        _require(all(isinstance(text, str) and text.strip() for text in item["scope_limits"]), "invalid scope limits")
        _require(all(isinstance(text, str) and text.strip() for text in item["open_questions"]), "invalid open questions")
        packets.append({
            "packet_version": PACKET_VERSION,
            "case_id": CASE_ID,
            "graph_version": lock["graph_version"],
            "candidate_id": item["candidate_id"],
            "gt_status": item["gt_status"],
            "security_question": item["security_question"],
            "decision_to_reach": item["decision_to_reach"],
            "source": item["source"],
            "affected_object": item["affected_object"],
            "invariant": item["invariant"],
            "minimal_artifact": item["minimal_artifact"],
            "positive_outcome": item["positive_outcome"],
            "negative_outcome": item["negative_outcome"],
            "scope_limits": item["scope_limits"],
            "open_questions": item["open_questions"],
            "safe_sibling_contrasts": contrasts,
            "evidence": evidence,
            "boundary_status": "candidate_only",
        })
    expected_pairs = {tuple(sorted(pair)) for pair in itertools.combinations(PILOT_A_CANDIDATES, 2)}
    actual_pairs = [tuple(sorted((item.get("candidate_a"), item.get("candidate_b")))) for item in raw_pairs]
    _require(len(raw_pairs) == 15 and len(set(actual_pairs)) == 15 and set(actual_pairs) == expected_pairs,
             "Pilot A boundary proposal must cover all 15 unordered pairs once")
    proposals = []
    for item in raw_pairs:
        _require(set(item) == {"candidate_a", "candidate_b", "decision", "rationale", "counterfactual", "independent_reasoning"},
                 "invalid boundary proposal fields")
        _require(item["decision"] in {"split", "merge", "uncertain"}, "invalid boundary proposal decision")
        for key in ("rationale", "counterfactual", "independent_reasoning"):
            _require(isinstance(item[key], str) and item[key].strip(), f"empty boundary field: {key}")
        proposals.append({
            **item,
            "reviewer_id": "codex_primary",
            "review_status": "preliminary_single_review",
            "source": "frozen_target_only",
            "counts_as_independent_blind_annotation": False,
        })
    payloads = {
        "candidate_packets.jsonl": _jsonl_bytes(packets),
        "boundary_preliminary.jsonl": _jsonl_bytes(proposals),
    }
    payloads["reviewer_bundle.json"] = _json_bytes({
        "packet_version": PACKET_VERSION,
        "case_id": CASE_ID,
        "graph_version": lock["graph_version"],
        "input_lock_sha256": _digest((directory.parent / "input_lock.json").read_bytes()),
        "review_instructions": (
            "请只凭冻结 target、v1 GT 与此证据包独立判断每个候选对 split/merge/uncertain，"
            "逐对写安全问题、结论、必要链及反事实。不要查看其他标注者的记录、boundary_preliminary、"
            "T4 transcript/finding/score/task 或任何 condition 表现。"
        ),
        "candidates": packets,
        "unordered_pairs": [
            {
                "candidate_a": a,
                "candidate_b": b,
                "security_question_a": next(item["security_question"] for item in packets if item["candidate_id"] == a),
                "security_question_b": next(item["security_question"] for item in packets if item["candidate_id"] == b),
            }
            for a, b in itertools.combinations(PILOT_A_CANDIDATES, 2)
        ],
    })
    anchor_by_id = {item["candidate_id"]: item["evidence"][0] for item in packets}
    payloads["review_form_template.jsonl"] = _jsonl_bytes([
        {
            "reviewer_id": "",
            "candidate_a": a,
            "candidate_b": b,
            "security_question_a": next(item["security_question"] for item in packets if item["candidate_id"] == a),
            "security_question_b": next(item["security_question"] for item in packets if item["candidate_id"] == b),
            "decision": "",
            "counterfactual": "",
            "rationale": "",
            "evidence_refs": [
                {**{key: anchor_by_id[a][key] for key in ("path", "line", "symbol", "excerpt", "excerpt_sha256")}, "role": "candidate_a"},
                {**{key: anchor_by_id[b][key] for key in ("path", "line", "symbol", "excerpt", "excerpt_sha256")}, "role": "candidate_b"},
            ],
        }
        for a, b in itertools.combinations(PILOT_A_CANDIDATES, 2)
    ])
    payloads["packet_manifest.json"] = _json_bytes({
        "packet_version": PACKET_VERSION,
        "case_id": CASE_ID,
        "graph_version": lock["graph_version"],
        "input_lock_sha256": _digest((directory.parent / "input_lock.json").read_bytes()),
        "source_spec_sha256": _digest(source_path.read_bytes()),
        "builder_sha256": _digest(Path(__file__).read_bytes()),
        "candidate_packets_sha256": _digest(payloads["candidate_packets.jsonl"]),
        "boundary_preliminary_sha256": _digest(payloads["boundary_preliminary.jsonl"]),
        "reviewer_bundle_sha256": _digest(payloads["reviewer_bundle.json"]),
        "review_form_template_sha256": _digest(payloads["review_form_template.jsonl"]),
        "candidate_count": 6,
        "unordered_pair_count": 15,
        "node_boundary_status": (
            "preliminary_single_review; preparer saw planning document with historical aggregate; "
            "does not count as independent blind annotation; double review and third adjudication pending"
        ),
    })
    return payloads


def build(directory: Path = PILOT_DIR) -> dict[str, Any]:
    _require(not directory.is_symlink(), "Pilot A directory must not be a symlink")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    payloads = render(directory)
    for name, data in payloads.items():
        path = directory / name
        _require(not path.is_symlink(), f"private packet file is a symlink: {name}")
        path.write_bytes(data)
        path.chmod(0o600)
    return verify(directory)


def verify(directory: Path = PILOT_DIR) -> dict[str, Any]:
    payloads = render(directory)
    for name, expected in payloads.items():
        path = directory / name
        _require(path.is_file() and not path.is_symlink() and path.read_bytes() == expected,
                 f"Pilot A packet changed or missing: {name}")
    return {
        "status": "verified_preliminary",
        "candidate_count": 6,
        "unordered_pair_count": 15,
        "input_lock_sha256": _digest((directory.parent / "input_lock.json").read_bytes()),
        "packet_manifest_sha256": _digest(payloads["packet_manifest.json"]),
        "independent_review_complete": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "verify"))
    args = parser.parse_args()
    try:
        result = build() if args.command == "build" else verify()
    except GraphValidationError as exc:
        parser.exit(1, f"Pilot A packet error: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
