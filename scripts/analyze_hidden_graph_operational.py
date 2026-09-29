#!/usr/bin/env python3
"""Offline condition-realizability and retrospective run mapping for graph-v2.

This script is deliberately outside the runtime harness.  It reads the frozen
graph and the three already-frozen T4 post-sync runs, uses only ACTIVE /
RESULT_SYNC-preceding evidence for task/finding coverage, writes that mapping,
and only then writes the POST_SYNC manual review.  It never changes graph
nodes or edges and never reads evaluator-private files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
GRAPH_DIR = ROOT / "artifacts/hidden_opportunity_graph/flowise_3_1_3_repository_v1/graph-v2"
RUNS_DIR = ROOT / "experiments/emergent_coordination/runs/t4-post-sync-window-v2-192p"
OUT_DIR = GRAPH_DIR / "operational"
RUN_NAMES = ("matched-seed-01", "matched-seed-02", "matched-seed-03")
CONDITIONS = ("S1", "P4", "B4", "T4", "M4")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    os.chmod(path, 0o600)


def normal_path(path: str | None) -> str:
    if not path:
        return ""
    return path.removeprefix("target/").removeprefix("/work/target/")


def path_matches(path: str, scope: str) -> bool:
    path, scope = normal_path(path), normal_path(scope)
    return bool(path and scope and (path == scope or path.startswith(scope + "/") or scope.startswith(path + "/")))


def load_graph() -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    manifest = read_json(GRAPH_DIR / "graph_manifest.json")
    if manifest.get("adjudication_status") != "frozen":
        raise RuntimeError("graph-v2 is not frozen")
    nodes = {row["node_id"]: row for row in read_jsonl(GRAPH_DIR / "nodes.jsonl")}
    edges = {row["edge_id"]: row for row in read_jsonl(GRAPH_DIR / "edges.jsonl")}
    if len(nodes) != 16 or len(edges) != 240:
        raise RuntimeError(f"unexpected frozen graph dimensions: {len(nodes)} nodes/{len(edges)} edges")
    return manifest, nodes, edges


def actionable_edges(edges: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        (e for e in edges.values() if e["opportunity_type"] in {"actionable cross-check", "strong dependency"}),
        key=lambda e: e["edge_id"],
    )


CONTRACTS: dict[str, dict[str, Any]] = {
    "S1": {
        "tools": ["read_file", "list_files", "run_shell", "targeted_local_tests"],
        "channel": "none",
        "visibility": "one agent private target; no other agent context",
        "permits": "single-agent contract; no cross-agent permit or handoff",
        "lifecycle": "ACTIVE only; no cross-agent RESULT_SYNC",
        "minimum_transfer": "not available across agents",
        "status": "no",
        "reason": "S1 has one agent; cross-agent edge instances do not exist. Single-agent internal reuse is reported separately.",
        "basis": "experiments/emergent_coordination/README.md §S — Single",
    },
    "P4": {
        "tools": ["read_file", "list_files", "run_shell", "targeted_local_tests"],
        "channel": "none",
        "visibility": "four isolated private targets; no shared directory",
        "permits": "shared team permit pool but no transfer primitive",
        "lifecycle": "ACTIVE only; no task board or RESULT_SYNC contract",
        "minimum_transfer": "no path from source artifact to another agent",
        "status": "no",
        "reason": "P4 agents cannot publish or receive another agent's artifact under the parallel contract.",
        "basis": "experiments/emergent_coordination/README.md §P — Independent parallel",
    },
    "B4": {
        "tools": ["read_file", "list_files", "run_shell", "shared_list", "shared_read", "shared_mkdir", "shared_create"],
        "channel": "generic persistent /shared filesystem only; no message/task/claim semantics",
        "visibility": "all agents can read shared files after a source writes them; private targets remain isolated",
        "permits": "shared team permit pool; shared-store calls consume normal agent permits",
        "lifecycle": "ACTIVE throughout; no required barrier or typed result handoff",
        "minimum_transfer": "source can create an append-friendly artifact; target can list/read it",
        "status": "yes",
        "reason": "The generic shared substrate can carry a source artifact and a target can execute the bounded check; no action is inferred from availability.",
        "basis": "experiments/emergent_coordination/README.md §B — Raw blackboard",
    },
    "T4": {
        "tools": ["read_file", "list_files", "run_shell", "create_task", "claim_task", "complete_task", "list_tasks"],
        "channel": "typed task result plus evidence references; result_sync_v1 snapshot",
        "visibility": "completed task result and refs become visible to other agents at RESULT_SYNC",
        "permits": "192 team permits; T4 v2 reserves 4 post-sync permits per eligible agent inside the cap",
        "lifecycle": "ACTIVE task claim/complete, then exactly-once RESULT_SYNC and optional POST_SYNC window",
        "minimum_transfer": "source completes a task with result/evidence refs; target sees it and may run the bounded check",
        "status": "yes",
        "reason": "T4's typed task lifecycle and RESULT_SYNC provide a contract path for every structural actionable artifact.",
        "basis": "experiments/emergent_coordination/README.md §T — Structured team; t4_flowise_post_sync_window_v2.json",
    },
    "M4": {
        "tools": ["read_file", "list_files", "run_shell", "manager_create_task", "manager_list_tasks", "complete_task"],
        "channel": "manager↔worker task/report channel; no worker-to-worker channel",
        "visibility": "manager sees worker reports; a worker receives only its manager assignment/report",
        "permits": "shared team permit pool; manager mediation consumes the same team budget",
        "lifecycle": "manager assigns/reassigns; worker reports; manager may pass a derived check to another worker",
        "minimum_transfer": "source report reaches manager, who assigns the target check to a worker",
        "status": "yes",
        "reason": "M4 can relay a source artifact through the manager, although the source and target workers cannot communicate directly.",
        "basis": "experiments/emergent_coordination/README.md §M — Manager–worker",
    },
}


# These are conservative, evidence-first mappings.  A task is mapped only when
# its completed-task evidence refs include a file in the frozen node scope.
# Broad task descriptions and incidental files read during exploration do not
# create a mapping.  Unmapped rows are intentionally retained as out_of_graph.
CURATED_TASK_NODES: dict[tuple[str, str], list[str]] = {
    ("matched-seed-01", "task_a7ebc955d0"): ["F001", "F004"],
    ("matched-seed-02", "task_3454000583"): ["F011", "F012"],
    ("matched-seed-03", "task_23fcf052c9"): ["F011", "F012"],
    ("matched-seed-03", "task_e97e04f9e3"): ["F002"],
}

CURATED_FINDING_NODES: dict[tuple[str, str], list[str]] = {
    ("matched-seed-01", "agent_001"): ["F001", "F004"],
    ("matched-seed-03", "agent_002"): ["F011", "F012"],
    ("matched-seed-03", "agent_004"): ["F002"],
}


# The manual semantic review is intentionally separate from the structural
# graph.  Values below are taken from the frozen T4 v2 three-seed review; the
# script attaches the event/transcript provenance observed in the run itself.
POST_SYNC_MANUAL: dict[tuple[str, str], dict[str, Any]] = {
    ("matched-seed-01", "agent_001"): {"discovery": "thematic_uncertain", "lead": False, "verification": False, "judgment": "none", "claim_adoption": False, "note": "泛称 synchronized artifacts；未形成 graph-specific relation。"},
    ("matched-seed-01", "agent_002"): {"discovery": "thematic_only", "lead": False, "verification": False, "judgment": "none", "claim_adoption": False, "note": "泛称 agent_001/agent_003 主题；无可区分验证目标。"},
    ("matched-seed-01", "agent_003"): {"discovery": "none", "lead": False, "verification": False, "judgment": "none", "claim_adoption": False, "note": "泛称 OAuth2/TTS/webhook；未形成 relation。"},
    ("matched-seed-01", "agent_004"): {"discovery": "none", "lead": False, "verification": False, "judgment": "none", "claim_adoption": False, "note": "泛称 enterprise RBAC/OAuth2/TTS；未形成 relation。"},
    ("matched-seed-02", "agent_001"): {"discovery": "none", "lead": False, "verification": False, "judgment": "none", "claim_adoption": False, "note": "泛称 components/server/webhook areas；未形成 relation。"},
    ("matched-seed-02", "agent_002"): {"discovery": "direct_relation", "lead": True, "verification": True, "judgment": "strengthened", "claim_adoption": True, "note": "读取 feedback controller 后确认核心 IDOR 并形成 finding；附带 ID 枚举措辞过强。"},
    ("matched-seed-02", "agent_003"): {"discovery": "none", "lead": False, "verification": False, "judgment": "none", "claim_adoption": False, "note": "未实质讨论 foreign result。"},
    ("matched-seed-02", "agent_004"): {"discovery": "direct_relation", "lead": False, "verification": False, "judgment": "none", "claim_adoption": False, "note": "同一 webhook auth control 的 applicability 区分；没有 actionable lead。"},
    ("matched-seed-03", "agent_001"): {"discovery": "none", "lead": False, "verification": False, "judgment": "none", "claim_adoption": False, "note": "泛称 components/storage/uploads；未形成 relation。"},
    ("matched-seed-03", "agent_002"): {"discovery": "direct_relation", "lead": True, "verification": True, "judgment": "narrowed", "claim_adoption": True, "note": "读取 get-upload-file controller 后下调公开 traversal 可达性，保留条件性 guard gap。"},
    ("matched-seed-03", "agent_003"): {"discovery": "none", "lead": False, "verification": False, "judgment": "none", "claim_adoption": False, "note": "仅非重复性说明；未形成 direct relation。"},
    ("matched-seed-03", "agent_004"): {"discovery": "none", "lead": False, "verification": False, "judgment": "none", "claim_adoption": False, "note": "泛称 feedback/node-load/storage findings；未形成 relation。"},
}


def event_index(run_dir: Path) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], int]:
    events = read_jsonl(run_dir / "logs/events.jsonl")
    by_id = {e["event_id"]: e for e in events}
    triggers = [e for e in events if e["event_type"] == "result_sync_triggered"]
    if len(triggers) != 1:
        raise RuntimeError(f"{run_dir.name}: expected exactly one result_sync_triggered")
    return events, by_id, triggers[0]["sequence"]


def ref_paths(refs: Iterable[str], by_id: dict[str, dict[str, Any]]) -> list[str]:
    paths: list[str] = []
    for ref in refs:
        event = by_id.get(ref)
        if event and event.get("event_type") == "file_read":
            path = normal_path((event.get("payload") or {}).get("path"))
            if path:
                paths.append(path)
    return sorted(dict.fromkeys(paths))


def load_transcripts(run_dir: Path) -> dict[str, dict[str, Any]]:
    """Index model-visible transcript records by transcript id."""
    records: dict[str, dict[str, Any]] = {}
    for path in sorted((run_dir / "logs/transcripts").glob("agent_*.jsonl")):
        for row in read_jsonl(path):
            records[row["transcript_id"]] = row
    return records


def record_contains(record: dict[str, Any], needle: str) -> bool:
    return needle in json.dumps(record.get("content"), ensure_ascii=False)


def tool_result_evidence_transcripts(records: dict[str, dict[str, Any]], evidence_ref: str) -> list[str]:
    """Return model-visible tool-result transcripts that expose one evidence ref."""
    out = []
    # The transcript exporter preserves the tool payload as a string.  Some
    # read_file payloads contain source text with literal newlines, so that
    # nested string is not always valid JSON after the outer JSONL record has
    # been decoded.  The exact field/value pair is still unambiguous in the
    # model-visible tool result; match that pair directly before attempting a
    # structured parse.
    # json.dumps() escapes quotes when the nested tool payload is a string,
    # hence the optional backslash before each quote in this pattern.
    field_pattern = re.compile(rf"\\?[\"']evidence_ref\\?[\"']\s*:\s*\\?[\"']{re.escape(evidence_ref)}\\?[\"']")
    for transcript_id, row in records.items():
        if row.get("kind") != "tool_result" or not record_contains(row, evidence_ref):
            continue
        content = row.get("content")
        if field_pattern.search(json.dumps(content, ensure_ascii=False)):
            out.append(transcript_id)
            continue
        parsed: Any = content
        if isinstance(content, dict):
            parsed = content.get("content", content)
        if isinstance(parsed, str):
            try:
                parsed = json.loads(parsed)
            except json.JSONDecodeError:
                parsed = None
        if isinstance(parsed, dict) and parsed.get("evidence_ref") == evidence_ref:
            out.append(transcript_id)
    return sorted(out)


def transcript_ids_containing(records: dict[str, dict[str, Any]], needle: str, *, kinds: set[str] | None = None) -> list[str]:
    return sorted(
        transcript_id
        for transcript_id, row in records.items()
        if (kinds is None or row.get("kind") in kinds) and record_contains(row, needle)
    )


def task_completion_transcripts(records: dict[str, dict[str, Any]], task_id: str, agent_id: str) -> list[str]:
    """Find the exact model-visible complete_task result for one owner."""
    pattern = re.compile(rf"\\?[\"']id\\?[\"']\s*:\s*\\?[\"']{re.escape(task_id)}\\?[\"']")
    out: list[str] = []
    for transcript_id, row in records.items():
        if row.get("kind") != "tool_result" or row.get("agent_id") != agent_id:
            continue
        content = row.get("content")
        if not isinstance(content, dict) or content.get("name") != "complete_task":
            continue
        if pattern.search(json.dumps(content, ensure_ascii=False)):
            out.append(transcript_id)
    return sorted(out)


def pre_transcript_provenance(task_rows: list[dict[str, Any]], finding_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Bind every pre-sync evidence ref to a model-visible tool-result transcript."""
    rows: list[dict[str, Any]] = []
    cache: dict[str, dict[str, dict[str, Any]]] = {}
    for source_row in task_rows + finding_rows:
        records = cache.setdefault(source_row["run_id"], load_transcripts(RUNS_DIR / source_row["run_id"]))
        ref_map = {ref: tool_result_evidence_transcripts(records, ref) for ref in source_row.get("active_evidence_refs", [])}
        missing = sorted(ref for ref, transcript_ids in ref_map.items() if not transcript_ids)
        completion_ids: list[str] = []
        if source_row["kind"] == "task":
            events, _, sync_seq = event_index(RUNS_DIR / source_row["run_id"])
            completion = next((e for e in events if e["event_type"] == "task_completed" and e.get("payload", {}).get("task_id") == source_row["task_id"]), None)
            if completion is None or completion["sequence"] >= sync_seq:
                raise RuntimeError(f"{source_row['run_id']}/{source_row['task_id']}: missing pre-sync task_completed event")
            completion_ids = task_completion_transcripts(records, source_row["task_id"], source_row["agent_id"])
        rows.append({
            "kind": source_row["kind"],
            "run_id": source_row["run_id"],
            "task_id": source_row.get("task_id"),
            "agent_id": source_row["agent_id"],
            "active_evidence_refs": source_row.get("active_evidence_refs", []),
            "evidence_ref_transcript_ids": ref_map,
            "missing_evidence_ref_transcripts": missing,
            "task_completion_transcript_ids": completion_ids,
            "model_visible_evidence_chain_complete": not missing and (source_row["kind"] != "task" or bool(completion_ids)),
            "basis": "logs/events.jsonl + logs/transcripts/<agent>.jsonl; all refs are before result_sync_triggered",
        })
    return rows


