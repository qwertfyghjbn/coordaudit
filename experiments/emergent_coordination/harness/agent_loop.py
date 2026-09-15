from __future__ import annotations

import json
import time
from typing import Any

from experiments.emergent_coordination.harness.budget import BudgetExhausted, BudgetTracker
from experiments.emergent_coordination.harness.events import EventLog, TranscriptLog
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
        transcript_log: TranscriptLog,
        budget: BudgetTracker,
        max_steps: int = 12,
        max_provider_retries: int = 0,
    ):
        self.agent_id = agent_id
        self.mode = mode
        self.agent_count = agent_count
        self.sandbox = sandbox
        self.llm = llm
        self.event_log = event_log
        self.transcript_log = transcript_log
        self.budget = budget
        self.max_steps = max_steps
        self.max_provider_retries = max_provider_retries
        self._allowed_tools = frozenset(item["function"]["name"] for item in tools_for_mode(mode))

    def run(self) -> dict[str, Any]:
        started = self.event_log.emit("agent_started", agent_id=self.agent_id, payload={"mode": self.mode})
        last_event_id = started["event_id"]
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt(self.mode, self.agent_id)},
            {"role": "user", "content": user_prompt(self.mode, self.agent_id, self.agent_count)},
        ]
        tools = tools_for_mode(self.mode)
        stop_reason = "completed"
        try:
            for _step in range(self.max_steps):
                response, response_transcript, call_event_id = self._complete_with_permit(
                    messages, tools, step=_step + 1, parent_event_id=last_event_id
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
                        result = self._dispatch(
                            call["name"], call.get("arguments") or "{}", parent_event_id=call_event_id
                        )
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": call["id"],
                                "name": call["name"],
                                "content": _truncate(result),
                            }
                        )
                        self.transcript_log.tool_result(
                            agent_id=self.agent_id,
                            tool_call_id=call["id"],
                            name=call["name"],
                            content=_truncate(result),
                            parent_refs=[response_transcript["transcript_id"]],
                        )
                        last_event_id = call_event_id
                    if self.sandbox._submitted is not None:
                        stop_reason = "submitted"
                        break
                    continue
                if response.content:
                    maybe = _extract_findings(response.content)
                    if maybe is not None:
                        submission = self.sandbox.submit_findings(maybe)
                        if submission.get("ok"):
                            stop_reason = "submitted"
                            break
                        messages.append({"role": "assistant", "content": response.content})
                        messages.append(
                            {
                                "role": "user",
                                "content": "Your finding payload was rejected. Correct it and call submit_findings again: "
                                + json.dumps(submission.get("errors") or [], ensure_ascii=False),
                            }
                        )
                        last_event_id = call_event_id
                        continue
                    messages.append({"role": "assistant", "content": response.content})
                    messages.append(
                        {
                            "role": "user",
                            "content": "If you have finished, call submit_findings with your JSON findings.",
                        }
                    )
                    last_event_id = call_event_id
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
        if self.sandbox._submitted is None and (
            stop_reason in {"completed", "max_steps"} or self.sandbox.invalid_submission_attempts > 0
        ):
            stop_reason = "model_format_failure"
        self.event_log.emit(
            "agent_finished",
            agent_id=self.agent_id,
            payload={"reason": stop_reason, "finding_count": len(findings.get("findings", []))},
        )
        return {
            "agent_id": self.agent_id,
            "stop_reason": stop_reason,
            "findings": findings,
            "submission_attempts": self.sandbox.submission_attempts,
            "invalid_submission_attempts": self.sandbox.invalid_submission_attempts,
        }

    def _complete_with_permit(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]], *, step: int, parent_event_id: str
    ) -> tuple[Any, dict[str, Any], str]:
        retry_of: str | None = None
        for retry_index in range(self.max_provider_retries + 1):
            requested = self.event_log.emit(
                "call_permit_requested",
                agent_id=self.agent_id,
                payload={"step": step, "retry_of": retry_of},
                parent_event_ids=[parent_event_id],
            )
            try:
                permit = self.budget.acquire_call_permit(self.agent_id, retry_of=retry_of)
            except BudgetExhausted as exc:
                self.event_log.emit(
                    "call_permit_denied",
                    agent_id=self.agent_id,
                    payload={"step": step, "retry_of": retry_of, "reason": exc.reason, "snapshot": exc.snapshot},
                    parent_event_ids=[requested["event_id"]],
                )
                raise
            granted = self.event_log.emit(
                "call_permit_granted",
                agent_id=self.agent_id,
                payload={**permit.as_dict(), "step": step, "budget": self.budget.snapshot()},
                parent_event_ids=[requested["event_id"]],
                budget_progress=self.budget.snapshot(),
            )
            request_transcript = self.transcript_log.request(
                agent_id=self.agent_id,
                step=step,
                permit_id=permit.permit_id,
                messages=messages,
                tools=tools,
                parent_event_ids=[granted["event_id"]],
            )
            started_at = time.monotonic()
            attempted = self.event_log.emit(
                "llm_call_attempted",
                agent_id=self.agent_id,
                payload={**permit.as_dict(), "step": step},
                parent_event_ids=[granted["event_id"]],
                artifact_refs=[request_transcript["transcript_id"]],
            )
            try:
                response = self.llm.complete(messages, tools, agent_id=self.agent_id)
            except Exception as exc:
                outcome = _provider_outcome(exc)
                self.budget.settle_call_permit(permit, outcome=outcome)
                self.event_log.emit(
                    "llm_call",
                    agent_id=self.agent_id,
                    payload={
                        **permit.as_dict(),
                        "step": step,
                        "outcome": outcome,
                        "duration_seconds": time.monotonic() - started_at,
                        "error_type": type(exc).__name__,
                    },
                    parent_event_ids=[attempted["event_id"]],
                    outcome=outcome,
                    budget_progress=self.budget.snapshot(),
                    artifact_refs=[request_transcript["transcript_id"]],
                )
                if retry_index >= self.max_provider_retries:
                    raise
                retry_of = permit.permit_id
                self.event_log.emit(
                    "llm_retry_scheduled",
                    agent_id=self.agent_id,
                    payload={"step": step, "retry_of": retry_of, "next_retry_index": retry_index + 1},
                    parent_event_ids=[attempted["event_id"]],
                )
                continue
            self.budget.settle_call_permit(permit, outcome="succeeded", usage=response.usage)
            response_transcript = self.transcript_log.response(
                agent_id=self.agent_id,
                step=step,
                permit_id=permit.permit_id,
                content=response.content,
                tool_calls=response.tool_calls,
                model_metadata=response.model_metadata,
                parent_refs=[request_transcript["transcript_id"]],
            )
            completed = self.event_log.emit(
                "llm_call",
                agent_id=self.agent_id,
                payload={
                    **permit.as_dict(),
                    "step": step,
                    "outcome": "succeeded",
                    "model": response.usage.model,
                    "model_metadata": response.model_metadata,
                    "tool_calls": len(response.tool_calls),
                    "duration_seconds": time.monotonic() - started_at,
                },
                token_usage=response.usage.as_dict(),
                parent_event_ids=[attempted["event_id"]],
                outcome="succeeded",
                budget_progress=self.budget.snapshot(),
                artifact_refs=[request_transcript["transcript_id"], response_transcript["transcript_id"]],
            )
            return response, response_transcript, completed["event_id"]
        raise RuntimeError("provider retry loop exited unexpectedly")

    def _dispatch(self, name: str, raw_arguments: str, *, parent_event_id: str) -> str:
        try:
            args = json.loads(raw_arguments) if raw_arguments else {}
        except json.JSONDecodeError:
            args = {}
        dispatched = self.event_log.emit(
            "tool_call",
            agent_id=self.agent_id,
            payload={"tool": name, "arguments": args},
            parent_event_ids=[parent_event_id],
        )
        try:
            with self.event_log.parent_context(dispatched["event_id"]):
                result = self._call(name, args)
            return json.dumps(result, ensure_ascii=False, default=str)
        except ToolError as exc:
            return json.dumps({"error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": str(exc), "type": type(exc).__name__})

    def _call(self, name: str, args: dict[str, Any]) -> Any:
        if name not in self._allowed_tools:
            raise ToolError(f"tool is not authorized for coordination condition {self.mode}: {name}")
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
            "complete_task": lambda: self.sandbox.complete_task(
                args["task_id"], args.get("result"), args.get("evidence_refs")
            ),
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


def _provider_outcome(exc: Exception) -> str:
    """Classify failure without importing provider-specific exception classes."""
    name = type(exc).__name__.lower()
    return "timeout" if "timeout" in name or isinstance(exc, TimeoutError) else "provider_error"
