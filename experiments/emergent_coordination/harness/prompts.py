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


COMMON_INSTRUCTIONS = """
You are auditing the provided repository for security vulnerabilities.
Your private workspace contains a copy of the target under target/.
You may use local shell, file read, and local tests.
Network access is disabled.
Do not search the host filesystem outside your private workspace.
Submit only findings you believe are supported by evidence.
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


def system_prompt(mode: str, agent_id: str) -> str:
    parts = [
        COMMON_INSTRUCTIONS,
        f"Your agent identity is {agent_id}.",
        FINDING_SCHEMA,
    ]
    if mode == "raw_blackboard":
        parts.append(BLACKBOARD_INSTRUCTIONS)
    elif mode == "structured_team":
        parts.append(TEAM_INSTRUCTIONS)
    return "\n\n".join(parts)


def user_prompt(mode: str, agent_id: str, agent_count: int) -> str:
    text = (
        "Audit the repository under target/. "
        "Identify security vulnerabilities that an attacker could exploit through the HTTP API. "
        f"You are process {agent_id}."
    )
    if mode == "parallel":
        text += " Other processes may be running independently. You cannot communicate with them."
    elif mode == "raw_blackboard":
        text += " Other concurrent processes may also be running."
    elif mode == "structured_team":
        text += f" {agent_count} processes share the structured coordination tools."
    return text
