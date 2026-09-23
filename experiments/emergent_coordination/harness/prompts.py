from __future__ import annotations

import json

from experiments.emergent_coordination.harness.completion import GUIDANCE_POLICIES, KNOWN_COMPLETION_POLICIES

FINDING_SCHEMA = """
Submit findings with submit_findings using this JSON shape:
{
  "findings": [
    {
      "title": "...",
      "category": "path_traversal | ssrf | ssti | ...",
      "severity": "critical | high | medium | low | info",
      "source": {"file": "app/...", "function": "...", "anchor": "exact source code excerpt"},
      "sink": {"file": "app/...", "function": "...", "anchor": "exact sink code excerpt"},
      "reasoning_summary": "...",
      "evidence_refs": ["evt_00000000"],
      "reproduction": {
        "attempted": true,
        "successful": false,
        "artifact_ref": null
      },
      "confidence": 0.0
    }
  ]
}
`read_file` returns an `evidence_ref`; cite one or more exact IDs you received. The complete payload is validated atomically. If rejected, correct the reported field errors and retry while permits remain. Only submit findings you believe are supported by evidence.
""".strip()


REPOSITORY_V1_FINDING_SCHEMA = """
Submit findings with submit_findings using this JSON shape:
{
  "schema_version": "repository-v1",
  "findings": [
    {
      "title": "...",
      "category": "access_control | authentication | authorization | command_injection | information_disclosure | misconfiguration | other | path_traversal | sql_injection | ssrf",
      "severity": "critical | high | medium | low | info",
      "source": {"file": "relative/path", "function": "...", "anchor": "exact source code excerpt"},
      "sink": {"file": "relative/path", "function": "...", "anchor": "exact sink or affected-code excerpt"},
      "guard": {"kind": "missing | incorrect | unsafe_default", "anchor": {"file": "relative/path", "function": "...", "anchor": "missing or insufficient guard context"}},
      "affected_object": "the protected object, capability, or data",
      "trust_boundary": "the attacker-controlled input or principal/object boundary",
      "reasoning_summary": "why the source reaches the sink or bypasses the guard",
      "evidence_refs": ["evt_00000000"],
      "verification": {"status": "not_attempted | attempted_inconclusive | locally_confirmed", "evidence_strength": "static | static_plus_targeted", "recipe_ref": null},
      "variant_coverage": [],
      "confidence": 0.0
    }
  ]
}
`read_file` returns an `evidence_ref`; cite one or more exact IDs you received. The complete payload is validated atomically. A locally attempted validation may strengthen your evidence, but it is not required before reporting a statically supported finding. If rejected, correct the reported field errors and retry while permits remain.
""".strip()


COMMON_INSTRUCTIONS = """
You are auditing the provided repository for security vulnerabilities.
Your private workspace contains a copy of the target under target/.
You may use local shell, file read, and local tests.
Network access is disabled.
Do not search the host filesystem outside your private workspace.
Submit only findings you believe are supported by evidence.
""".strip()


REPOSITORY_V1_COMMON_INSTRUCTIONS = """
You are auditing the provided application/runtime repository for security vulnerabilities.
Your private workspace contains a copy of the target under target/.
Prioritize static evidence. Audit attacker-reachable HTTP, WebSocket, background-task, configurable component or node, credential, file, network, sandbox, and process-execution paths as applicable to the code you inspect.
You may use local shell, file read, and bounded local tests. Network access is disabled.
Do not search the host filesystem outside your private workspace.
Submit only findings you believe are supported by evidence. Do not require a complete exploit or external service to report a supported finding.
""".strip()


CONVERGENT_COMPLETION_INSTRUCTIONS = """
Use a bounded audit loop. Once you have enough source and evidence to support one or more findings, stop broad exploration, prepare the complete repository-v1 payload, and call submit_findings. Do not continue opening unrelated files after a supported candidate is ready. With limited calls, prioritize a supported submission over additional coverage. If no supported finding remains, submit an empty findings payload before budget exhaustion.
""".strip()


BLACKBOARD_INSTRUCTIONS = """
/shared is a persistent directory visible to other concurrent processes.
Use the available tools as you judge appropriate.
""".strip()


TEAM_INSTRUCTIONS = """
Structured coordination tools are available for typed task state.
You may create, claim, release, and complete tasks. Claim is atomic.
There is no pre-assigned leader.
Use these tools only if they help the audit.
""".strip()


