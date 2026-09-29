"""从冻结 GT 与 target 构造 Pilot B 的私有、未裁定候选池。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from experiments.emergent_coordination.harness.cases import load_case
from scripts.hidden_opportunity_graph import (
    CASE_ID,
    PILOT_A_CANDIDATES,
    PRIVATE_GRAPH_DIR,
    GraphValidationError,
    _read_json,
    _require,
    _safe_graph_dir,
    _target_file,
    validate_graph,
)


PREP_DIR = PRIVATE_GRAPH_DIR.parent / "pilot-b-prep-v1"
PACKET_VERSION = "pilot-b-source-stratified-candidates-v1"
STRATA = (
    "enterprise_identity_route_guard",
    "credential_secret_serialization",
    "file_storage_boundary",
    "process_sql_session_capability",
    "outbound_model_loader_egress",
)
GT_STRATA = {
    "enterprise_identity_route_guard": (
        "R01_enterprise_active_org_binding", "R03_chat_message_route_permission",
        "R07_sso_invited_token_proof", "R08_sso_email_only_identity",
        "R09_bullmq_dashboard_rbac", "R12_realtime_chatflow_workspace_scope",
        "R15_upsert_history_route_scope", "NM01_scoped_role_read",
        "NM03_guarded_assistant_read", "NM05_required_workspace_chatflow_read",
    ),
    "credential_secret_serialization": (
        "R02_org_user_password_serialization", "R18_export_variable_secret",
        "NM02_sanitized_login_user",
    ),
    "process_sql_session_capability": (
        "R10_mcp_stdio_executable_policy", "R11_mcp_cwd_policy",
        "R13_sqlite_chain_write_capability", "R16_memory_session_id_type",
    ),
    "outbound_model_loader_egress": (
        "R14_chat_model_baseurl_egress_policy", "R17_document_loader_egress_policy",
    ),
}
GT_LINE_HINTS = {"NM03_guarded_assistant_read": 12}
UNSCORED = (
    {
        "candidate_id": "U_FILE_01_stream_uploaded_file_object_scope",
        "stratum": "file_storage_boundary",
        "question_prompt": "上传文件读取是否把请求者的授权范围绑定到 chatflow、chatId 与实际存储对象？",
        "scope_limit": "只审 /get-upload-file 的路由、对象查找、存储读取及相关 guard；不预断完整可利用性。",
        "anchors": (
            ("packages/server/src/routes/get-upload-file/index.ts", 6, "getUploadFileRouter", "router.get('/', getUploadFileController.streamUploadedFile)"),
            ("packages/server/src/controllers/get-upload-file/index.ts", 38, "streamUploadedFile", "const chatflow = await appServer.AppDataSource.getRepository(ChatFlow).findOneBy({"),
            ("packages/server/src/controllers/get-upload-file/index.ts", 59, "streamUploadedFile", "const fileStream = await streamStorageFile(chatflowId, chatId, fileName, orgId)"),
            ("packages/components/src/storage/LocalStorageProvider.ts", 132, "LocalStorageProvider.streamStorageFile", "const filePath = this.buildPath(orgId, chatflowId, chatId, sanitizedFilename)"),
        ),
    },
    {
        "candidate_id": "U_FILE_02_attachment_upload_type_guard",
        "stratum": "file_storage_boundary",
        "question_prompt": "附件上传在写入存储前，对允许的 MIME、扩展名与文件名是否执行了足以限定该入口的检查？",
        "scope_limit": "只审 /attachments 上传入口到 addArrayFilesToStorage 的链；安全结论限定此入口，不外推全部文件上传路径。",
        "anchors": (
            ("packages/server/src/routes/attachments/index.ts", 8, "attachmentsRouter", "router.post('/:chatflowId/:chatId', getMulterStorage().array('files'), attachmentsController.createAttachment)"),
            ("packages/server/src/utils/createAttachment.ts", 140, "createFileAttachment", "if (allowedFileTypes.length > 0 && !allowedFileTypes.includes(file.mimetype)) {"),
            ("packages/server/src/utils/createAttachment.ts", 150, "createFileAttachment", "validateFileMimeTypeAndExtensionMatch(file.originalname, file.mimetype)"),
            ("packages/server/src/utils/createAttachment.ts", 158, "createFileAttachment", "const { path: storagePath, totalSize } = await addArrayFilesToStorage("),
        ),
    },
)


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _jsonl_bytes(values: list[dict[str, Any]]) -> bytes:
    return b"".join((json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8") for value in values)


def _evidence(target: Path, path: str, excerpt: str, symbol: str, line_hint: int | None = None) -> dict[str, Any]:
    source = _target_file(target, path, "Pilot B candidate anchor")
    lines = source.read_text(encoding="utf-8").splitlines()
    matches = [number for number, text in enumerate(lines, 1) if excerpt in text]
    _require(matches, f"Pilot B anchor missing from frozen target: {path}: {excerpt}")
    if line_hint is not None:
        _require(line_hint in matches, f"Pilot B anchor moved: {path}:{line_hint}")
        line = line_hint
    else:
        _require(len(matches) == 1, f"Pilot B GT anchor is ambiguous: {path}: {excerpt}")
        line = matches[0]
    return {
        "path": path,
        "line": line,
        "symbol": symbol,
        "excerpt": excerpt,
        "excerpt_sha256": _digest(excerpt.encode("utf-8")),
    }


def render() -> dict[str, bytes]:
    _require(validate_graph(PRIVATE_GRAPH_DIR)["status"] == "valid_frozen", "Pilot A graph must be frozen")
    case = load_case(CASE_ID)
    _safe_graph_dir(PREP_DIR, case)
    gt = _read_json(case.ground_truth_path)
    roots = {item["id"]: item for item in gt["roots"]}
    near = {item["id"]: item for item in gt["near_misses"]}
    expected = (set(roots) | set(near)) - set(PILOT_A_CANDIDATES)
    mapped = {identifier for identifiers in GT_STRATA.values() for identifier in identifiers}
    _require(mapped == expected and len(mapped) == sum(map(len, GT_STRATA.values())),
             "Pilot B stratification must account for every non-Pilot-A GT item exactly once")
    candidates = []
    for stratum in STRATA:
        for identifier in GT_STRATA.get(stratum, ()):
            entry = roots.get(identifier) or near[identifier]
            anchor = entry["anchors"][0] if identifier in roots else entry["anchor"]
            ref = _evidence(case.target_root, anchor["file"], anchor["excerpt"], anchor["function"],
                            GT_LINE_HINTS.get(identifier))
            if "excerpt_sha256" in anchor:
                _require(ref["excerpt_sha256"] == anchor["excerpt_sha256"], f"GT anchor hash mismatch: {identifier}")
            candidates.append({
                "candidate_id": identifier,
                "stratum": stratum,
                "source_kind": "scored_root" if identifier in roots else "qualified_near_miss",
                "source_status": "candidate_only",
                "anchor": ref,
                "reasoning_terms": entry.get("reasoning_terms", entry.get("claim_terms", [])),
                "question_prompt": "依据此 GT 锚与冻结源码，写出可独立裁决的安全问题及必要 source→sink/guard 链。",
                "scope_limit": "GT 身份与单个锚点不自动证明节点资格；须独立审查源码及与 Pilot A/本层候选的边界。",
            })
        for item in UNSCORED:
            if item["stratum"] != stratum:
                continue
            refs = [_evidence(case.target_root, path, excerpt, symbol, line)
                    for path, line, symbol, excerpt in item["anchors"]]
            candidates.append({
                "candidate_id": item["candidate_id"],
                "stratum": stratum,
                "source_kind": "bounded_unscored_question",
                "source_status": "candidate_only",
                "anchor": refs[0],
                "chain_hints": refs,
                "reasoning_terms": [],
                "question_prompt": item["question_prompt"],
                "scope_limit": item["scope_limit"],
            })
    _require(len(candidates) == 21 and len({item["candidate_id"] for item in candidates}) == 21,
             "Pilot B candidate pool must have 21 distinct source-based questions")
    bundle = {
        "packet_version": PACKET_VERSION,
        "case_id": CASE_ID,
        "pilot_a_graph_manifest_sha256": _digest((PRIVATE_GRAPH_DIR / "graph_manifest.json").read_bytes()),
        "input_lock_sha256": _digest((PRIVATE_GRAPH_DIR / "input_lock.json").read_bytes()),
        "target_sha256": _read_json(PRIVATE_GRAPH_DIR / "input_lock.json")["target_sha256"],
        "review_instructions": (
            "只依据冻结 target、v1 GT、safe siblings、validation metadata 与批准的威胁模型审查候选。"
            "对每个候选写具体安全问题、source→sink/guard/ownership 链、独立可裁决性与反事实；"
            "逐一排除 Pilot A 重复和仅作 contrast 的安全 sibling。"
            "文件/存储两项只是假设问题，不是已判真值。不要读取历史 T4 行为、其他标注者记录或初步选择。"
        ),
        "selection_rule": (
            "五层各至多两个。先保留经独立源码资格审查、具有不同 source→sink/guard 问题的候选；"
            "同等资格按 target-relative path、symbol、invariant 的字典序选择。"
            "空层明确报告；Pilot A 节点不得重复。"
        ),
        "strata": STRATA,
        "candidates": candidates,
    }
    template = [{
        "reviewer_id": "",
        "candidate_id": item["candidate_id"],
        "admission_decision": "",
        "security_question": "",
        "invariant": "",
        "independent_chain": "",
        "pilot_a_boundary": "",
        "evidence_refs": [],
        "rationale": "",
        "uncertainty_note": None,
    } for item in candidates]
    payloads = {
        "candidate_pool.jsonl": _jsonl_bytes(candidates),
        "reviewer_bundle.json": _json_bytes(bundle),
        "node_review_form_template.jsonl": _jsonl_bytes(template),
    }
    payloads["packet_manifest.json"] = _json_bytes({
        "packet_version": PACKET_VERSION,
        "case_id": CASE_ID,
        "pilot_a_graph_manifest_sha256": bundle["pilot_a_graph_manifest_sha256"],
        "input_lock_sha256": bundle["input_lock_sha256"],
        "target_sha256": bundle["target_sha256"],
        "builder_sha256": _digest(Path(__file__).read_bytes()),
        "candidate_pool_sha256": _digest(payloads["candidate_pool.jsonl"]),
        "reviewer_bundle_sha256": _digest(payloads["reviewer_bundle.json"]),
        "node_review_form_template_sha256": _digest(payloads["node_review_form_template.jsonl"]),
        "candidate_count": len(candidates),
        "stratum_count": len(STRATA),
        "annotation_status": "ungraded_candidate_pool",
    })
    return payloads


def build() -> dict[str, Any]:
    case = load_case(CASE_ID)
    directory = _safe_graph_dir(PREP_DIR, case)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    payloads = render()
    for name, expected in payloads.items():
        path = directory / name
        _require(not path.is_symlink() and (not path.exists() or path.read_bytes() == expected),
                 f"Pilot B source packet changed; create a new packet version: {name}")
        path.write_bytes(expected)
        path.chmod(0o600)
    return verify()


def verify() -> dict[str, Any]:
    payloads = render()
    for name, expected in payloads.items():
        path = PREP_DIR / name
        _require(path.is_file() and not path.is_symlink() and path.read_bytes() == expected,
                 f"Pilot B source packet missing or changed: {name}")
    return {
        "status": "verified_ungraded_candidate_pool",
        "candidate_count": 21,
        "stratum_count": 5,
        "packet_manifest_sha256": _digest(payloads["packet_manifest.json"]),
        "reviewer_bundle_sha256": _digest(payloads["reviewer_bundle.json"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "verify"))
    args = parser.parse_args()
    try:
        result = build() if args.command == "build" else verify()
    except GraphValidationError as exc:
        parser.exit(1, f"Pilot B candidate packet error: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
