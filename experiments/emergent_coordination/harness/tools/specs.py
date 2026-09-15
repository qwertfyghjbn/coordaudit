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
            "description": "Read a text file from the private workspace.",
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
            "description": "Submit the final machine-readable findings JSON for this agent.",
            "parameters": {
                "type": "object",
                "properties": {
                    "findings": {
                        "type": "array",
                        "items": {"type": "object"},
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
            "description": "Mark a claimed task completed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string"},
                    "result_artifacts": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["task_id"],
            },
        },
    },
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


def tools_for_mode(mode: str) -> list[dict[str, Any]]:
    tools = list(COMMON_TOOLS)
    if mode == "raw_blackboard":
        tools.extend(BLACKBOARD_TOOLS)
    elif mode == "structured_team":
        tools.extend(TEAM_TOOLS)
    return tools
