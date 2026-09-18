from __future__ import annotations

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


MANAGER_INSTRUCTIONS = """
You are the team's manager. Assign focused investigation tasks to workers, inspect their reports, and decide what remains worth auditing. You may cancel or reassign work. You are responsible for coordination only; do not assume facts not supported by the repository evidence or worker reports. Workers cannot communicate with one another.
""".strip()


WORKER_INSTRUCTIONS = """
You are a worker in a manager-led audit. Work only on your current assignment, report its result and evidence references to the manager, and request more work when ready. You cannot communicate with other workers or choose unassigned work.
""".strip()


def base_prompt(profile: str = "repository_pilot_v0") -> tuple[str, str]:
    if profile == "repository_pilot_v0":
        return COMMON_INSTRUCTIONS, FINDING_SCHEMA
    if profile == "repository_v1":
        return REPOSITORY_V1_COMMON_INSTRUCTIONS, REPOSITORY_V1_FINDING_SCHEMA
    raise ValueError(f"unknown prompt profile: {profile}")


def system_prompt(mode: str, agent_id: str, profile: str = "repository_pilot_v0", role: str | None = None) -> str:
    common, finding_schema = base_prompt(profile)
    parts = [
        common,
        f"Your agent identity is {agent_id}.",
        finding_schema,
    ]
    if mode == "raw_blackboard":
        parts.append(BLACKBOARD_INSTRUCTIONS)
    elif mode == "structured_team":
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
    elif profile == "repository_v1":
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
            text += f" You are the manager for {agent_count - 1} workers. Start by assigning useful audit work."
        elif role == "worker":
            text += " You are a worker. Your assignment is delivered through the worker coordination tools."
        else:
            raise ValueError("manager_worker prompt requires role=manager or role=worker")
    return text
