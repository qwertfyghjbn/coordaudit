from __future__ import annotations

from typing import Any


COMMON_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files under the private workspace. The target snapshot lives under target/.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Relative path under the private workspace."}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a text file and return its content with an evidence_ref. Use that exact evidence_ref in submitted findings.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write a text file under scratch/. The target snapshot is read-only.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_shell",
            "description": "Run a local shell command inside the private workspace. Network access is disabled.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "timeout": {"type": "integer"},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_findings",
            "description": "Atomically submit the final frozen finding payload. Invalid payloads return field errors and may be retried while permits remain.",
            "parameters": {
                "type": "object",
                "properties": {
                    "findings": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["title", "category", "severity", "source", "sink", "reasoning_summary", "evidence_refs", "reproduction", "confidence"],
                            "properties": {
                                "title": {"type": "string"},
                                "category": {"type": "string", "enum": ["path_traversal", "ssrf", "ssti", "command_injection", "sql_injection", "deserialization", "access_control", "authentication", "authorization", "information_disclosure", "cryptographic", "misconfiguration", "other"]},
                                "severity": {"type": "string", "enum": ["critical", "high", "medium", "low", "info"]},
                                "source": {"type": "object"},
                                "sink": {"type": "object"},
                                "reasoning_summary": {"type": "string"},
                                "evidence_refs": {"type": "array", "items": {"type": "string"}},
                                "reproduction": {"type": "object"},
                                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                            },
                        },
                    }
                },
                "required": ["findings"],
            },
        },
    },
]


BLACKBOARD_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "shared_list",
            "description": "List entries in the persistent shared directory.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "shared_read",
            "description": "Read a file from the persistent shared directory.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "shared_mkdir",
            "description": "Create a directory in the persistent shared directory.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "shared_create",
            "description": "Create a new file in the persistent shared directory. Existing files cannot be overwritten unless append=true.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                    "append": {"type": "boolean"},
                },
                "required": ["path", "content"],
            },
        },
    },
]


# The primary N=4 T4 treatment is deliberately limited to typed task state.
# Messaging and artifact APIs remain implemented in the dispatcher for later,
# separately frozen ablations; they must not leak into this matched block.
TEAM_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_tasks",
            "description": "List coordination tasks.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_task",
            "description": "Create a coordination task.",
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                    "dependencies": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "claim_task",
            "description": "Atomically claim an open task.",
            "parameters": {
                "type": "object",
                "properties": {"task_id": {"type": "string"}},
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "release_task",
            "description": "Release a claimed task back to open.",
            "parameters": {
                "type": "object",
                "properties": {"task_id": {"type": "string"}},
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "complete_task",
            "description": "Mark a claimed task completed with a result and evidence references.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string"},
                    "result": {"type": "string"},
                    "evidence_refs": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["task_id"],
            },
        },
    },
]


FUTURE_TEAM_EXTENSION_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "send_message",
            "description": "Send a message to another agent id or to '*'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["to", "body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_messages",
            "description": "List messages visible to this agent.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "publish_artifact",
            "description": "Publish a named artifact into shared coordination state.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["name", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_artifacts",
            "description": "List published artifacts.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


MANAGER_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "manager_create_task",
            "description": "Assign one investigation task to one worker.",
            "parameters": {
                "type": "object",
                "properties": {"worker_id": {"type": "string"}, "description": {"type": "string"}},
                "required": ["worker_id", "description"],
            },
        },
    },
    {
        "type": "function",
        "function": {"name": "manager_list_tasks", "description": "List assigned tasks and worker reports.", "parameters": {"type": "object", "properties": {}}},
    },
    {
        "type": "function",
        "function": {
            "name": "manager_cancel_task",
            "description": "Cancel an assigned task.",
            "parameters": {"type": "object", "properties": {"task_id": {"type": "string"}, "reason": {"type": "string"}}, "required": ["task_id", "reason"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "manager_reassign_task",
            "description": "Move an assigned or cancelled task to a worker.",
            "parameters": {"type": "object", "properties": {"task_id": {"type": "string"}, "worker_id": {"type": "string"}}, "required": ["task_id", "worker_id"]},
        },
    },
]


MANAGER_WORKER_TOOLS = [
    {
        "type": "function",
        "function": {"name": "worker_get_assignment", "description": "Read your currently assigned task, if any.", "parameters": {"type": "object", "properties": {}}},
    },
    {
        "type": "function",
        "function": {
            "name": "worker_report_task",
            "description": "Report the result and evidence references for your assigned task to the manager.",
            "parameters": {"type": "object", "properties": {"task_id": {"type": "string"}, "result": {"type": "string"}, "evidence_refs": {"type": "array", "items": {"type": "string"}}}, "required": ["task_id", "result", "evidence_refs"]},
        },
    },
    {
        "type": "function",
        "function": {"name": "worker_request_more", "description": "Tell the manager that you are ready for another assignment.", "parameters": {"type": "object", "properties": {}}},
    },
]


REPOSITORY_V1_SUBMIT_FINDINGS_TOOL = {
    "type": "function",
    "function": {
        "name": "submit_findings",
        "description": "Atomically submit the final repository-v1 finding payload. Invalid payloads return field errors and may be retried while permits remain.",
        "parameters": {
            "type": "object",
            "properties": {
                "schema_version": {"type": "string", "enum": ["repository-v1"]},
                "findings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["title", "category", "severity", "source", "sink", "guard", "affected_object", "trust_boundary", "reasoning_summary", "evidence_refs", "verification", "variant_coverage", "confidence"],
                        "properties": {
                            "title": {"type": "string"},
                            "category": {"type": "string", "enum": ["access_control", "authentication", "authorization", "command_injection", "information_disclosure", "misconfiguration", "other", "path_traversal", "sql_injection", "ssrf"]},
                            "severity": {"type": "string", "enum": ["critical", "high", "medium", "low", "info"]},
                            "source": {"type": "object"},
                            "sink": {"type": "object"},
                            "guard": {"type": "object"},
                            "affected_object": {"type": "string"},
                            "trust_boundary": {"type": "string"},
                            "reasoning_summary": {"type": "string"},
                            "evidence_refs": {"type": "array", "items": {"type": "string"}},
                            "verification": {"type": "object"},
                            "variant_coverage": {"type": "array", "items": {"type": "object"}},
                            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        },
                    },
                },
            },
            "required": ["schema_version", "findings"],
        },
    },
}


def tools_for_mode(mode: str, finding_schema: str = "repository_pilot_v0", role: str | None = None) -> list[dict[str, Any]]:
    tools = list(COMMON_TOOLS)
    if finding_schema == "repository_v1":
        tools[-1] = REPOSITORY_V1_SUBMIT_FINDINGS_TOOL
    elif finding_schema != "repository_pilot_v0":
        raise ValueError(f"unknown finding schema: {finding_schema}")
    if mode == "raw_blackboard":
        tools.extend(BLACKBOARD_TOOLS)
    elif mode == "structured_team":
        tools.extend(TEAM_TOOLS)
    elif mode == "manager_worker":
        if role == "manager":
            tools.extend(MANAGER_TOOLS)
        elif role == "worker":
            tools.extend(MANAGER_WORKER_TOOLS)
        else:
            raise ValueError("manager_worker tools require role=manager or role=worker")
    return tools
