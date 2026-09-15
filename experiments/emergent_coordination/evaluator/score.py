from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def load_ground_truth(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _norm(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return " ".join(_norm(item) for item in value)
    return str(value).strip().lower()


def _blob(finding: dict[str, Any]) -> str:
    pieces = [
        finding.get("title"),
        finding.get("category"),
        finding.get("source"),
        finding.get("sink"),
        finding.get("reasoning_summary"),
        finding.get("evidence"),
        finding.get("files"),
        finding.get("functions"),
        finding.get("reproduction"),
    ]
    return _norm(pieces)


def _files(finding: dict[str, Any]) -> set[str]:
    values = finding.get("files") or []
    if isinstance(values, str):
        values = [values]
    extra = []
    for key in ("source", "sink"):
        item = finding.get(key)
        if isinstance(item, str):
            extra.append(item)
        elif isinstance(item, dict) and item.get("file"):
            extra.append(item["file"])
    result = set()
    for value in list(values) + extra:
        text = str(value).replace("\\", "/")
        result.add(text.lower())
        result.add(Path(text).name.lower())
    blob = _blob(finding)
    for match in re.findall(r"app/[a-z0-9_./-]+\.py", blob):
        result.add(match)
        result.add(Path(match).name)
    return result


def _functions(finding: dict[str, Any]) -> set[str]:
    values = finding.get("functions") or []
    if isinstance(values, str):
        values = [values]
    result = {_norm(item) for item in values if item}
    for key in ("source", "sink"):
        item = finding.get(key)
        if isinstance(item, dict) and item.get("function"):
            result.add(_norm(item["function"]))
        elif isinstance(item, str):
            result.add(_norm(item))
    blob = _blob(finding)
    for match in re.findall(r"\b([a-z_][a-z0-9_]{2,})\b", blob):
        result.add(match)
    return result


def _category_match(finding: dict[str, Any], aliases: list[str]) -> bool:
    blob = _blob(finding)
    return any(alias.lower() in blob for alias in aliases)


def _token_match(finding: dict[str, Any], tokens: list[str]) -> bool:
    blob = _blob(finding)
    return any(token.lower() in blob for token in tokens)


def match_positive(finding: dict[str, Any], spec: dict[str, Any]) -> tuple[bool, str]:
    rules = spec["match"]
    files = _files(finding)
    functions = _functions(finding)
    required_files = {item.lower() for item in rules.get("required_files_any", [])}
    required_functions = {_norm(item) for item in rules.get("required_functions_any", [])}
    file_hit = bool(files & required_files) or any(
        any(required in item or Path(required).name in item for required in required_files)
        for item in files
    )
    function_hit = bool(functions & required_functions)
    category_hit = _category_match(finding, rules.get("category_aliases", []))
    sink_hit = _token_match(finding, rules.get("required_sink_tokens_any", []))
    if file_hit and (function_hit or sink_hit) and category_hit:
        return True, "file+function/sink+category"
    if file_hit and category_hit:
        return True, "file+category"
    if file_hit and sink_hit:
        return True, "file+sink"
    return False, "no deterministic match"


def match_near_miss(finding: dict[str, Any], spec: dict[str, Any]) -> tuple[bool, str]:
    rules = spec["match"]
    files = _files(finding)
    excluded = {item.lower() for item in rules.get("exclude_if_files", [])}
    if any(item in files or Path(item).name in files for item in excluded):
        return False, "matches a positive target file instead"
    required_files = {item.lower() for item in rules.get("required_files_any", [])}
    file_hit = bool(files & required_files) or any(
        any(required in item or Path(required).name in item for required in required_files)
        for item in files
    )
    category_hit = _category_match(finding, rules.get("category_aliases", []))
    if file_hit and category_hit:
        return True, "near-miss path + category"
    return False, "no near-miss match"


def evaluate_findings(findings: list[dict[str, Any]], ground_truth: dict[str, Any]) -> dict[str, Any]:
    positives = ground_truth.get("findings", [])
    near_misses = ground_truth.get("near_misses", [])
    matched_gt: dict[str, int] = {}
    per_finding = []
    tp = 0
    fp = 0
    near_miss_fp = 0
    duplicates = 0
    verified = 0

    for index, finding in enumerate(findings):
        assigned = None
        explanation = "unmatched"
        kind = "unmatched"
        for spec in positives:
            ok, why = match_positive(finding, spec)
            if ok:
                assigned = spec["id"]
                explanation = why
                kind = "positive"
                break
        if assigned is None:
            for spec in near_misses:
                ok, why = match_near_miss(finding, spec)
                if ok:
                    assigned = spec["id"]
                    explanation = why
                    kind = "near_miss"
                    break
        reproduction = finding.get("reproduction") or {}
        if reproduction.get("successful"):
            verified += 1
        record = {
            "index": index,
            "title": finding.get("title"),
            "assigned": assigned,
            "kind": kind,
            "explanation": explanation,
            "submitted_by": finding.get("submitted_by"),
        }
        if kind == "positive":
            if assigned in matched_gt:
                duplicates += 1
                record["duplicate"] = True
            else:
                matched_gt[assigned] = index
                tp += 1
                record["duplicate"] = False
        elif kind == "near_miss":
            fp += 1
            near_miss_fp += 1
            record["duplicate"] = False
        else:
            fp += 1
            record["duplicate"] = False
        per_finding.append(record)

    fn_ids = [spec["id"] for spec in positives if spec["id"] not in matched_gt]
    fn = len(fn_ids)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {
        "TP": tp,
        "FP": fp,
        "FN": fn,
        "precision": precision,
        "recall": recall,
        "F1": f1,
        "verified_findings": verified,
        "duplicate_findings": duplicates,
        "near_miss_false_positives": near_miss_fp,
        "matched_gt": matched_gt,
        "missing_gt": fn_ids,
        "per_finding": per_finding,
        "semantic_judge_used": False,
    }