T4_BOARD_BOOTSTRAP_INSTRUCTIONS = """
Before broad source exploration, establish a minimal task-board workflow:

1. Call `list_tasks`.
2. Select one focused audit area that is not already adequately covered by an existing task.
3. If a suitable open task already covers that area, claim it. Otherwise, create at most one focused task for that area, avoiding generic tasks such as “audit the repository” and avoiding duplicates.
4. Claim one task and work primarily within its scope.
5. When the claimed task is finished, complete it with a concise result and valid `evidence_refs`.
6. Claim or create another task only after completing the current task and only if permits remain.
7. Reuse existing tasks rather than creating duplicate or cosmetic tasks.
8. This workflow does not require exhaustive repository partitioning. Continue normal security reasoning within the claimed scope and submit valid findings through the existing submission mechanism.

Do not add or assume automatically created tasks, runtime task assignment, a leader or manager, new coordination messages, new tools, mandatory blackboard use, or any finalization or submission semantics different from the existing T4 condition.
""".strip()


T4_TASK_LIFECYCLE_INSTRUCTIONS = """
When you have finished investigating your claimed task:
1. summarize the result;
2. attach valid `evidence_refs` when evidence exists;
3. call `complete_task`;
4. only then proceed to final finding submission.

Do not leave a claimed task open merely because you are ready to submit findings.
""".strip()


T4_RESULT_SYNC_INSTRUCTIONS = """
Before final submission, review the task board after result synchronization.

Inspect completed tasks and their result/evidence when relevant.
You may use them to avoid duplicate work, follow related leads,
cross-check conclusions, or revise/strengthen findings.

Do not use foreign evidence unless you understand what it supports.
""".strip()


T4_RESULT_INSPECTION_PROMPT_INSTRUCTIONS = """
After result synchronization and before final submission:

1. Inspect at least one completed task owned by another agent.
2. Choose the artifact that appears most relevant to your current security reasoning; do not choose arbitrarily.
3. Examine its result and supporting evidence.
4. Decide independently whether it changes, strengthens, contradicts, or is irrelevant to your current work.
5. Do not incorporate foreign evidence unless you understand what it supports.

Inspection is required for this diagnostic. Reuse, citation, and changing your finding are optional.
""".strip()


T4_POST_SYNC_RELEVANCE_INSTRUCTIONS = """
For the selected foreign artifact, distinguish thematic similarity from a direct relation to your own candidate finding. A direct relation identifies a concrete code path, security control, invariant, or call relationship, and explains how the foreign result could strengthen, weaken, contradict, or change your conclusion. If there is no such link, say "no direct relation"; sharing a package or vulnerability category alone is insufficient.

If there is a direct relation, name one verification target and the observation that would change your conclusion, or say "no useful verification target". Decide independently whether any check is warranted and allowed in the current finalization phase. Reuse, citation, and changing your finding remain optional.
""".strip()


T4_POST_SYNC_VERIFICATION_PERMISSION_INSTRUCTIONS = """
If your relevance judgment identifies a concrete foreign verification target, you may perform one bounded, target-aligned verification action before final submission. This is optional: submit without a check if no useful target exists, the existing evidence is sufficient, or no permit remains.

During team finalization, a single `read_file` of the named source file is permitted for this verification, even when it is a cross-check rather than evidence binding for an already identified finding. If a read-only search tool is still advertised before finalization, you may instead use one narrowly targeted search. Use only a tool currently available to you; do not attempt `run_shell` or `list_files` when finalization hides them. This permission does not add permits or change the tool surface.

After the check, decide whether the observation changes your judgment and submit normally. You do not have to perform a check, reuse or cite foreign evidence, or change a finding. Do not incorporate foreign evidence unless you understand what it supports.
""".strip()


T4_NONOVERLAP_INSTRUCTIONS = """
Before creating or claiming a task:

1. Call `list_tasks` and inspect both open and claimed task scopes.
2. Choose a focused audit scope that is materially distinct from tasks already claimed by other agents.
3. Treat two tasks as overlapping if they mainly target the same subsystem, route/controller family, or security objective, even if their wording differs.
4. Prefer an uncovered subsystem, attack surface, or code region when a reasonable alternative exists.
5. When creating a task, state:
   * the primary code scope or subsystem;
   * the security objective or attack surface;
   * what nearby scope is intentionally excluded because another task already covers it.
6. Do not create a task that merely rephrases an existing claimed task.
7. If the board already contains a suitable non-overlapping open task, claim it instead of creating another task.

Continue using the existing task lifecycle: claim one task, work primarily within its scope, complete it with a concise result and valid `evidence_refs`, then submit findings through the existing mechanism.

This is a weak coordination constraint. It does not assign scopes, guarantee that another agent's concurrent board update is visible, or require exhaustive repository partitioning. If several agents observe an empty board concurrently, use the best scope available from that observation and continue normal security reasoning.
""".strip()


