#!/usr/bin/env python3
"""Build and mechanically smoke-test the sampled HOG blind reviewer packet."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.sample_hidden_opportunity_density import CASE, OUT, ROOT, json_bytes, jsonl_bytes, load_json, load_jsonl, sha

SOURCE_RUBRIC = CASE / "expansion-edge-batches-v1/batch-01/packet/reviewer_rubric.json"
PACKET = OUT / "packet"
TARGET = "experiments/emergent_coordination/repositories/flowise_3_1_3_repository_v1"


def render() -> dict[str, bytes]:
    prereg = load_json(OUT / "sampling_prereg.json")
    rows = load_jsonl(OUT / "sampled_pairs.jsonl")
    nodes = load_jsonl(CASE / "expansion-node-set-v2/nodes_frozen.jsonl")
    source = load_json(SOURCE_RUBRIC)
    assert len(rows) == 100 and len(nodes) == 27
    assert sha((OUT / "sampled_pairs.jsonl").read_bytes()) == prereg["sample_manifest_sha256"]
    # Preserve all substantive rubric text; only replace administrative context and
    # restrict source access to the frozen target. No historical labels are read.
    rubric = {k: source[k] for k in (
        "rubric_version", "decision_order", "mechanisms_examples", "mechanisms_examples_open_vocabulary",
        "record_requirements", "taxonomy",
    )}
    rubric.update({
        "annotation_status": "sampled_density_formal_double_blind",
        "structural_scope": "A→B 表示 A 可产出的具体信息潜在改变 B 的判断、最小验证路径或必要搜索工作；不要求某次 agent 真实传递或利用，也不以 runtime 工具、消息通道、visibility、预算为纳入条件。仅按冻结节点语义与源码做静态优先的有界验证推理。",
        "allowed_context": {
            "packet_files": ["reviewer_rubric.json", "reviewer_bundle.json", "review_form_template.jsonl", "packet_manifest.json"],
            "target_root": TARGET, "output": "reviews/reviewer_<a_or_b>.jsonl",
            "access_log": "reviews/reviewer_<a_or_b>_access.json",
        },
        "blindness": "只读本 packet 四文件及冻结 target 源码树。不得读取历史 graph/edge 标注、Pilot、Batch、smoke、QC、裁决、docs、scripts、tests、runs、其他 reviewer 输出或 evaluator-private 文件。不得做全仓检索；源码检索仅限 target 树。",
        "primary_boundary": "actionable cross-check 或 strong dependency = actionable；其他三类 = non-actionable。先判 binary，再填五类；仅 binary 边界本身证据不足时填 uncertainty_note。",
        "notice": "本包只用于 100 对 sampled opportunity-density estimation；每对均重新独立盲标。",
    })
    allowed_node_keys = ("node_id", "security_question", "invariant", "potential_artifact", "code_scope", "evidence_refs")
    safe_nodes = [{k: n[k] for k in allowed_node_keys} for n in nodes]
    bundle = {
        "packet_version": "sampled-opportunity-review-v1",
        "case_id": "flowise_3_1_3_repository_v1",
        "sample_manifest_sha256": prereg["sample_manifest_sha256"],
        "node_set_version": "expansion-node-set-v2",
        "nodes": safe_nodes,
        "directed_pairs": [{"source_node": r["source_node"], "target_node": r["target_node"]} for r in rows],
    }
    template = [{
        "reviewer_id": "", "source_node": r["source_node"], "target_node": r["target_node"],
        "opportunity_type": "", "mechanisms": [], "source_artifact": "", "target_claim": "",
        "expected_effect": [], "bounded_check": "", "evidence": [], "rationale": "",
        "confidence": "", "uncertainty_note": None,
    } for r in rows]
    data = {
        "reviewer_rubric.json": json_bytes(rubric),
        "reviewer_bundle.json": json_bytes(bundle),
        "review_form_template.jsonl": jsonl_bytes(template),
    }
    manifest = {
        "packet_version": "sampled-opportunity-review-v1",
        "status": "frozen_label_blind_packet",
        "pair_count": 100,
        "sample_manifest_sha256": prereg["sample_manifest_sha256"],
        "source_rubric_sha256": sha(SOURCE_RUBRIC.read_bytes()),
        "substantive_rubric_fields_copied_verbatim": [
            "rubric_version", "decision_order", "mechanisms_examples",
            "mechanisms_examples_open_vocabulary", "record_requirements", "taxonomy",
        ],
        "scope_change": "Administrative scope narrowed to sampled pairs and frozen target source; no taxonomy, decision rule, or threshold calibration change.",
        "packet_sha256": {name: sha(content) for name, content in data.items()},
    }
    data["packet_manifest.json"] = json_bytes(manifest)
    return data


def smoke(data: dict[str, bytes]) -> dict:
    bundle = json.loads(data["reviewer_bundle.json"])
    rubric = json.loads(data["reviewer_rubric.json"])
    manifest = json.loads(data["packet_manifest.json"])
    template = [json.loads(line) for line in data["review_form_template.jsonl"].splitlines()]
    forbidden = {"gt_root_ids", "truth_status", "adjudication_status", "boundary_rationale", "opportunity_type"}
    assert len(bundle["directed_pairs"]) == len(template) == manifest["pair_count"] == 100
    assert len({(p["source_node"], p["target_node"]) for p in bundle["directed_pairs"]}) == 100
    assert all(not (set(n) & forbidden) for n in bundle["nodes"])
    assert all(row["opportunity_type"] == "" for row in template)
    assert all(sha(data[name]) == digest for name, digest in manifest["packet_sha256"].items())
    assert rubric["taxonomy"] == load_json(SOURCE_RUBRIC)["taxonomy"]
    assert rubric["decision_order"] == load_json(SOURCE_RUBRIC)["decision_order"]
    assert rubric["record_requirements"] == load_json(SOURCE_RUBRIC)["record_requirements"]
    packet_paths = {f"artifacts/hidden_opportunity_graph/flowise_3_1_3_repository_v1/sampled-opportunity-density-v1/packet/{n}" for n in data}
    own_a = "artifacts/hidden_opportunity_graph/flowise_3_1_3_repository_v1/sampled-opportunity-density-v1/reviews/reviewer_a.jsonl"
    target_example = f"{TARGET}/packages/server/src/index.ts"
    def access_ok(log: dict) -> bool:
        return (set(log) == {"reviewer_id", "files_read"}
                and log["reviewer_id"] == "sampled-density-reviewer-a"
                and isinstance(log["files_read"], list)
                and packet_paths <= set(log["files_read"])
                and all(p in packet_paths | {own_a} or p.startswith(TARGET + "/") for p in log["files_read"]))
    synthetic_access = {"reviewer_id": "sampled-density-reviewer-a", "files_read": sorted(packet_paths | {own_a, target_example})}
    assert access_ok(synthetic_access)
    assert not access_ok({**synthetic_access, "files_read": synthetic_access["files_read"] + ["docs/research/forbidden.md"]})
    assert not access_ok({**synthetic_access, "reviewer_id": "sampled-density-reviewer-b"})
    assert not any(word in data["reviewer_bundle.json"] for word in (b"batch-03", b"reviewer_a", b"adjudication_summary", b"graph-v2:"))
    return {
        "status": "synthetic_schema_and_blindness_smoke_passed",
        "scope": "mechanical packet/schema/access-policy check; no semantic labels or production review",
        "checked_pair_count": 2,
        "sample_records_have_exact_template_keys": len(set(template[0]) ^ set(template[1])) == 0,
        "bundle_has_no_historical_structural_labels": True,
        "access_log_schema_and_scope_positive_negative_controls_passed": True,
        "source_rubric_taxonomy_and_decision_rules_unchanged": True,
        "packet_manifest_sha256": sha(data["packet_manifest.json"]),
    }


def main() -> None:
    data = render()
    report = smoke(data)
    PACKET.mkdir(parents=True, exist_ok=True)
    for name, content in data.items():
        path = PACKET / name
        if path.exists():
            assert path.read_bytes() == content, f"frozen packet changed: {path}"
        else:
            path.write_bytes(content)
    path = OUT / "smoke_qc.json"
    content = json_bytes(report)
    if path.exists():
        assert path.read_bytes() == content, "smoke report changed"
    else:
        path.write_bytes(content)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
