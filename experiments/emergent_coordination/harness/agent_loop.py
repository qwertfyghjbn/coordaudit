from __future__ import annotations

import json
from typing import Any

from experiments.emergent_coordination.harness.budget import BudgetExhausted, BudgetTracker
from experiments.emergent_coordination.harness.events import EventLog
from experiments.emergent_coordination.harness.llm.client import LLMClient
from experiments.emergent_coordination.harness.prompts import system_prompt, user_prompt
from experiments.emergent_coordination.harness.tools.sandbox import AgentSandbox, ToolError
from experiments.emergent_coordination.harness.tools.specs import tools_for_mode


class AgentRunner:
    def __init__(
        self,
        *,
        agent_id: str,
        mode: str,
        agent_count: int,
        sandbox: AgentSandbox,
        llm: LLMClient,
        event_log: EventLog,
        budget: BudgetTracker,
        max_steps: int = 12,
    ):
        self.agent_id = agent_id
        self.mode = mode
        self.agent_count = agent_count
        self.sandbox = sandbox
        self.llm = llm
        self.event_log = event_log
        self.budget = budget
        self.max_steps = max_steps

    def run(self) -> dict[str, Any]:
        self.event_log.emit("agent_started", agent_id=self.agent_id, payload={"mode": self.mode})
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt(self.mode, self.agent_id)},
            {"role": "user", "content": user_prompt(self.mode, self.agent_id, self.agent_count)},
        ]
        tools = tools_for_mode(self.mode)
        stop_reason = "completed"
        try:
            for _step in range(self.max_steps):
                response = self.llm.complete(messages, tools, agent_id=self.agent_id)
                self.budget.charge(self.agent_id, response.usage)
                self.event_log.emit(
                    "llm_call",
                    agent_id=self.agent_id,
                    payload={"model": response.usage.model, "tool_calls": len(response.tool_calls)},
                    token_usage=response.usage.as_dict(),
                )
                if response.tool_calls:
                    messages.append(
                        {
                            "role": "assistant",
                            "content": response.content or "",
                            "tool_calls": [
                                {
                                    "id": call["id"],
                                    "type": "function",
                                    "function": {
                                        "name": call["name"],
                                        "arguments": call["arguments"],
                                    },
                                }
                                for call in response.tool_calls
                            ],
                        }
                    )
                    for call in response.tool_calls:
                        result = self._dispatch(call["name"], call.get("arguments") or "{}")
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": call["id"],
                                "name": call["name"],
                                "content": _truncate(result),
                            }
                        )
                    if self.sandbox._submitted is not None:
                        stop_reason = "submitted"
                        break
                    continue
                if response.content:
                    maybe = _extract_findings(response.content)
                    if maybe is not None:
                        self.sandbox.submit_findings(maybe)
                        stop_reason = "submitted"
                        break
                    messages.append({"role": "assistant", "content": response.content})
                    messages.append(
                        {
                            "role": "user",
                            "content": "If you have finished, call submit_findings with your JSON findings.",
                        }
                    )
            else:
                stop_reason = "max_steps"
        except BudgetExhausted as exc:
            stop_reason = "budget_exhausted"
            self.event_log.emit(
                "budget_exhausted",
                agent_id=self.agent_id,
                payload={"reason": exc.reason, "snapshot": exc.snapshot},
            )
        except Exception as exc:  # noqa: BLE001 - run must record unexpected failures
            stop_reason = "error"
            self.event_log.emit(
                "error",
                agent_id=self.agent_id,
                payload={"error": str(exc), "type": type(exc).__name__},
            )
        findings = self.sandbox._submitted or {"findings": []}
        self.event_log.emit(
            "agent_finished",
            agent_id=self.agent_id,
            payload={"reason": stop_reason, "finding_count": len(findings.get("findings", []))},
        )
        return {
            "agent_id": self.agent_id,
            "stop_reason": stop_reason,
            "findings": findings,
        }

    def _dispatch(self, name: str, raw_arguments: str) -> str:
        try:
            args = json.loads(raw_arguments) if raw_arguments else {}
        except json.JSONDecodeError:
            args = {}
        self.event_log.emit(
            "tool_call",
            agent_id=self.agent_id,
            payload={"tool": name, "arguments": args},
        )
        try:
            result = self._call(name, args)
            return json.dumps(result, ensure_ascii=False, default=str)
        except ToolError as exc:
            return json.dumps({"error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": str(exc), "type": type(exc).__name__})

    def _call(self, name: str, args: dict[str, Any]) -> Any:
        mapping = {
            "list_files": lambda: self.sandbox.list_files(args.get("path", "target")),
            "read_file": lambda: self.sandbox.read_file(args["path"]),
            "write_file": lambda: self.sandbox.write_file(args["path"], args.get("content", "")),
            "run_shell": lambda: self.sandbox.run_shell(args["command"], int(args.get("timeout", 30))),
            "submit_findings": lambda: self.sandbox.submit_findings(args.get("findings", [])),
            "shared_list": lambda: self.sandbox.shared_list(args.get("path", ".")),
            "shared_read": lambda: self.sandbox.shared_read(args["path"]),
            "shared_mkdir": lambda: self.sandbox.shared_mkdir(args["path"]),
            "shared_create": lambda: self.sandbox.shared_create(
                args["path"], args.get("content", ""), bool(args.get("append", False))
            ),
            "list_tasks": lambda: self.sandbox.list_tasks(),
            "create_task": lambda: self.sandbox.create_task(args["description"], args.get("dependencies")),
            "claim_task": lambda: self.sandbox.claim_task(args["task_id"]),
            "release_task": lambda: self.sandbox.release_task(args["task_id"]),
            "complete_task": lambda: self.sandbox.complete_task(args["task_id"], args.get("result_artifacts")),
            "send_message": lambda: self.sandbox.send_message(args["to"], args["body"]),
            "list_messages": lambda: self.sandbox.list_messages(),
            "publish_artifact": lambda: self.sandbox.publish_artifact(args["name"], args["content"]),
            "list_artifacts": lambda: self.sandbox.list_artifacts(),
        }
        if name not in mapping:
            raise ToolError(f"unknown tool: {name}")
        return mapping[name]()


def _extract_findings(content: str) -> dict[str, Any] | None:
    text = content.strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            parsed = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    if isinstance(parsed, dict) and "findings" in parsed:
        return parsed
    return None


def _truncate(text: str, limit: int = 12000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...[truncated]..."
