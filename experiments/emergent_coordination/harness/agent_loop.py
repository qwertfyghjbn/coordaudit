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
        role: str | None = None,
        sandbox: AgentSandbox,
        llm: LLMClient,
        event_log: EventLog,
        transcript_log: TranscriptLog,
        budget: BudgetTracker,
        prompt_profile: str = "repository_pilot_v0",
        finding_schema: str = "repository_pilot_v0",
        max_steps: int = 12,
        max_provider_retries: int = 0,
    ):
        self.agent_id = agent_id
        self.mode = mode
        self.agent_count = agent_count
        self.role = role
        self.sandbox = sandbox
        self.llm = llm
        self.event_log = event_log
        self.transcript_log = transcript_log
        self.budget = budget
        self.prompt_profile = prompt_profile
        self.finding_schema = finding_schema
        self.max_steps = max_steps
        self.max_provider_retries = max_provider_retries
        self._allowed_tools = frozenset(item["function"]["name"] for item in tools_for_mode(mode, finding_schema, role))
        self._started = False
        self._finished = False
        self._step = 0
        self._last_event_id: str | None = None
        self._messages: list[dict[str, Any]] = []
        self._tools = tools_for_mode(mode, finding_schema, role)
        self._stop_reason = "completed"

    def run(self) -> dict[str, Any]:
        while not self._finished:
            self.advance()
        return self.result()

    def advance(self) -> dict[str, Any]:
        """Execute at most one model call while preserving model-visible context.

        Policies that need lifecycle-aware scheduling use this method; the
        legacy runner path simply calls it until terminal state.
        """
        if self._finished:
            return self.result()
        if not self._started:
            started = self.event_log.emit("agent_started", agent_id=self.agent_id, payload={"mode": self.mode, "role": self.role})
            self._last_event_id = started["event_id"]
            self._messages = [
                {"role": "system", "content": system_prompt(self.mode, self.agent_id, self.prompt_profile, self.role)},
                {"role": "user", "content": user_prompt(self.mode, self.agent_id, self.agent_count, self.prompt_profile, self.role)},
            ]
            self._started = True
        if self._step >= self.max_steps:
            self._finish("max_steps")
            return self.result()
        try:
            response, response_transcript, call_event_id = self._complete_with_permit(
                self._messages, self._tools, step=self._step + 1, parent_event_id=self._last_event_id or ""
            )
            self._step += 1
            if response.tool_calls:
                self._messages.append(
                    {
                        "role": "assistant",
                        "content": response.content or "",
                        "tool_calls": [
                            {"id": call["id"], "type": "function", "function": {"name": call["name"], "arguments": call["arguments"]}}
                            for call in response.tool_calls
                        ],
                    }
                )
                for call in response.tool_calls:
                    result = self._dispatch(call["name"], call.get("arguments") or "{}", parent_event_id=call_event_id)
                    self._messages.append({"role": "tool", "tool_call_id": call["id"], "name": call["name"], "content": _truncate(result)})
                    self.transcript_log.tool_result(
                        agent_id=self.agent_id, tool_call_id=call["id"], name=call["name"], content=_truncate(result),
                        parent_refs=[response_transcript["transcript_id"]],
                    )
                    self._last_event_id = call_event_id
                if self.sandbox._submitted is not None:
                    self._finish("submitted")
            elif response.content:
                maybe = _extract_findings(response.content)
                if maybe is not None:
                    submission = self.sandbox.submit_findings(maybe)
                    if submission.get("ok"):
                        self._finish("submitted")
                    else:
                        self._messages.append({"role": "assistant", "content": response.content})
                        self._messages.append({"role": "user", "content": "Your finding payload was rejected. Correct it and call submit_findings again: " + json.dumps(submission.get("errors") or [], ensure_ascii=False)})
                        self._last_event_id = call_event_id
                else:
                    self._messages.append({"role": "assistant", "content": response.content})
                    self._messages.append({"role": "user", "content": "If you have finished, call submit_findings with your JSON findings."})
                    self._last_event_id = call_event_id
        except BudgetExhausted as exc:
            self.event_log.emit(
                "budget_exhausted",
                agent_id=self.agent_id,
                payload={"reason": exc.reason, "snapshot": exc.snapshot},
            )
            self._finish("budget_exhausted")
        except Exception as exc:  # noqa: BLE001 - run must record unexpected failures
            self.event_log.emit(
                "error",
                agent_id=self.agent_id,
                payload={"error": str(exc), "type": type(exc).__name__},
            )
            self._finish("error")
        if not self._finished and self._step >= self.max_steps:
            self._finish("max_steps")
        return self.result()

    def stop_waiting(self, reason: str = "waiting_for_assignment") -> dict[str, Any]:
        """Finish an idle worker without inventing a model-format failure."""
        if not self._started:
            started = self.event_log.emit("agent_started", agent_id=self.agent_id, payload={"mode": self.mode, "role": self.role})
            self._last_event_id = started["event_id"]
            self._started = True
        if not self._finished:
            self._finish(reason)
        return self.result()

    def _finish(self, stop_reason: str) -> None:
        if self._finished:
            return
        findings = self.sandbox._submitted or {"findings": []}
        if self.sandbox._submitted is None and (stop_reason in {"completed", "max_steps"} or self.sandbox.invalid_submission_attempts > 0):
            stop_reason = "model_format_failure"
        self._stop_reason = stop_reason
        self._finished = True
        self.event_log.emit("agent_finished", agent_id=self.agent_id, payload={"reason": stop_reason, "finding_count": len(findings.get("findings", []))})

    def result(self) -> dict[str, Any]:
        findings = self.sandbox._submitted or {"findings": []}
        return {
            "agent_id": self.agent_id,
            "stop_reason": self._stop_reason,
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
        except json.JSONDecodeError as exc:
            return self._reject_tool_arguments(
                name,
                parent_event_id=parent_event_id,
                reason="invalid_json",
                details={"line": exc.lineno, "column": exc.colno},
            )
        if not isinstance(args, dict):
            return self._reject_tool_arguments(
                name,
                parent_event_id=parent_event_id,
                reason="arguments_not_object",
                details={"received_type": type(args).__name__},
            )
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

    def _reject_tool_arguments(
        self,
        name: str,
        *,
        parent_event_id: str,
        reason: str,
        details: dict[str, Any],
    ) -> str:
        error = {
            "code": "invalid_tool_arguments",
            "tool": name,
            "message": "Tool arguments must be a valid JSON object. Correct the arguments and retry.",
            "reason": reason,
            **details,
        }
        self.event_log.emit(
            "tool_call",
            agent_id=self.agent_id,
            payload={"tool": name, "argument_error": error},
            parent_event_ids=[parent_event_id],
            outcome="rejected",
        )
        return json.dumps({"ok": False, "error": error}, ensure_ascii=False)

    def _call(self, name: str, args: dict[str, Any]) -> Any:
        if name not in self._allowed_tools:
            raise ToolError(f"tool is not authorized for coordination condition {self.mode}: {name}")
        mapping = {
            "list_files": lambda: self.sandbox.list_files(args.get("path", "target")),
            "read_file": lambda: self.sandbox.read_file(args["path"]),
            "write_file": lambda: self.sandbox.write_file(args["path"], args.get("content", "")),
            "run_shell": lambda: self.sandbox.run_shell(args["command"], int(args.get("timeout", 30))),
            "submit_findings": lambda: self.sandbox.submit_findings(
                args if self.finding_schema == "repository_v1" else args.get("findings", [])
            ),
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
            "manager_create_task": lambda: self.sandbox.manager_create_task(args["worker_id"], args["description"]),
            "manager_list_tasks": lambda: self.sandbox.manager_list_tasks(),
            "manager_cancel_task": lambda: self.sandbox.manager_cancel_task(args["task_id"], args["reason"]),
            "manager_reassign_task": lambda: self.sandbox.manager_reassign_task(args["task_id"], args["worker_id"]),
            "worker_get_assignment": lambda: self.sandbox.worker_get_assignment(),
            "worker_report_task": lambda: self.sandbox.worker_report_task(
                args["task_id"], args["result"], args["evidence_refs"]
            ),
            "worker_request_more": lambda: self.sandbox.worker_request_more(),
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
