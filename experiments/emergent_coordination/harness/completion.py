"""Completion-policy semantics shared by runtime, prompts, and analysis.

Two finalization generations exist and must stay distinguishable forever:

* Generation 1 (``convergent_v1``, ``scheduler_only``): the finalization
  window trims only the *advertised* tool surface; dispatch continues to
  authorize the full mode allowlist.  This is frozen historical behavior —
  the restriction is advisory and bypassable at dispatch.
* Generation 2 (``convergent_v2``, ``scheduler_only_v2``): the same
  window plus a hard dispatch-authorization gate.  While the gate is
  active only ``submit_findings`` may execute; every other requested
  tool is rejected before argument parsing, tool dispatch, or any
  sandbox access, and the attempt is recorded as a structured event.
"""

from __future__ import annotations

from typing import Any

FINALIZATION_RESERVE = 8

ADVISORY_FINALIZATION_POLICIES = frozenset({"convergent_v1", "scheduler_only"})
HARD_FINALIZATION_POLICIES = frozenset({"convergent_v2", "scheduler_only_v2"})
FINALIZATION_POLICIES = ADVISORY_FINALIZATION_POLICIES | HARD_FINALIZATION_POLICIES
GUIDANCE_POLICIES = frozenset({"guidance_only", "convergent_v1", "convergent_v2"})
KNOWN_COMPLETION_POLICIES = frozenset({"guidance_only"}) | FINALIZATION_POLICIES

# The only tools dispatch may authorize while a hard finalization gate is
# active.  An allowlist at the dispatch layer — never a name blacklist.
FINALIZATION_ALLOWED_TOOLS = frozenset({"submit_findings"})
# Team-level calibration keeps the existing tool surface available for the
# narrow evidence-binding operation that a finding payload may still require.
# Open-ended shell, coordination, and discovery calls remain gated.
TEAM_FINALIZATION_ALLOWED_TOOLS = frozenset({"submit_findings", "read_file"})

GATE_REJECTED_BY = "hard_finalization_gate"

_NEUTRAL_FINALIZATION_MESSAGE = (
    "Finalization phase: the available tool surface is now restricted to submit_findings. "
    "Use only evidence already acquired."
)
_STRONG_FINALIZATION_MESSAGE = (
    "Finalization phase: do not inspect more files or call any coordination tool. "
    "Call submit_findings now with the complete repository-v1 payload. "
    "Use only evidence already acquired; if no supported finding remains, submit an empty findings payload."
)


def finalization_message(policy: str) -> str:
    """Finalization user message, byte-identical across generations."""
    if policy in {"convergent_v1", "convergent_v2"}:
        return _STRONG_FINALIZATION_MESSAGE
    return _NEUTRAL_FINALIZATION_MESSAGE


def team_finalization_message(policy: str, *, task_lifecycle_reminder: bool = False) -> str:
    """Deterministic team-level signal used by the 96-permit calibration."""
    if policy in {"convergent_v1", "convergent_v2"}:
        message = (
            "Team finalization phase is active because the shared permit ledger reached its "
            "preregistered reserve. Stop open-ended exploration and submit the complete "
            "repository-v1 payload now. You may use read_file only to bind strictly necessary "
            "evidence for a finding already identified; do not use shell or coordination tools. "
            "If no supported finding remains, submit an empty findings payload."
        )
    else:
        message = (
        "Team finalization phase is active. Stop open-ended exploration and submit the complete "
        "finding payload; read_file is allowed only for strictly necessary evidence binding."
        )
    if task_lifecycle_reminder:
        message += " If you still own a claimed task, close it with complete_task before finishing the run."
    return message


def gate_rejection(
    tool: str,
    *,
    team_finalization: bool = False,
    task_completion_allowed: bool = False,
) -> dict[str, Any]:
    """Deterministic runtime rejection returned for a prohibited tool call.

    The payload never echoes the requested arguments and never includes
    target content, so a rejection cannot leak repository state.
    """
    return {
        "ok": False,
        "error": {
            "code": "prohibited_tool_during_finalization",
            "tool": tool,
            "rejected_by": GATE_REJECTED_BY,
            "message": (
                (
                    "The team finalization phase is active; only submit_findings, read_file "
                    "for necessary evidence binding, and complete_task for closing a claimed task "
                    "may be dispatched."
                    if task_completion_allowed
                    else "The team finalization phase is active; only submit_findings and read_file "
                    "for necessary evidence binding may be dispatched."
                )
                if team_finalization
                else "The finalization phase is active; only submit_findings may be dispatched. "
                "Build your submission from evidence already acquired."
            ),
        },
    }
