"""Classification of model calls by their observed role.

One role per model call, with a fixed precedence so that runtime logging and
offline analysis assign identical labels:

1. ``submission``   — the response tried to call ``submit_findings`` (including
                      unparseable/truncated arguments; the intent is what counts).
2. ``finalization`` — the call happened inside a completion-policy finalization
                      window (runtime-restricted tool surface).
3. ``coordination`` — the response called a coordination-surface tool.
4. ``exploration``  — anything else (reads, shell, listing, plain text).
"""

from __future__ import annotations

from typing import Iterable

SUBMISSION_TOOLS = frozenset({"submit_findings"})

COORDINATION_TOOLS = frozenset(
    {
        "shared_list",
        "shared_read",
        "shared_mkdir",
        "shared_create",
        "list_tasks",
        "create_task",
        "claim_task",
        "release_task",
        "complete_task",
        "send_message",
        "list_messages",
        "publish_artifact",
        "list_artifacts",
        "manager_create_task",
        "manager_list_tasks",
        "manager_cancel_task",
        "manager_reassign_task",
        "worker_get_assignment",
        "worker_report_task",
        "worker_request_more",
    }
)

CALL_ROLES = ("exploration", "coordination", "submission", "finalization")


def classify_call_role(tool_names: Iterable[str], *, finalization_active: bool) -> str:
    names = {str(name) for name in tool_names}
    if names & SUBMISSION_TOOLS:
        return "submission"
    if finalization_active:
        return "finalization"
    if names & COORDINATION_TOOLS:
        return "coordination"
    return "exploration"