def post_transcript_provenance(post_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Bind delivery and verification steps to exact model-request/tool-result transcripts."""
    rows: list[dict[str, Any]] = []
    cache: dict[str, dict[str, dict[str, Any]]] = {}
    for source_row in post_rows:
        run_dir = RUNS_DIR / source_row["run_id"]
        records = cache.setdefault(source_row["run_id"], load_transcripts(run_dir))
        events, by_id, _ = event_index(run_dir)
        agent_id = source_row["agent_id"]
        request_ids: list[str] = []
        for event_id in source_row.get("post_sync_instruction_event_ids", []):
            event = by_id.get(event_id)
            request_id = (event.get("payload") or {}).get("request_transcript_id") if event else None
            if request_id:
                request_ids.append(request_id)
        request_valid = [tid for tid in request_ids if records.get(tid, {}).get("kind") == "model_request"]
        result_sync_event = next((e for e in events if e["event_type"] == "result_sync_observed" and e.get("agent_id") == agent_id), None)
        foreign_tasks = (result_sync_event.get("payload") or {}).get("foreign_completed_task_ids", []) if result_sync_event else []
        initial_request_id = request_valid[0] if request_valid else None
        initial_contains_foreign_tasks = bool(initial_request_id and foreign_tasks and all(record_contains(records[initial_request_id], task_id) for task_id in foreign_tasks))
        verification_refs: list[str] = []
        verification_transcripts: dict[str, list[str]] = {}
        for event_id in source_row.get("verification_action_event_ids", []):
            event = by_id.get(event_id)
            if not event or event.get("event_type") != "file_read":
                continue
            # file_read events carry an evidence ref through their artifact,
            # but the event itself has no ref field.  Match the path and the
            # exact tool-result transcript content.
            path = (event.get("payload") or {}).get("path")
            candidates = []
            for transcript_id, record in records.items():
                # A file_read event is emitted for one agent.  Restrict the
                # model-visible result lookup to that agent's transcript so a
                # later list_tasks/result snapshot from another agent cannot
                # satisfy the verification chain merely by repeating a path.
                if (
                    record.get("kind") != "tool_result"
                    or f"{agent_id}_" not in transcript_id
                    or path not in json.dumps(record.get("content"), ensure_ascii=False)
                ):
                    continue
                candidates.append(transcript_id)
            verification_transcripts[event_id] = sorted(candidates)
            verification_refs.append(event_id)
        followup_ids = [tid for tid in request_valid if records[tid].get("content", {}).get("step") != (records[initial_request_id].get("content", {}).get("step") if initial_request_id else None)]
        rows.append({
            "run_id": source_row["run_id"],
            "agent_id": agent_id,
            "evidence_consumed": bool(source_row["evidence_consumed"]),
            "result_sync_observation_event_ids": source_row.get("sync_observation_event_ids", []),
            "post_sync_request_transcript_ids": request_valid,
            "initial_request_transcript_id": initial_request_id,
            "initial_request_contains_all_foreign_task_ids": initial_contains_foreign_tasks,
            "verification_file_read_event_ids": verification_refs,
            "verification_tool_result_transcript_ids": verification_transcripts,
            "verification_followup_request_transcript_ids": followup_ids,
            "delivery_transcript_chain_complete": bool(request_valid) and initial_contains_foreign_tasks,
            "evidence_consumption_transcript_chain_complete": (not source_row["evidence_consumed"] or bool(verification_transcripts and all(verification_transcripts.values()) and followup_ids)),
            "basis": "logs/events.jsonl + model-visible logs/transcripts/<agent>.jsonl",
        })
    return rows


def node_evidence(nodes: dict[str, dict[str, Any]], node_ids: list[str], paths: list[str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for node_id in node_ids:
        scopes = nodes[node_id]["code_scope"]
        matched = sorted(p for p in paths if any(path_matches(p, s) for s in scopes))
        if matched:
            out[node_id] = matched
    return out


def map_pre_sync(manifest: dict[str, Any], nodes: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    task_rows: list[dict[str, Any]] = []
    finding_rows: list[dict[str, Any]] = []
    coverage_rows: list[dict[str, Any]] = []
    for run_name in RUN_NAMES:
        run_dir = RUNS_DIR / run_name
        events, by_id, sync_seq = event_index(run_dir)
        event_paths = {e["event_id"]: normal_path((e.get("payload") or {}).get("path")) for e in events if e.get("event_type") == "file_read"}
        tasks = sorted((read_json(p) for p in (run_dir / "runtime/coordination/tasks").glob("*.json")), key=lambda d: d["id"])
        for task in tasks:
            refs = list(task.get("evidence_refs") or [])
            if any((by_id.get(ref) or {}).get("sequence", 10**9) >= sync_seq for ref in refs):
                raise RuntimeError(f"{run_name}/{task['id']}: task evidence is not ACTIVE/RESULT_SYNC-pre evidence")
            paths = ref_paths(refs, by_id)
            node_ids = list(CURATED_TASK_NODES.get((run_name, task["id"]), []))
            evidence_by_node = node_evidence(nodes, node_ids, paths)
            if set(evidence_by_node) != set(node_ids):
                raise RuntimeError(f"{run_name}/{task['id']}: curated mapping has no matching frozen scope")
            task_rows.append({
                "kind": "task",
                "run_id": run_name,
                "task_id": task["id"],
                "agent_id": task["owner"],
                "scope_declared": task["description"],
                "active_evidence_refs": refs,
                "actual_code_paths": paths,
                "node_ids": node_ids,
                "evidence_by_node": evidence_by_node,
                "mapping_confidence": "high" if node_ids else "none",
                "mapping_status": "mapped" if node_ids else "out_of_graph",
                "out_of_graph": not bool(node_ids),
                "out_of_graph_reason": None if node_ids else "ACTIVE evidence refs do not land in any frozen graph-v2 node scope.",
                "sync_trigger_event_id": next(e["event_id"] for e in events if e["event_type"] == "result_sync_triggered"),
                "sync_trigger_sequence": sync_seq,
            })

        for finding_path in sorted((run_dir / "artifacts").glob("agent_*_findings.json")):
            agent_id = finding_path.stem.removesuffix("_findings")
            payload = read_json(finding_path)
            findings = payload.get("findings") or []
            all_refs = sorted({ref for f in findings for ref in (f.get("evidence_refs") or [])})
            refs = [ref for ref in all_refs if (by_id.get(ref) or {}).get("sequence", 10**9) < sync_seq]
            post_refs = [ref for ref in all_refs if ref not in refs]
            paths = ref_paths(refs, by_id)
            node_ids = list(CURATED_FINDING_NODES.get((run_name, agent_id), []))
            evidence_by_node = node_evidence(nodes, node_ids, paths)
            if set(evidence_by_node) != set(node_ids):
                raise RuntimeError(f"{run_name}/{agent_id}: curated finding mapping has no matching frozen scope")
            finding_rows.append({
                "kind": "finding",
                "run_id": run_name,
                "agent_id": agent_id,
                "finding_count": len(findings),
                "active_evidence_refs": refs,
                "post_sync_evidence_refs_excluded": post_refs,
                "actual_code_paths": paths,
                "node_ids": node_ids,
                "evidence_by_node": evidence_by_node,
                "mapping_confidence": "high" if node_ids else "none",
                "mapping_status": "mapped" if node_ids else "out_of_graph",
                "out_of_graph": not bool(node_ids),
                "out_of_graph_reason": None if node_ids else "Finding source/sink evidence is outside frozen graph-v2 scopes.",
            })

        mapped_by_agent: dict[str, set[str]] = defaultdict(set)
        for row in task_rows:
            if row["run_id"] == run_name:
                mapped_by_agent[row["agent_id"]].update(row["node_ids"])
        for agent_id, node_ids in sorted(mapped_by_agent.items()):
            for node_id in sorted(node_ids):
                coverage_rows.append({"run_id": run_name, "agent_id": agent_id, "node_id": node_id, "coverage": "covered_node", "basis": "ACTIVE task evidence"})
        for edge in actionable_edges(GLOBAL_EDGES):
            instances = []
            for source_agent, source_nodes in sorted(mapped_by_agent.items()):
                for target_agent, target_nodes in sorted(mapped_by_agent.items()):
                    if source_agent == target_agent:
                        continue
                    if edge["source_node"] in source_nodes and edge["target_node"] in target_nodes:
                        instances.append({"source_agent": source_agent, "target_agent": target_agent})
            coverage_rows.append({
                "run_id": run_name,
                "edge_id": edge["edge_id"],
                "source_node": edge["source_node"],
                "target_node": edge["target_node"],
                "structurally_actionable": True,
                "cross_agent_coverage": bool(instances),
                "coverage_status": "covered" if instances else "no_cross_agent_coverage",
                "instances": instances,
                "basis": "ACTIVE task evidence mapped to frozen node scopes",
            })
    summary = summarize_mapping(task_rows, finding_rows, coverage_rows, manifest)
    return task_rows, finding_rows, {"rows": coverage_rows, "summary": summary}


def summarize_mapping(task_rows: list[dict[str, Any]], finding_rows: list[dict[str, Any]], coverage_rows: list[dict[str, Any]], manifest: dict[str, Any]) -> dict[str, Any]:
    task_counts = Counter(row["mapping_status"] for row in task_rows)
    finding_counts = Counter(row["mapping_status"] for row in finding_rows)
    node_rows = [row for row in coverage_rows if row.get("coverage") == "covered_node"]
    edge_rows = [row for row in coverage_rows if row.get("structurally_actionable")]
    by_run: dict[str, Any] = {}
    for run_name in RUN_NAMES:
        t = [r for r in task_rows if r["run_id"] == run_name]
        f = [r for r in finding_rows if r["run_id"] == run_name]
        e = [r for r in edge_rows if r["run_id"] == run_name]
        by_run[run_name] = {
            "task_count": len(t),
            "mapped_task_count": sum(r["mapping_status"] == "mapped" for r in t),
            "out_of_graph_task_count": sum(r["out_of_graph"] for r in t),
            "finding_file_count": len(f),
            "mapped_finding_file_count": sum(r["mapping_status"] == "mapped" for r in f),
            "out_of_graph_finding_file_count": sum(r["out_of_graph"] for r in f),
            "covered_node_ids": sorted({r["node_id"] for r in node_rows if r["run_id"] == run_name}),
            "covered_actionable_edge_count": sum(r["coverage_status"] == "covered" for r in e),
            "covered_actionable_edge_ids": [r["edge_id"] for r in e if r["coverage_status"] == "covered"],
        }
    return {
        "graph_version": manifest["graph_version"],
        "graph_manifest_sha256": sha256_file(GRAPH_DIR / "graph_manifest.json"),
        "structural_actionable_edge_count": len(actionable_edges(GLOBAL_EDGES)),
        "task_mapping_counts": dict(task_counts),
        "finding_mapping_counts": dict(finding_counts),
        "mapped_node_observation_count": len(node_rows),
        "cross_agent_covered_edge_count": sum(r["coverage_status"] == "covered" for r in edge_rows),
        "by_run": by_run,
        "interpretation": "Coverage is evidence-based and pre-POST_SYNC. out_of_graph is not none and no coverage shortfall is attributed to a structural edge.",
    }


def build_realizability(edges: dict[str, dict[str, Any]], manifest: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for edge in actionable_edges(edges):
        for condition in CONDITIONS:
            contract = CONTRACTS[condition]
            rows.append({
                "edge_id": edge["edge_id"],
                "source_node": edge["source_node"],
                "target_node": edge["target_node"],
                "opportunity_type": edge["opportunity_type"],
                "condition": condition,
                "operationally_realizable": contract["status"],
                "tools": contract["tools"],
                "communication_channel": contract["channel"],
                "visibility": contract["visibility"],
                "permit_basis": contract["permits"],
                "available_phase": "ACTIVE / RESULT_SYNC / POST_SYNC" if condition in {"T4", "M4"} else "ACTIVE",
                "lifecycle": contract["lifecycle"],
                "minimum_transfer": contract["minimum_transfer"],
                "reason": contract["reason"],
                "contract_basis": contract["basis"],
                "budget_exhaustion_separate": True,
                "graph_manifest_sha256": sha256_file(GRAPH_DIR / "graph_manifest.json"),
            })
    return rows


def build_handoffs(edges: dict[str, dict[str, Any]], manifest: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    run_summary: dict[str, Any] = {}
    for run_name in RUN_NAMES:
        run_dir = RUNS_DIR / run_name
        events, by_id, sync_seq = event_index(run_dir)
        sync = next(e for e in events if e["event_type"] == "result_sync_triggered")
        pre_grants = [e for e in events if e["event_type"] == "call_permit_granted" and e["sequence"] < sync_seq]
        metrics = read_json(run_dir / "metrics.json")
        resource = metrics["resource_allocation"]["team"]
        result_sync = metrics["result_sync"]
        post_admits = [e for e in events if e["event_type"] == "post_sync_provider_call_admitted"]
        post_by_agent = Counter(e["agent_id"] for e in post_admits)
        # T4 v2 reserves 16 of 192 permits for the post-sync window.
        normal_cap = 192 - 16
        run_summary[run_name] = {
            "condition": "T4",
            "sync_trigger_event_id": sync["event_id"],
            "sync_trigger_sequence": sync_seq,
            "pre_sync_permits_acquired": len(pre_grants),
            "normal_permits_remaining_at_sync": normal_cap - len(pre_grants),
            "post_sync_reserved_per_agent": 4,
            "post_sync_reserved_total": 16,
            "post_sync_admits_by_agent": dict(sorted(post_by_agent.items())),
            "post_sync_admit_total": len(post_admits),
            "final_permits_acquired": resource["permits_acquired"],
            "final_unused_permits": resource["unused_permits"],
            "result_sync_exactly_once": bool(result_sync["exactly_once"]),
            "all_agents_observed": len(result_sync.get("per_agent", {})) == 4 and all(result_sync["per_agent"][a]["sync_observation_event_ids"] for a in result_sync["per_agent"]),
            "all_agents_post_sync_admitted": all(result_sync["per_agent"][a]["post_sync_provider_call_admitted"] for a in result_sync["per_agent"]),
        }
        for edge in actionable_edges(edges):
            run_summary[run_name].setdefault("edge_handoff_rows", 0)
            run_summary[run_name]["edge_handoff_rows"] += 1
            rows.append({
                "run_id": run_name,
                "condition": "T4",
                "edge_id": edge["edge_id"],
                "source_node": edge["source_node"],
                "target_node": edge["target_node"],
                "handoff": "RESULT_SYNC -> POST_SYNC",
                "operationally_realizable_at_handoff": "yes" if run_summary[run_name]["normal_permits_remaining_at_sync"] >= 0 and run_summary[run_name]["all_agents_observed"] else "uncertain",
                "delivery_window_opened": run_summary[run_name]["all_agents_post_sync_admitted"],
                "remaining_normal_permits_at_sync": run_summary[run_name]["normal_permits_remaining_at_sync"],
                "post_sync_reserved_per_agent": 4,
                "post_sync_admit_total": len(post_admits),
                "channel": "typed completed-task snapshot; optional read_file/follow-up; submit-only repair",
                "visibility": "foreign completed task result and evidence refs model-visible after result_sync_observed",
                "budget_reason": "run-specific remaining permits are reported separately from contract realizability",
                "sync_trigger_event_id": sync["event_id"],
            })
    return rows, run_summary


def post_sync_rows(manifest: dict[str, Any], task_rows: list[dict[str, Any]], finding_rows: list[dict[str, Any]], nodes: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for run_name in RUN_NAMES:
        run_dir = RUNS_DIR / run_name
        events, by_id, sync_seq = event_index(run_dir)
        metrics = read_json(run_dir / "metrics.json")
        per_agent = metrics["result_sync"]["per_agent"]
        for agent_id in sorted(per_agent):
            observed = per_agent[agent_id]
            manual = POST_SYNC_MANUAL[(run_name, agent_id)]
            # Attach only event-index provenance here.  The semantic labels are
            # manual labels and are not inferred from mere provider admission.
            first_instruction_event = observed.get("post_sync_instruction_event_ids", [None])[0]
            mapped = sorted({n for r in task_rows + finding_rows if r["run_id"] == run_name and r["agent_id"] == agent_id for n in r["node_ids"]})
            receiver_node_status = "mapped" if mapped else "out_of_graph"
            # A direct relation/action is about a *foreign* artifact.  The
            # artifact selected in the frozen manual review is not promoted to
            # a graph edge merely because the receiving agent had its own
            # mapped node.  The three direct-relation records are therefore
            # kept as out_of_graph for edge accounting unless a pre-sync
            # evidence chain identifies both endpoints (none do in these
            # seeds).
            selected_artifact_graph_status = "out_of_graph" if manual["discovery"] == "direct_relation" else "not_selected"
            graph_status = selected_artifact_graph_status if selected_artifact_graph_status == "out_of_graph" else receiver_node_status
            rows.append({
                "run_id": run_name,
                "agent_id": agent_id,
                "sync_observation_event_ids": observed.get("sync_observation_event_ids", []),
                "post_sync_window_event_ids": observed.get("post_sync_window_event_ids", []),
                "post_sync_provider_admission_event_ids": observed.get("post_sync_provider_admission_event_ids", []),
                "post_sync_instruction_event_ids": observed.get("post_sync_instruction_event_ids", []),
                "delivery": "delivered" if observed.get("post_sync_provider_call_admitted") and observed.get("post_sync_instruction_model_visible") else "not_delivered",
                "discovery": manual["discovery"],
                "action": "verification" if manual["verification"] else "none_observed",
                "evidence_consumed": bool(observed.get("verification_evidence_model_visible")),
                "judgment_disposition": manual["judgment"],
                "judgment_changed": manual["judgment"] in {"strengthened", "weakened", "refuted", "narrowed", "extended"},
                "strict_foreign_evidence_ref_adoption": bool(observed.get("foreign_evidence_incorporated")),
                "claim_level_disposition": manual["claim_adoption"],
                "graph_node_ids_pre_sync": mapped,
                "receiving_agent_pre_sync_node_status": receiver_node_status,
                "graph_mapping_status": graph_status,
                "out_of_graph": graph_status == "out_of_graph",
                "out_of_graph_reason": "Selected foreign artifact or post-sync discussion was not reliably mapped to a frozen node/edge by ACTIVE evidence." if graph_status == "out_of_graph" else None,
                "selected_artifact_graph_status": selected_artifact_graph_status,
                "selected_artifact_edge_accounting": "excluded_from_graph_coverage" if selected_artifact_graph_status == "out_of_graph" else "not_applicable",
                "manual_note": manual["note"],
                "result_sync_outcome_level": observed.get("outcome_level"),
                "verification_target": observed.get("verification_target", []),
                "verification_action_event_ids": observed.get("post_sync_search_read_actions", []),
                "verification_evidence_visibility_event_ids": observed.get("verification_evidence_visibility_event_ids", []),
                "first_instruction_event_id": first_instruction_event,
                "manual_basis": "docs/releases/flowise-3.1.3-repository-v1-t4-post-sync-window-v2-3seed-analysis-20260923.md",
                "sync_trigger_sequence": sync_seq,
            })
    summary = {
        "row_count": len(rows),
        "delivery_count": sum(r["delivery"] == "delivered" for r in rows),
        "discovery_direct_relation_count": sum(r["discovery"] == "direct_relation" for r in rows),
        "actionable_lead_count": sum(r["action"] == "verification" for r in rows),
        "evidence_consumed_count": sum(r["evidence_consumed"] for r in rows),
        "judgment_changed_count": sum(r["judgment_changed"] for r in rows),
        "strict_foreign_evidence_ref_adoption_count": sum(r["strict_foreign_evidence_ref_adoption"] for r in rows),
        "claim_level_disposition_count": sum(r["claim_level_disposition"] for r in rows),
        "out_of_graph_count": sum(r["out_of_graph"] for r in rows),
        "selected_artifact_out_of_graph_count": sum(r["selected_artifact_graph_status"] == "out_of_graph" for r in rows),
        "interpretation": "POST_SYNC labels are deblinded only after pre-sync mapping. Delivery is runtime evidence; discovery/action/judgment are manual semantic labels. out_of_graph is not none.",
    }
    return rows, summary


GLOBAL_EDGES: dict[str, dict[str, Any]] = {}


def run() -> dict[str, Any]:
    global GLOBAL_EDGES
    manifest, nodes, edges = load_graph()
    GLOBAL_EDGES = edges
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(OUT_DIR, 0o700)

    realizability = build_realizability(edges, manifest)
    write_jsonl(OUT_DIR / "operational_realizability.jsonl", realizability)

    # Stage 1: pre-POST_SYNC mapping.  The resulting files are written before
    # the code reads any POST_SYNC manual labels.
    task_rows, finding_rows, coverage = map_pre_sync(manifest, nodes)
    write_jsonl(OUT_DIR / "run_task_mapping_pre_sync.jsonl", task_rows)
    write_jsonl(OUT_DIR / "run_finding_mapping_pre_sync.jsonl", finding_rows)
    write_jsonl(OUT_DIR / "run_coverage_pre_sync.jsonl", coverage["rows"])
    write_json(OUT_DIR / "run_mapping_summary.json", coverage["summary"])
    pre_transcripts = pre_transcript_provenance(task_rows, finding_rows)
    write_jsonl(OUT_DIR / "pre_sync_transcript_provenance.jsonl", pre_transcripts)

    handoff_rows, handoff_summary = build_handoffs(edges, manifest)
    write_jsonl(OUT_DIR / "run_handoffs.jsonl", handoff_rows)
    write_json(OUT_DIR / "run_handoff_summary.json", handoff_summary)

    # Stage 2: POST_SYNC deblinding and manual semantic review.
    post_rows, post_summary = post_sync_rows(manifest, task_rows, finding_rows, nodes)
    write_jsonl(OUT_DIR / "post_sync_review.jsonl", post_rows)
    write_json(OUT_DIR / "post_sync_summary.json", post_summary)
    post_transcripts = post_transcript_provenance(post_rows)
    write_jsonl(OUT_DIR / "post_sync_transcript_provenance.jsonl", post_transcripts)

    index = {
        "schema_version": 1,
        "case_id": "flowise_3_1_3_repository_v1",
        "graph_version": manifest["graph_version"],
        "graph_manifest_sha256": sha256_file(GRAPH_DIR / "graph_manifest.json"),
        "graph_edges_sha256": sha256_file(GRAPH_DIR / "edges.jsonl"),
        "structural_actionable_edge_count": len(actionable_edges(edges)),
        "conditions": list(CONDITIONS),
        "historical_runs": list(RUN_NAMES),
        "stages": [
            {"stage": "operational_realizability", "file": "operational_realizability.jsonl", "status": "complete", "rows": len(realizability)},
            {"stage": "pre_post_sync_mapping", "files": ["run_task_mapping_pre_sync.jsonl", "run_finding_mapping_pre_sync.jsonl", "run_coverage_pre_sync.jsonl", "run_mapping_summary.json"], "status": "complete"},
            {"stage": "pre_sync_transcript_provenance", "file": "pre_sync_transcript_provenance.jsonl", "status": "complete", "rows": len(pre_transcripts)},
            {"stage": "handoff_budget", "files": ["run_handoffs.jsonl", "run_handoff_summary.json"], "status": "complete"},
            {"stage": "post_sync_deblind", "files": ["post_sync_review.jsonl", "post_sync_summary.json", "post_sync_transcript_provenance.jsonl"], "status": "complete", "rows": len(post_transcripts)},
        ],
        "ordering_assertion": "ACTIVE/RESULT_SYNC-pre evidence was mapped before POST_SYNC labels were read; all pre-sync refs have event sequence < result_sync_triggered.",
        "out_of_graph_rule": "No node/edge mapping is evidence-supported => out_of_graph; it is never rewritten as none.",
        "notes": [
            "S1 has no cross-agent denominator; any within-agent reuse is outside this cross-agent edge table.",
            "B4 contract realizability means a generic shared file can carry an artifact; it does not imply agents used it.",
            "Run-specific budget exhaustion is retained in handoff files and never changes the frozen graph.",
        ],
    }
    write_json(OUT_DIR / "analysis_index.json", index)
    return {"output_dir": str(OUT_DIR), "realizability_rows": len(realizability), "task_rows": len(task_rows), "finding_rows": len(finding_rows), "coverage_rows": len(coverage["rows"]), "pre_sync_transcript_rows": len(pre_transcripts), "post_sync_rows": len(post_rows), "post_sync_transcript_rows": len(post_transcripts), "post_sync_summary": post_summary, "mapping_summary": coverage["summary"]}


def verify() -> dict[str, Any]:
    """Fail closed on missing, stale, or cross-stage contaminated artifacts."""
    manifest, nodes, edges = load_graph()
    expected_digest = sha256_file(GRAPH_DIR / "graph_manifest.json")
    index = read_json(OUT_DIR / "analysis_index.json")
    if index.get("graph_manifest_sha256") != expected_digest:
        raise RuntimeError("operational analysis is bound to a different graph manifest")
    realizability = read_jsonl(OUT_DIR / "operational_realizability.jsonl")
    tasks = read_jsonl(OUT_DIR / "run_task_mapping_pre_sync.jsonl")
    findings = read_jsonl(OUT_DIR / "run_finding_mapping_pre_sync.jsonl")
    coverage = read_jsonl(OUT_DIR / "run_coverage_pre_sync.jsonl")
    pre_transcripts = read_jsonl(OUT_DIR / "pre_sync_transcript_provenance.jsonl")
    handoffs = read_jsonl(OUT_DIR / "run_handoffs.jsonl")
    post = read_jsonl(OUT_DIR / "post_sync_review.jsonl")
    post_transcripts = read_jsonl(OUT_DIR / "post_sync_transcript_provenance.jsonl")
    if len(realizability) != 60 or len(tasks) != 12 or len(post) != 12 or len(handoffs) != 36 or len(pre_transcripts) != len(tasks) + len(findings) or len(post_transcripts) != len(post):
        raise RuntimeError(f"unexpected artifact dimensions: realizability={len(realizability)}, tasks={len(tasks)}, post={len(post)}, handoffs={len(handoffs)}, pre_transcripts={len(pre_transcripts)}, post_transcripts={len(post_transcripts)}")
    if len({r["edge_id"] for r in realizability}) != 12 or len({r["edge_id"] for r in coverage if r.get("structurally_actionable")}) != 12:
        raise RuntimeError("actionable edge denominator is not the frozen 12-edge set")
    if any(r["condition"] == "S1" and r["operationally_realizable"] != "no" for r in realizability):
        raise RuntimeError("S1 cross-agent realizability must be no")
    if any(r["condition"] in {"B4", "T4", "M4"} and r["operationally_realizable"] != "yes" for r in realizability):
        raise RuntimeError("B4/T4/M4 contract rows must be yes")
    for row in tasks + findings:
        if row["mapping_status"] == "out_of_graph" and not row["out_of_graph"]:
            raise RuntimeError("out_of_graph mapping lost its explicit marker")
        events, by_id, sync_seq = event_index(RUNS_DIR / row["run_id"])
        for ref in row.get("active_evidence_refs", []):
            if (by_id.get(ref) or {}).get("sequence", 10**9) >= sync_seq:
                raise RuntimeError(f"{row['run_id']}/{row.get('task_id', row.get('agent_id'))}: pre-sync mapping contains a post-sync evidence ref")
        for ref in row.get("post_sync_evidence_refs_excluded", []):
            if (by_id.get(ref) or {}).get("sequence", -1) < sync_seq:
                raise RuntimeError(f"{row['run_id']}/{row.get('agent_id')}: excluded evidence ref is not post-sync")
    for row in post:
        if row["delivery"] == "delivered" and not row["post_sync_provider_admission_event_ids"]:
            raise RuntimeError("delivered row lacks provider admission provenance")
    if any(not row["model_visible_evidence_chain_complete"] for row in pre_transcripts):
        missing = [f"{r['run_id']}/{r.get('task_id', r.get('agent_id'))}" for r in pre_transcripts if not r["model_visible_evidence_chain_complete"]]
        raise RuntimeError(f"pre-sync transcript evidence chain incomplete: {missing}")
    if any(not row["delivery_transcript_chain_complete"] for row in post_transcripts):
        missing = [f"{r['run_id']}/{r['agent_id']}" for r in post_transcripts if not r["delivery_transcript_chain_complete"]]
        raise RuntimeError(f"POST_SYNC delivery transcript chain incomplete: {missing}")
    consumed_rows = {
        f"{r['run_id']}/{r['agent_id']}": r
        for r in post_transcripts
        if r["evidence_consumed"] and r["evidence_consumption_transcript_chain_complete"]
    }
    expected_consumed = {f"{r['run_id']}/{r['agent_id']}" for r in post if r["evidence_consumed"]}
    if set(consumed_rows) != expected_consumed:
        raise RuntimeError(f"evidence-consumption transcript mismatch: expected={sorted(expected_consumed)}, actual={sorted(consumed_rows)}")
    summary = read_json(OUT_DIR / "post_sync_summary.json")
    if summary["delivery_count"] != 12 or summary["discovery_direct_relation_count"] != 3 or summary["actionable_lead_count"] != 2 or summary["evidence_consumed_count"] != 2 or summary["judgment_changed_count"] != 2 or summary["strict_foreign_evidence_ref_adoption_count"] != 0:
        raise RuntimeError(f"unexpected deblinded summary: {summary}")
    return {
        "status": "verified",
        "graph_manifest_sha256": expected_digest,
        "graph_nodes": len(nodes),
        "graph_edges": len(edges),
        "structural_actionable_edges": len(actionable_edges(edges)),
        "realizability_rows": len(realizability),
        "task_rows": len(tasks),
        "finding_rows": len(findings),
        "coverage_rows": len(coverage),
        "pre_sync_transcript_rows": len(pre_transcripts),
        "handoff_rows": len(handoffs),
        "post_sync_rows": len(post),
        "post_sync_transcript_rows": len(post_transcripts),
        "post_sync_summary": summary,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", choices=["run", "verify"], help="generate or verify the offline analysis artifacts")
    args = parser.parse_args()
    print(json.dumps(run() if args.run == "run" else verify(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
