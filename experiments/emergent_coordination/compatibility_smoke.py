#!/usr/bin/env python3
"""Probe the configured provider without creating a coordination experiment.

This validates OpenAI-compatible request/response and function-call handling.
It intentionally does not mount the audit target, run an Agent, or score a
finding, so its result cannot be interpreted as an S/P/B/T experiment.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.emergent_coordination.harness.llm.client import client_from_env


PROBE_TOOL = {
    "type": "function",
    "function": {
        "name": "compatibility_echo",
        "description": "Return the supplied probe value unchanged.",
        "parameters": {
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
            "additionalProperties": False,
        },
    },
}


def _response_metadata(response: object) -> dict:
    return {
        "model": getattr(response, "model_metadata", {}),
        "usage": getattr(response, "usage").as_dict(),
        "tool_calls": len(getattr(response, "tool_calls", [])),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a non-experimental DeepSeek compatibility probe.")
    parser.add_argument("--model", default="deepseek-flash")
    args = parser.parse_args()

    llm = client_from_env(model=args.model, thinking_mode="disabled", max_tokens=64)
    if llm is None:
        print("No LLM credentials found; refusing to call the provider.", file=sys.stderr)
        return 2

    messages = [
        {"role": "system", "content": "You are a provider compatibility probe."},
        {"role": "user", "content": "Call compatibility_echo with value 'coord-audit'."},
    ]
    try:
        first = llm.complete(
            messages,
            [PROBE_TOOL],
            agent_id="compatibility_probe",
            tool_choice={"type": "function", "function": {"name": "compatibility_echo"}},
        )
        if len(first.tool_calls) != 1 or first.tool_calls[0]["name"] != "compatibility_echo":
            raise RuntimeError("provider did not return the forced compatibility_echo tool call")
        arguments = json.loads(first.tool_calls[0]["arguments"])
        if arguments != {"value": "coord-audit"}:
            raise RuntimeError("provider returned unexpected compatibility_echo arguments")
        messages.extend(
            [
                {
                    "role": "assistant",
                    "content": first.content or "",
                    "tool_calls": [
                        {
                            "id": first.tool_calls[0]["id"],
                            "type": "function",
                            "function": {
                                "name": "compatibility_echo",
                                "arguments": first.tool_calls[0]["arguments"],
                            },
                        }
                    ],
                },
                {
                    "role": "tool",
                    "tool_call_id": first.tool_calls[0]["id"],
                    "content": "coord-audit",
                },
            ]
        )
        second = llm.complete(messages, [PROBE_TOOL], agent_id="compatibility_probe")
        if not second.content:
            raise RuntimeError("provider did not continue after the tool result")
    except Exception as exc:  # noqa: BLE001 - present a concise smoke failure
        print(json.dumps({"status": "failed", "requested_model": args.model, "error": str(exc)}))
        return 1

    print(
        json.dumps(
            {
                "status": "passed",
                "requested_model": args.model,
                "thinking_mode": "disabled",
                "first_response": _response_metadata(first),
                "second_response": _response_metadata(second),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
