"""离线 Hidden Opportunity Graph 输入锁定与结构校验；不参与 Agent runtime。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any

from experiments.emergent_coordination.harness.block_runner import tree_digest
from experiments.emergent_coordination.harness.cases import load_case


ROOT = Path(__file__).resolve().parents[1]
CASE_ID = "flowise_3_1_3_repository_v1"
GRAPH_VERSION = "graph-v1"
PILOT_B_GRAPH_VERSION = "graph-v2"
GRAPH_SCHEMA_VERSION = "1.0.0"
ANNOTATION_PROTOCOL_VERSION = "repository-v1-hidden-opportunity-graph-20260923"
PRIVATE_GRAPH_DIR = ROOT / "artifacts" / "hidden_opportunity_graph" / CASE_ID / GRAPH_VERSION
PILOT_B_GRAPH_DIR = PRIVATE_GRAPH_DIR.parent / PILOT_B_GRAPH_VERSION
PILOT_B_PREP_DIR = PRIVATE_GRAPH_DIR.parent / "pilot-b-prep-v1"
PROTOCOL_PATH = "docs/research/repository-v1-hidden-opportunity-graph-plan-20260923.md"
THREAT_MODEL_PATH = "docs/adr/0006-repository-v1-static-first-validation-boundary.md"
PILOT_A_CANDIDATES = [
    "R04_generic_credential_lookup_scope",
    "R05_openai_assistant_credential_lookup_scope",
    "R06_assistant_delete_credential_lookup_scope",
    "R20_tts_private_flow_credential_use",
    "NM04_scoped_credential_read",
    "R19_tts_abort_cross_operation",
]
OPPORTUNITY_TYPES = {
    "none", "thematic-only", "direct relation", "actionable cross-check", "strong dependency"
}
ACTIONABLE_TYPES = {"actionable cross-check", "strong dependency"}
ADJUDICATION_STATUSES = {"proposed", "agreed", "adjudicated", "uncertain", "rejected"}
NODE_STATUSES = {"scored_positive", "qualified_near_miss", "admitted_unscored", "unresolved"}
EFFECTS = {"validate", "refute", "narrow", "extend", "avoid_duplicate_search"}
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
NODE_ID_RE = re.compile(r"F[0-9]{3,}\Z")


class GraphValidationError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise GraphValidationError(message)


def _sha256(path: Path) -> str:
    _require(path.is_file(), f"missing file: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _object(value: Any, where: str, required: set[str], optional: set[str] | None = None) -> dict[str, Any]:
    _require(isinstance(value, dict), f"{where}: expected object")
    optional = optional or set()
    _require(required <= value.keys(), f"{where}: missing fields {sorted(required - value.keys())}")
    _require(value.keys() <= required | optional, f"{where}: unexpected fields {sorted(value.keys() - required - optional)}")
    return value


def _string(value: Any, where: str, *, nonempty: bool = True) -> str:
    _require(isinstance(value, str), f"{where}: expected string")
    if nonempty:
        _require(bool(value.strip()), f"{where}: empty string")
    return value


def _sha(value: Any, where: str) -> str:
    value = _string(value, where)
    _require(bool(SHA256_RE.fullmatch(value)), f"{where}: invalid SHA-256")
    return value


def _list(value: Any, where: str) -> list[Any]:
    _require(isinstance(value, list), f"{where}: expected array")
    return value


def _read_json(path: Path) -> dict[str, Any]:
    _require(path.is_file(), f"missing file: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise GraphValidationError(f"invalid JSON: {path}: {exc}") from exc
    _require(isinstance(value, dict), f"{path}: expected JSON object")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    _require(path.is_file(), f"missing file: {path}")
    records = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        _require(bool(line.strip()), f"{path}:{number}: blank JSONL line")
        try:
            value = json.loads(line)
        except ValueError as exc:
            raise GraphValidationError(f"{path}:{number}: invalid JSON: {exc}") from exc
        _require(isinstance(value, dict), f"{path}:{number}: expected JSON object")
        records.append(value)
    return records


def _relative_path(value: Any, where: str) -> str:
    value = _string(value, where)
    path = PurePosixPath(value)
    _require(not path.is_absolute() and value == path.as_posix() and ".." not in path.parts and "." not in path.parts,
             f"{where}: must be a normalized target-relative path")
    return value


def _target_file(target: Path, relative: str, where: str) -> Path:
    source = (target / relative).resolve()
    _require(source.is_relative_to(target.resolve()) and source.is_file(), f"{where}: target file missing or escapes target")
    return source


def _evidence(value: Any, where: str, target: Path, role: str | None = None) -> None:
    item = _object(value, where, {"path", "line", "symbol", "excerpt", "excerpt_sha256"}, {"role"})
    if role is not None:
        _require(item.get("role") == role, f"{where}: role must be {role}")
    elif "role" in item:
        _string(item["role"], f"{where}.role")
    relative = _relative_path(item["path"], f"{where}.path")
    line = item["line"]
    _require(type(line) is int and line >= 1, f"{where}.line: expected positive integer")
    _string(item["symbol"], f"{where}.symbol")
    excerpt = _string(item["excerpt"], f"{where}.excerpt")
    _require("\r" not in excerpt and not excerpt.startswith("\n"), f"{where}.excerpt: invalid line start")
    digest = _sha(item["excerpt_sha256"], f"{where}.excerpt_sha256")
    _require(hashlib.sha256(excerpt.encode("utf-8")).hexdigest() == digest, f"{where}: excerpt hash mismatch")
    source = _target_file(target, relative, where)
    content = source.read_text(encoding="utf-8")
    offsets = [match.start() for match in re.finditer(re.escape(excerpt), content)]
    _require(any(content.count("\n", 0, offset) + 1 == line for offset in offsets),
             f"{where}: excerpt not found at target line {line}")


def _safe_graph_dir(directory: Path, case: Any) -> Path:
    _require(directory.absolute() == directory.resolve(), "graph directory must not contain symlinks")
    directory = directory.resolve()
    forbidden = [case.target_root, case.evaluator_private_root, ROOT / "experiments" / "emergent_coordination" / "runs"]
    _require(not any(directory.is_relative_to(path.resolve()) or path.resolve().is_relative_to(directory) for path in forbidden),
             "graph directory overlaps target, frozen evaluator assets, or runs")
    return directory


def _check_graph_files(directory: Path) -> None:
    for name in (
        "input_lock.json", "graph_manifest.json", "nodes.jsonl", "edges.jsonl",
        "node_reviews.jsonl", "edge_reviews.jsonl", "adjudications.jsonl"
    ):
        _require(not (directory / name).is_symlink(), f"graph file must not be a symlink: {name}")


def _expected_graph_version(directory: Path, graph_version: str | None) -> str:
    version = graph_version or (PILOT_B_GRAPH_VERSION if directory.name == PILOT_B_GRAPH_VERSION else GRAPH_VERSION)
    _require(version in {GRAPH_VERSION, PILOT_B_GRAPH_VERSION}, f"unsupported graph version: {version}")
    return version


def _input_payload(graph_version: str = GRAPH_VERSION) -> dict[str, Any]:
    case = load_case(CASE_ID)
    manifest = case.manifest
    digests = manifest["digests"]
    target_digest = tree_digest(case.target_root)
    private_digest = tree_digest(case.evaluator_private_root)
    _require(target_digest == digests["target_tree_sha256"], "frozen target digest mismatch")
    _require(private_digest == digests["evaluator_private_tree_sha256"], "frozen evaluator-private digest mismatch")
    gt = _read_json(case.ground_truth_path)
    _require(gt["case_id"] == CASE_ID and gt["target_tree_sha256"] == target_digest, "GT target binding mismatch")
    _require(len(gt["roots"]) == 20 and len(gt["near_misses"]) == 5, "v1 GT count mismatch")
    siblings = _read_json(case.evaluator_private_root / "safe_siblings.json")
    _require(siblings["case_id"] == CASE_ID, "safe siblings case mismatch")
    root_ids = {item["id"] for item in gt["roots"]}
    near_ids = {item["id"] for item in gt["near_misses"]}
    _require(set(PILOT_A_CANDIDATES) <= root_ids | near_ids, "Pilot A candidate missing from v1 GT")
    files = {
        "case_manifest": f"experiments/emergent_coordination/manifests/{CASE_ID}.json",
        "ground_truth": f"experiments/emergent_coordination/evaluator_private/{CASE_ID}/ground_truth.json",
        "safe_siblings": f"experiments/emergent_coordination/evaluator_private/{CASE_ID}/safe_siblings.json",
        "validation_metadata": f"experiments/emergent_coordination/evaluator_private/{CASE_ID}/verification_metadata.json",
        "protocol": PROTOCOL_PATH,
        "threat_model": THREAT_MODEL_PATH,
    }
    pilot_scope = {"phase": "Pilot A", "candidate_gt_ids": PILOT_A_CANDIDATES, "nodes_not_yet_adjudicated": True}
    if graph_version == PILOT_B_GRAPH_VERSION:
        packet_path = PILOT_B_PREP_DIR / "packet_manifest.json"
        packet = _read_json(packet_path)
        _require(packet["case_id"] == CASE_ID and packet["candidate_count"] == 21
                 and packet["annotation_status"] == "ungraded_candidate_pool",
                 "Pilot B candidate packet is not locked")
        pilot_scope = {
            "phase": "Pilot A + Pilot B",
            "pilot_a_graph_manifest_sha256": _sha256(PRIVATE_GRAPH_DIR / "graph_manifest.json"),
            "pilot_b_candidate_packet_sha256": _sha256(packet_path),
            "selection_status": "pending_independent_node_qc",
        }
    return {
        "input_lock_schema_version": "1.0.0",
        "case_id": CASE_ID,
        "graph_version": graph_version,
        "graph_schema_version": GRAPH_SCHEMA_VERSION,
        "annotation_protocol_version": ANNOTATION_PROTOCOL_VERSION,
        "target_sha256": target_digest,
        "evaluator_private_tree_sha256": private_digest,
        "gt_generation": gt["version"],
        "files": {name: {"path": path, "sha256": _sha256(ROOT / path)} for name, path in files.items()},
        "node_admission_rules": (
            "bounded independent security question; split by distinct invariant, independently decidable truth, "
            "and independent source-to-sink/guard/ownership/reachability reasoning; merge root variants"
        ),
        "pilot_scope": pilot_scope,
        "blindness_boundary": "frozen source, v1 GT, safe siblings, validation metadata, approved threat model only",
    }


def _json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def initialize_graph(directory: Path = PRIVATE_GRAPH_DIR, *, graph_version: str | None = None) -> Path:
    case = load_case(CASE_ID)
    directory = _safe_graph_dir(directory, case)
    version = _expected_graph_version(directory, graph_version)
    payload = _input_payload(version)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    _check_graph_files(directory)
    lock_path = directory / "input_lock.json"
    if lock_path.exists():
        _require(lock_path.read_bytes() == _json_bytes(payload), "existing input lock differs; use a new graph version")
    else:
        lock_path.write_bytes(_json_bytes(payload))
    lock_path.chmod(0o600)
    for name in ("nodes.jsonl", "edges.jsonl", "node_reviews.jsonl", "edge_reviews.jsonl", "adjudications.jsonl"):
        path = directory / name
        if not path.exists():
            path.touch(mode=0o600)
    manifest_path = directory / "graph_manifest.json"
    if not manifest_path.exists():
        manifest_path.write_bytes(_json_bytes({
            "graph_schema_version": GRAPH_SCHEMA_VERSION,
            "graph_version": version,
            "case_id": CASE_ID,
            "target_sha256": payload["target_sha256"],
            "gt_generation": payload["gt_generation"],
            "gt_sha256": payload["files"]["ground_truth"]["sha256"],
            "safe_sibling_sha256": payload["files"]["safe_siblings"]["sha256"],
            "annotation_protocol_version": ANNOTATION_PROTOCOL_VERSION,
            "input_lock_sha256": _sha256(lock_path),
            "nodes_sha256": _sha256(directory / "nodes.jsonl"),
            "edges_sha256": _sha256(directory / "edges.jsonl"),
            "node_reviews_sha256": _sha256(directory / "node_reviews.jsonl"),
            "edge_reviews_sha256": _sha256(directory / "edge_reviews.jsonl"),
            "adjudications_sha256": _sha256(directory / "adjudications.jsonl"),
            "adjudication_date": None,
            "adjudication_status": "draft",
        }))
    manifest_path.chmod(0o600)
    validate_graph(directory, graph_version=version)
    return directory


def stamp_draft(directory: Path = PRIVATE_GRAPH_DIR, *, graph_version: str | None = None) -> dict[str, Any]:
    """Record current draft file hashes after an annotation batch; never rewrite a frozen graph."""
    case = load_case(CASE_ID)
    directory = _safe_graph_dir(directory, case)
    _check_graph_files(directory)
    version = _expected_graph_version(directory, graph_version)
    _require(_read_json(directory / "input_lock.json") == _input_payload(version), "input lock changed or stale")
    manifest_path = directory / "graph_manifest.json"
    manifest = _read_json(manifest_path)
    _require(manifest.get("adjudication_status") == "draft", "cannot stamp a frozen graph")
    for key, filename in (
        ("nodes_sha256", "nodes.jsonl"),
        ("edges_sha256", "edges.jsonl"),
        ("node_reviews_sha256", "node_reviews.jsonl"),
        ("edge_reviews_sha256", "edge_reviews.jsonl"),
        ("adjudications_sha256", "adjudications.jsonl"),
    ):
        manifest[key] = _sha256(directory / filename)
    manifest_path.write_bytes(_json_bytes(manifest))
    manifest_path.chmod(0o600)
    return validate_graph(directory, graph_version=version)


def _validate_node(value: Any, where: str, target: Path, root_ids: set[str], near_ids: set[str]) -> str:
    node = _object(value, where, {
        "node_id", "security_question", "code_scope", "invariant", "boundary_rationale", "evidence_refs",
        "truth_status", "gt_root_ids", "adjudication_status", "potential_artifact"
    }, {"near_miss_ids", "uncertainty_note"})
    node_id = _string(node["node_id"], f"{where}.node_id")
    _require(bool(NODE_ID_RE.fullmatch(node_id)), f"{where}: invalid node ID")
    for key in ("security_question", "invariant", "boundary_rationale", "potential_artifact"):
        _string(node[key], f"{where}.{key}")
    scope = _list(node["code_scope"], f"{where}.code_scope")
    _require(bool(scope), f"{where}: empty code scope")
    for item in scope:
        _target_file(target, _relative_path(item, f"{where}.code_scope"), where)
    refs = _list(node["evidence_refs"], f"{where}.evidence_refs")
    _require(bool(refs), f"{where}: no evidence refs")
    for i, item in enumerate(refs):
        _evidence(item, f"{where}.evidence_refs[{i}]", target)
    _require(isinstance(node["truth_status"], str) and node["truth_status"] in NODE_STATUSES,
             f"{where}: invalid truth status")
    _require(isinstance(node["adjudication_status"], str) and node["adjudication_status"] in ADJUDICATION_STATUSES,
             f"{where}: invalid adjudication status")
    ids = _list(node["gt_root_ids"], f"{where}.gt_root_ids")
    _require(all(isinstance(item, str) and item in root_ids for item in ids) and len(ids) == len(set(ids)),
             f"{where}: invalid GT root mapping")
    near = _list(node.get("near_miss_ids", []), f"{where}.near_miss_ids")
    _require(all(isinstance(item, str) and item in near_ids for item in near) and len(near) == len(set(near)),
             f"{where}: invalid near-miss mapping")
    if node["truth_status"] == "scored_positive":
        _require(bool(ids), f"{where}: scored positive needs GT root")
    if node["truth_status"] == "qualified_near_miss":
        _require(bool(near), f"{where}: qualified near miss needs near-miss ID")
    if node["adjudication_status"] == "uncertain":
        _string(node.get("uncertainty_note"), f"{where}.uncertainty_note")
    return node_id


def _validate_edge(value: Any, where: str, target: Path, node_ids: set[str], graph_version: str) -> tuple[str, str]:
    edge = _object(value, where, {
        "edge_id", "source_node", "target_node", "direction", "opportunity_type", "mechanisms", "source_artifact",
        "target_claim", "expected_effect", "bounded_check", "evidence", "rationale", "confidence",
        "adjudication_status", "reviewer_ids", "uncertainty_note"
    })
    source, destination = edge["source_node"], edge["target_node"]
    _require(isinstance(source, str) and isinstance(destination, str), f"{where}: endpoints must be node IDs")
    _require(source in node_ids and destination in node_ids and source != destination, f"{where}: invalid endpoint or self-edge")
    _require(edge["edge_id"] == f"{graph_version}:{source}:{destination}", f"{where}: edge ID mismatch")
    _require(edge["direction"] == "source_to_target", f"{where}: invalid direction")
    category = edge["opportunity_type"]
    _require(isinstance(category, str) and category in OPPORTUNITY_TYPES, f"{where}: invalid opportunity type")
    _require(isinstance(edge["adjudication_status"], str) and edge["adjudication_status"] in ADJUDICATION_STATUSES,
             f"{where}: invalid adjudication status")
    _require(isinstance(edge["confidence"], str) and edge["confidence"] in {"high", "medium", "low"},
             f"{where}: invalid confidence")
    _string(edge["rationale"], f"{where}.rationale")
    mechanisms = _list(edge["mechanisms"], f"{where}.mechanisms")
    _require(all(isinstance(item, str) and item.strip() for item in mechanisms) and len(mechanisms) == len(set(mechanisms)),
             f"{where}: invalid mechanisms")
    effects = _list(edge["expected_effect"], f"{where}.expected_effect")
    _require(all(isinstance(item, str) and item in EFFECTS for item in effects) and len(effects) == len(set(effects)),
             f"{where}: invalid expected effects")
    reviewers = _list(edge["reviewer_ids"], f"{where}.reviewer_ids")
    _require(all(isinstance(item, str) and item.strip() for item in reviewers) and len(reviewers) == len(set(reviewers)),
             f"{where}: invalid reviewer IDs")
    refs = _list(edge["evidence"], f"{where}.evidence")
    for i, item in enumerate(refs):
        _evidence(item, f"{where}.evidence[{i}]", target)
    if category != "none":
        _require({"source", "target"} <= {item.get("role") for item in refs}, f"{where}: missing A/B evidence")
    if category in ACTIONABLE_TYPES:
        for key in ("source_artifact", "target_claim", "bounded_check"):
            _string(edge[key], f"{where}.{key}")
        _require(bool(effects), f"{where}: actionable edge needs expected effect")
    else:
        for key in ("source_artifact", "target_claim", "bounded_check"):
            _string(edge[key], f"{where}.{key}", nonempty=False)
    if edge["adjudication_status"] == "uncertain":
        _string(edge["uncertainty_note"], f"{where}.uncertainty_note")
    elif edge["uncertainty_note"] is not None:
        _string(edge["uncertainty_note"], f"{where}.uncertainty_note")
    return source, destination


def _validate_review_logs(directory: Path, node_ids: set[str], target: Path, graph_version: str) -> None:
    node_keys = {
        "reviewer_id", "candidate_a", "candidate_b", "security_question_a", "security_question_b",
        "decision", "counterfactual", "rationale", "evidence_refs"
    }
    edge_keys = {
        "reviewer_id", "source_node", "target_node", "opportunity_type", "mechanisms", "source_artifact",
        "target_claim", "expected_effect", "bounded_check", "evidence", "rationale", "confidence", "uncertainty_note"
    }
    adjudication_keys = {"kind", "item_id", "adjudicator_id", "decision", "rationale", "reviewer_ids"}
    for i, record in enumerate(_read_jsonl(directory / "node_reviews.jsonl")):
        where = f"node_reviews[{i}]"
        _object(record, where, node_keys, {"uncertainty_note"})
        for key in ("reviewer_id", "candidate_a", "candidate_b", "security_question_a", "security_question_b",
                    "counterfactual", "rationale"):
            _string(record[key], f"{where}.{key}")
        _require(record["candidate_a"] != record["candidate_b"]
                 and isinstance(record["decision"], str)
                 and record["decision"] in {"split", "merge", "uncertain"},
                 f"{where}: invalid node decision")
        refs = _list(record["evidence_refs"], f"{where}.evidence_refs")
        _require(bool(refs), f"{where}: missing source evidence")
        for j, item in enumerate(refs):
            _evidence(item, f"{where}.evidence_refs[{j}]", target)
    for i, record in enumerate(_read_jsonl(directory / "edge_reviews.jsonl")):
        where = f"edge_reviews[{i}]"
        _object(record, where, edge_keys)
        _string(record["reviewer_id"], f"{where}.reviewer_id")
        final_shape = {key: value for key, value in record.items() if key != "reviewer_id"}
        final_shape.update({
            "edge_id": f"{graph_version}:{record['source_node']}:{record['target_node']}",
            "direction": "source_to_target",
            "adjudication_status": "proposed",
            "reviewer_ids": [record["reviewer_id"]],
        })
        _validate_edge(final_shape, where, target, node_ids, graph_version)
    for i, record in enumerate(_read_jsonl(directory / "adjudications.jsonl")):
        where = f"adjudications[{i}]"
        _object(record, where, adjudication_keys, {"uncertainty_note"})
        _require(isinstance(record["kind"], str) and record["kind"] in {"node_boundary", "edge"},
                 f"{where}: invalid kind")
        for key in ("item_id", "adjudicator_id", "decision", "rationale"):
            _string(record[key], f"{where}.{key}")
        reviewers = _list(record["reviewer_ids"], f"{where}.reviewer_ids")
        _require(all(isinstance(x, str) and x.strip() for x in reviewers) and len(reviewers) == len(set(reviewers)),
                 f"{where}: invalid reviewers")


def validate_graph(directory: Path = PRIVATE_GRAPH_DIR, *, graph_version: str | None = None) -> dict[str, Any]:
    case = load_case(CASE_ID)
    directory = _safe_graph_dir(directory, case)
    version = _expected_graph_version(directory, graph_version)
    _check_graph_files(directory)
    lock = _read_json(directory / "input_lock.json")
    _require(lock == _input_payload(version), "input lock no longer matches frozen inputs or protocol")
    manifest = _object(_read_json(directory / "graph_manifest.json"), "graph_manifest", {
        "graph_schema_version", "graph_version", "case_id", "target_sha256", "gt_generation", "gt_sha256",
        "safe_sibling_sha256", "annotation_protocol_version", "input_lock_sha256", "nodes_sha256", "edges_sha256",
        "node_reviews_sha256", "edge_reviews_sha256", "adjudications_sha256",
        "adjudication_date", "adjudication_status"
    })
    for key, expected in {
        "graph_schema_version": GRAPH_SCHEMA_VERSION,
        "graph_version": version,
        "case_id": CASE_ID,
        "target_sha256": lock["target_sha256"],
        "gt_generation": lock["gt_generation"],
        "gt_sha256": lock["files"]["ground_truth"]["sha256"],
        "safe_sibling_sha256": lock["files"]["safe_siblings"]["sha256"],
        "annotation_protocol_version": ANNOTATION_PROTOCOL_VERSION,
        "input_lock_sha256": _sha256(directory / "input_lock.json"),
        "nodes_sha256": _sha256(directory / "nodes.jsonl"),
        "edges_sha256": _sha256(directory / "edges.jsonl"),
        "node_reviews_sha256": _sha256(directory / "node_reviews.jsonl"),
        "edge_reviews_sha256": _sha256(directory / "edge_reviews.jsonl"),
        "adjudications_sha256": _sha256(directory / "adjudications.jsonl"),
    }.items():
        _require(manifest[key] == expected, f"graph manifest {key} mismatch")
    _require(isinstance(manifest["adjudication_status"], str)
             and manifest["adjudication_status"] in {"draft", "frozen"}, "invalid graph status")
    if manifest["adjudication_status"] == "frozen":
        _require(isinstance(manifest["adjudication_date"], str), "frozen graph requires adjudication date")
        try:
            date.fromisoformat(manifest["adjudication_date"])
        except (TypeError, ValueError) as exc:
            raise GraphValidationError("invalid adjudication date") from exc
    else:
        _require(manifest["adjudication_date"] is None, "draft graph cannot have adjudication date")
    gt = _read_json(case.ground_truth_path)
    roots = {item["id"] for item in gt["roots"]}
    near = {item["id"] for item in gt["near_misses"]}
    nodes = _read_jsonl(directory / "nodes.jsonl")
    node_ids = [_validate_node(item, f"nodes[{i}]", case.target_root, roots, near) for i, item in enumerate(nodes)]
    _require(len(node_ids) == len(set(node_ids)), "duplicate node ID")
    edges = _read_jsonl(directory / "edges.jsonl")
    actual = [_validate_edge(item, f"edges[{i}]", case.target_root, set(node_ids), version) for i, item in enumerate(edges)]
    expected = {(a, b) for a in node_ids for b in node_ids if a != b}
    _require(len(actual) == len(set(actual)) and set(actual) == expected,
             f"directed pair matrix incomplete or duplicated: expected {len(expected)}, found {len(actual)}")
    _validate_review_logs(directory, set(node_ids), case.target_root, version)
    if manifest["adjudication_status"] == "frozen":
        _require(len(nodes) >= 2, "cannot freeze an empty graph")
        _require(all(item["adjudication_status"] == "adjudicated" for item in nodes), "frozen graph has unadjudicated nodes")
        _require(all(item["adjudication_status"] in {"adjudicated", "uncertain"} for item in edges),
                 "frozen graph has unadjudicated edges")
    return {
        "status": "valid_draft" if manifest["adjudication_status"] == "draft" else "valid_frozen",
        "case_id": CASE_ID,
        "graph_version": version,
        "node_count": len(nodes),
        "directed_pair_count": len(edges),
        "expected_directed_pair_count": len(expected),
        "ready_for_node_annotation": manifest["adjudication_status"] == "draft",
        "human_qc_required": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("init", "stamp-draft", "validate"))
    parser.add_argument("--graph-version", choices=(GRAPH_VERSION, PILOT_B_GRAPH_VERSION), default=GRAPH_VERSION)
    args = parser.parse_args()
    directory = PRIVATE_GRAPH_DIR if args.graph_version == GRAPH_VERSION else PILOT_B_GRAPH_DIR
    try:
        if args.command == "init":
            initialize_graph(directory, graph_version=args.graph_version)
        result = (stamp_draft(directory, graph_version=args.graph_version) if args.command == "stamp-draft"
                  else validate_graph(directory, graph_version=args.graph_version))
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    except GraphValidationError as exc:
        parser.exit(1, f"graph validation failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