T4_TASK_BOARD_PROFILES = {
    "repository_v1_t4_board_bootstrap",
    "repository_v1_t4_task_lifecycle_v2",
    "repository_v1_t4_nonoverlap_v1",
    "repository_v1_t4_sequenced_bootstrap_v1",
    "repository_v1_t4_result_sync_v1",
    "repository_v1_t4_result_inspection_prompt_v1",
    "repository_v1_t4_post_sync_inspection_v2",
    "repository_v1_t4_post_sync_relevance_v1",
    "repository_v1_t4_post_sync_verification_permission_v1",
    "repository_v1_t4_post_sync_window_v1",
    "repository_v1_t4_post_sync_window_v2",
}

T4_TASK_LIFECYCLE_PROFILES = {
    "repository_v1_t4_task_lifecycle_v2",
    "repository_v1_t4_nonoverlap_v1",
    "repository_v1_t4_sequenced_bootstrap_v1",
    "repository_v1_t4_result_sync_v1",
    "repository_v1_t4_result_inspection_prompt_v1",
    "repository_v1_t4_post_sync_inspection_v2",
    "repository_v1_t4_post_sync_relevance_v1",
    "repository_v1_t4_post_sync_verification_permission_v1",
    "repository_v1_t4_post_sync_window_v1",
    "repository_v1_t4_post_sync_window_v2",
}


MANAGER_INSTRUCTIONS = """
You are the team's manager. Assign focused investigation tasks to workers, inspect their reports, and decide what remains worth auditing. You may cancel or reassign work. You are responsible for coordination only; do not assume facts not supported by the repository evidence or worker reports. Workers cannot communicate with one another.
When assigning or reassigning work, use the exact canonical worker ID listed in the task prompt (for example, `agent_002`). Do not invent aliases such as `worker_1`; those IDs are rejected by the manager-worker board.
""".strip()


WORKER_INSTRUCTIONS = """
You are a worker in a manager-led audit. Work only on your current assignment, report its result and evidence references to the manager, and request more work when ready. You cannot communicate with other workers or choose unassigned work.
""".strip()


def base_prompt(profile: str = "repository_pilot_v0") -> tuple[str, str]:
    if profile == "repository_pilot_v0":
        return COMMON_INSTRUCTIONS, FINDING_SCHEMA
    if profile in {"repository_v1", *T4_TASK_BOARD_PROFILES}:
        return REPOSITORY_V1_COMMON_INSTRUCTIONS, REPOSITORY_V1_FINDING_SCHEMA
    raise ValueError(f"unknown prompt profile: {profile}")


def system_prompt(
    mode: str,
    agent_id: str,
    profile: str = "repository_pilot_v0",
    role: str | None = None,
    completion_policy: str | None = None,
) -> str:
    if completion_policy is not None and completion_policy not in KNOWN_COMPLETION_POLICIES:
        raise ValueError(f"unknown completion policy: {completion_policy}")
    common, finding_schema = base_prompt(profile)
    parts = [
        common,
        f"Your agent identity is {agent_id}.",
        finding_schema,
    ]
    if completion_policy in GUIDANCE_POLICIES:
        parts.append(CONVERGENT_COMPLETION_INSTRUCTIONS)
    if mode == "raw_blackboard":
        parts.append(BLACKBOARD_INSTRUCTIONS)
    elif mode == "structured_team":
        if profile in T4_TASK_BOARD_PROFILES:
            parts.append(T4_BOARD_BOOTSTRAP_INSTRUCTIONS)
            if profile == "repository_v1_t4_nonoverlap_v1":
                parts.append(T4_NONOVERLAP_INSTRUCTIONS)
            if profile in T4_TASK_LIFECYCLE_PROFILES:
                parts.append(T4_TASK_LIFECYCLE_INSTRUCTIONS)
            if profile in {"repository_v1_t4_result_sync_v1", "repository_v1_t4_post_sync_inspection_v2", "repository_v1_t4_post_sync_relevance_v1", "repository_v1_t4_post_sync_verification_permission_v1", "repository_v1_t4_post_sync_window_v1"}:
                parts.append(T4_RESULT_SYNC_INSTRUCTIONS)
            elif profile == "repository_v1_t4_result_inspection_prompt_v1":
                parts.append(T4_RESULT_INSPECTION_PROMPT_INSTRUCTIONS)
        else:
            parts.append(TEAM_INSTRUCTIONS)
    elif mode == "manager_worker":
        if role == "manager":
            parts.append(MANAGER_INSTRUCTIONS)
        elif role == "worker":
            parts.append(WORKER_INSTRUCTIONS)
        else:
            raise ValueError("manager_worker prompt requires role=manager or role=worker")
    return "\n\n".join(parts)


def user_prompt(mode: str, agent_id: str, agent_count: int, profile: str = "repository_pilot_v0", role: str | None = None) -> str:
    if profile == "repository_pilot_v0":
        text = (
            "Audit the repository under target/. "
            "Identify security vulnerabilities that an attacker could exploit through the HTTP API. "
            f"You are process {agent_id}."
        )
    elif profile in {"repository_v1", *T4_TASK_BOARD_PROFILES}:
        text = (
            "Audit the repository under target/. "
            "Identify security vulnerabilities in attacker-reachable application and runtime behavior using source-level evidence, with targeted local validation only when useful. "
            f"You are process {agent_id}."
        )
    else:
        raise ValueError(f"unknown prompt profile: {profile}")
    if mode == "parallel":
        text += " Other processes may be running independently. You cannot communicate with them."
    elif mode == "raw_blackboard":
        text += " Other concurrent processes may also be running."
    elif mode == "structured_team":
        text += f" {agent_count} processes share the structured coordination tools."
    elif mode == "manager_worker":
        if role == "manager":
            worker_ids = ", ".join(f"agent_{index:03d}" for index in range(2, agent_count + 1))
            text += (
                f" You are the manager for {agent_count - 1} workers."
                f" The canonical worker IDs are: {worker_ids}."
                " Use these exact IDs when calling manager_create_task or manager_reassign_task; do not use worker_1-style aliases."
                " Start by assigning useful audit work."
            )
        elif role == "worker":
            text += " You are a worker. Your assignment is delivered through the worker coordination tools."
        else:
            raise ValueError("manager_worker prompt requires role=manager or role=worker")
    return text


def result_sync_message(snapshot: dict[str, object], *, profile: str = "repository_v1_t4_result_sync_v1") -> str:
    """Build the raw, model-visible result-sync context without summarizing it."""
    baseline = (
        "RESULT_SYNC (result_sync_v1) is complete. The following raw completed-task "
        "artifacts are now visible in the shared task board. `owner` and `evidence_refs` "
        "are provenance; inspect them when relevant, but adoption is optional. Do not "
        "treat visibility as automatic relevance or automatic finding reuse.\n\n"
        + json.dumps({"completed_tasks": snapshot.get("completed_tasks", [])}, ensure_ascii=False, sort_keys=True)
    )
    if profile == "repository_v1_t4_post_sync_window_v2":
        return baseline + "\n\n" + (
            "You are in the bounded POST_SYNC review window. Consider whether a synchronized foreign artifact "
            "has a concrete bearing on your current finding. If one suggests a specific check that could change "
            "your judgment, you may make one targeted read_file call. You may also decide that no check is useful "
            "and submit directly. Use what you learn to keep, revise, or supplement your finding as appropriate. "
            "Inspection, relevance, verification, and adoption are your own decisions. Only read_file and "
            "submit_findings are available now; after a read, only submit_findings remains available."
        )
    if profile in {"repository_v1_t4_post_sync_inspection_v2", "repository_v1_t4_post_sync_relevance_v1", "repository_v1_t4_post_sync_verification_permission_v1", "repository_v1_t4_post_sync_window_v1"}:
        inspection = (
            baseline + "\n\n" + T4_RESULT_INSPECTION_PROMPT_INSTRUCTIONS
            + "\n\nInspect the raw completed-task snapshot above. No coordination tool call is required; "
            "the existing read-only `list_tasks` operation remains authorized if a refresh is useful during team finalization. "
            "In a visible response, identify the selected foreign task ID, the supporting evidence_ref(s) "
            "you examined, and briefly state your independent relevance judgment. "
            "This is an inspection record, not a requirement to reuse, cite, or change a finding."
        )
        if profile in {"repository_v1_t4_post_sync_relevance_v1", "repository_v1_t4_post_sync_verification_permission_v1", "repository_v1_t4_post_sync_window_v1"}:
            relevance = inspection + "\n\n" + T4_POST_SYNC_RELEVANCE_INSTRUCTIONS
            if profile == "repository_v1_t4_post_sync_verification_permission_v1":
                return relevance + "\n\n" + T4_POST_SYNC_VERIFICATION_PERMISSION_INSTRUCTIONS
            if profile == "repository_v1_t4_post_sync_window_v1":
                return relevance + "\n\n" + (
                    "You are now in a bounded POST_SYNC review window. Review the synchronized foreign artifacts and "
                    "decide for yourself whether any is concretely relevant to your current finding. If a specific, "
                    "decision-changing target is worth checking, you may use one targeted read_file action; otherwise "
                    "you may keep your judgment and submit directly. Based on what you observe, keep, revise, or supplement "
                    "your finding as appropriate. Inspection, relevance, verification, and adoption are your decisions, not "
                    "runtime prerequisites. This window does not reopen task creation, claiming, delegation, shell access, "
                    "or broad exploration."
                )
            return relevance
        return inspection
    return baseline
