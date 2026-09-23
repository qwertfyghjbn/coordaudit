"""Hard dispatch-level finalization gate (completion generation 2).

Generation-2 policies (``convergent_v2``/``scheduler_only_v2``) must make
finalization a runtime property of dispatch authorization, not an
advertisement hint: while the gate is active only ``submit_findings`` may
execute, regardless of how the tool call is constructed.  Generation-1
policies keep their frozen advisory semantics.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from experiments.emergent_coordination.harness.llm.client import LLMResponse, MockLLMClient
from experiments.emergent_coordination.harness.budget import TokenUsage
from experiments.emergent_coordination.harness.runner import RunConfig, run_experiment


def _tool_call(name: str, arguments, call_id: str = "c1") -> dict:
    return {"id": call_id, "name": name, "arguments": arguments if isinstance(arguments, str) else json.dumps(arguments)}


def _response(*calls: dict, content: str | None = None) -> LLMResponse:
    return LLMResponse(
        content=content,
        tool_calls=list(calls),
        usage=TokenUsage(input_tokens=1, output_tokens=1, model="mock"),
        raw={"mock": True},
    )


def _load_events(run_dir: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in (Path(run_dir) / "logs" / "events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _load_transcripts(run_dir: Path, agent_id: str = "agent_001") -> list[dict]:
    return [
        json.loads(line)
        for line in (Path(run_dir) / "logs" / "transcripts" / f"{agent_id}.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _requests(transcripts: list[dict]) -> dict[int, dict]:
    return {
        record["content"]["step"]: record["content"]
        for record in transcripts
        if record.get("kind") == "model_request"
    }


# max_steps=12 with the fixed reserve of 8 makes step 5 the first
# finalization step; steps 1-4 keep the full tool surface.
STEPS_BEFORE_FINALIZATION = 4


class HardFinalizationGateTest(unittest.TestCase):
    def _run(self, llm, *, completion_policy, mode="single", agent_count=1, max_steps=12):
        with tempfile.TemporaryDirectory() as tmp:
            summary = run_experiment(
                RunConfig(
                    mode=mode,
                    agent_count=agent_count,
                    model="mock",
                    budgets={"hard_team_call_permits": 40},
                    runs_dir=Path(tmp),
                    max_steps=max_steps,
                    completion_policy=completion_policy,
                ),
                llm,
            )
            summary["_events"] = _load_events(Path(summary["run_dir"]))
            summary["_transcripts"] = _load_transcripts(Path(summary["run_dir"]))
            summary["_metrics"] = json.loads((Path(summary["run_dir"]) / "metrics.json").read_text(encoding="utf-8"))
        return summary

    def test_read_file_dispatch_rejected_once_finalization_starts(self):
        llm = MockLLMClient(
            scripts={
                "agent_001": [
                    _response(_tool_call("read_file", {"path": "target/README.md"}, f"c{step}"))
                    for step in range(1, STEPS_BEFORE_FINALIZATION + 1)
                ]
                + [
                    _response(_tool_call("read_file", {"path": "target/app/routes/files.py"}, "c5")),
                    _response(_tool_call("submit_findings", {"findings": []}, "c6")),
                ]
            }
        )
        summary = self._run(llm, completion_policy="scheduler_only_v2")
        events = summary["_events"]

        # Before finalization the reads execute normally.
        file_reads = [event for event in events if event["event_type"] == "file_read"]
        self.assertEqual(len(file_reads), STEPS_BEFORE_FINALIZATION)

        # Step 5 is inside finalization: the dispatch-level gate rejects.
        prohibited = [event for event in events if event["event_type"] == "prohibited_tool_attempt"]
        self.assertEqual(len(prohibited), 1)
        payload = prohibited[0]["payload"]
        self.assertEqual(payload["requested_tool"], "read_file")
        self.assertEqual(payload["rejected_by"], "hard_finalization_gate")
        self.assertTrue(payload["finalization_active"])
        self.assertEqual(payload["step"], 5)
        self.assertEqual(payload["call_id"], "c5")
        self.assertEqual(len(payload["arguments_sha256"]), 64)
        self.assertNotIn("arguments", payload)
        self.assertEqual(prohibited[0]["outcome"], "rejected")
        self.assertEqual(len(file_reads), STEPS_BEFORE_FINALIZATION)  # nothing extra executed

        tool_messages = [
            record["content"]
            for record in summary["_transcripts"]
            if record.get("kind") == "tool_result" and record["content"]["tool_call_id"] == "c5"
        ]
        rejection = json.loads(tool_messages[0]["content"])
        self.assertEqual(rejection["error"]["code"], "prohibited_tool_during_finalization")
        self.assertEqual(rejection["error"]["rejected_by"], "hard_finalization_gate")
        self.assertEqual(rejection["error"]["tool"], "read_file")

        # The agent can still submit afterwards.
        self.assertEqual(summary["agent_results"][0]["stop_reason"], "submitted")
        self.assertEqual(summary["agent_results"][0]["submission_attempts"], 1)

    def test_advertised_surface_contains_only_submit_findings_during_finalization(self):
        llm = MockLLMClient(
            scripts={
                "agent_001": [
                    _response(_tool_call("read_file", {"path": "target/README.md"}, "c1")),
                    _response(_tool_call("read_file", {"path": "target/README.md"}, "c2")),
                    _response(_tool_call("read_file", {"path": "target/README.md"}, "c3")),
                    _response(_tool_call("read_file", {"path": "target/README.md"}, "c4")),
                    _response(_tool_call("read_file", {"path": "target/README.md"}, "c5")),
                    _response(_tool_call("submit_findings", {"findings": []}, "c6")),
                ]
            }
        )
        summary = self._run(llm, completion_policy="convergent_v2")
        requests = _requests(summary["_transcripts"])
        self.assertIn("read_file", [tool["function"]["name"] for tool in requests[4]["tools"]])
        self.assertEqual([tool["function"]["name"] for tool in requests[5]["tools"]], ["submit_findings"])
        self.assertEqual([tool["function"]["name"] for tool in requests[6]["tools"]], ["submit_findings"])
        self.assertIn("Finalization phase", requests[5]["messages"][-1]["content"])

    def test_sequenced_bootstrap_preserves_complete_task_in_finalization_surface(self):
        llm = MockLLMClient(
            scripts={
                "agent_001": [
                    _response(_tool_call("read_file", {"path": "target/README.md"}, f"c{step}"))
                    for step in range(1, 5)
                ]
                + [_response(_tool_call("submit_findings", {"findings": []}, "c5"))]
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            summary = run_experiment(
                RunConfig(
                    mode="structured_team",
                    agent_count=1,
                    model="mock",
                    budgets={
                        "hard_team_call_permits": 12,
                        "max_provider_retries": 0,
                        "team_finalization_policy": "team_remaining_permits_v1",
                        "team_finalization_reserve": 7,
                    },
                    runs_dir=Path(tmp),
                    max_steps=12,
                    completion_policy="convergent_v2",
                    team_completion_policy="all_agents_terminal_v1",
                    team_finalization_policy="team_remaining_permits_v1",
                    team_finalization_reserve=7,
                    prompt_profile="repository_v1_t4_sequenced_bootstrap_v1",
                ),
                llm,
            )
            transcripts = _load_transcripts(Path(summary["run_dir"]))
        requests = _requests(transcripts)
        self.assertIn("complete_task", [tool["function"]["name"] for tool in requests[5]["tools"]])

    def test_shell_search_and_coordination_tools_are_all_rejected(self):
        llm = MockLLMClient(
            scripts={
                "agent_001": [
                    _response(_tool_call("create_task", {"description": "check routes"}, "c1")),
                    _response(_tool_call("read_file", {"path": "target/README.md"}, "c2")),
                    _response(_tool_call("list_files", {"path": "target"}, "c3")),
                    _response(_tool_call("read_file", {"path": "target/README.md"}, "c4")),
                    _response(
                        _tool_call("run_shell", {"command": "grep -r secret target/"}, "c5a"),
                        _tool_call("list_files", {"path": "target/app"}, "c5b"),
                        _tool_call("list_tasks", {}, "c5c"),
                    ),
                    _response(_tool_call("submit_findings", {"findings": []}, "c6")),
                ]
            }
        )
        summary = self._run(llm, completion_policy="convergent_v2", mode="structured_team")
        events = summary["_events"]

        prohibited = [event for event in events if event["event_type"] == "prohibited_tool_attempt"]
        self.assertEqual([event["payload"]["requested_tool"] for event in prohibited], ["run_shell", "list_files", "list_tasks"])
        # Task lifecycle events only exist from the pre-finalization call.
        self.assertEqual(len([event for event in events if event["event_type"] == "task_created"]), 1)
        shell_dispatches = [
            event
            for event in events
            if event["event_type"] == "tool_call"
            and (event.get("payload") or {}).get("tool") == "run_shell"
            and "arguments" in (event.get("payload") or {})
        ]
        self.assertEqual(len(shell_dispatches), 0)
        self.assertEqual(summary["agent_results"][0]["stop_reason"], "submitted")

    def test_malformed_arguments_cannot_bypass_the_gate(self):
        llm = MockLLMClient(
            scripts={
                "agent_001": [
                    _response(_tool_call("read_file", {"path": "target/README.md"}, f"c{step}"))
                    for step in range(1, STEPS_BEFORE_FINALIZATION + 1)
                ]
                + [
                    _response(_tool_call("read_file", '{"path": "target/unclosed', "c5")),
                    _response(_tool_call("submit_findings", {"findings": []}, "c6")),
                ]
            }
        )
        summary = self._run(llm, completion_policy="scheduler_only_v2")
        prohibited = [event for event in summary["_events"] if event["event_type"] == "prohibited_tool_attempt"]
        argument_errors = [
            event
            for event in summary["_events"]
            if event["event_type"] == "tool_call" and "argument_error" in (event.get("payload") or {})
        ]
        self.assertEqual(len(prohibited), 1)
        self.assertEqual(prohibited[0]["payload"]["requested_tool"], "read_file")
        self.assertEqual(argument_errors, [])  # the gate runs before argument parsing
        self.assertEqual(summary["agent_results"][0]["stop_reason"], "submitted")

    def test_rejection_does_not_restore_the_tool_surface(self):
        llm = MockLLMClient(
            scripts={
                "agent_001": [
                    _response(_tool_call("read_file", {"path": "target/README.md"}, f"c{step}"))
                    for step in range(1, STEPS_BEFORE_FINALIZATION + 1)
                ]
                + [
                    _response(_tool_call("read_file", {"path": "target/README.md"}, "c5")),
                    _response(_tool_call("run_shell", {"command": "ls target"}, "c6")),
                    _response(_tool_call("submit_findings", {"findings": []}, "c7")),
                ]
            }
        )
        summary = self._run(llm, completion_policy="scheduler_only_v2")
        prohibited = [event for event in summary["_events"] if event["event_type"] == "prohibited_tool_attempt"]
        self.assertEqual([event["payload"]["requested_tool"] for event in prohibited], ["read_file", "run_shell"])
        requests = _requests(summary["_transcripts"])
        self.assertEqual([tool["function"]["name"] for tool in requests[6]["tools"]], ["submit_findings"])
        self.assertEqual(summary["agent_results"][0]["stop_reason"], "submitted")

    def test_gate_inactive_for_none_and_guidance_only(self):
        for policy in (None, "guidance_only"):
            with self.subTest(policy=policy):
                llm = MockLLMClient(
                    scripts={
                        "agent_001": [
                            _response(_tool_call("read_file", {"path": "target/README.md"}, f"c{step}"))
                            for step in range(1, STEPS_BEFORE_FINALIZATION + 1)
                        ]
                        + [
                            _response(_tool_call("read_file", {"path": "target/README.md"}, "c5")),
                            _response(_tool_call("submit_findings", {"findings": []}, "c6")),
                        ]
                    }
                )
                summary = self._run(llm, completion_policy=policy)
                self.assertEqual(
                    len([event for event in summary["_events"] if event["event_type"] == "file_read"]),
                    STEPS_BEFORE_FINALIZATION + 1,
                )
                self.assertEqual([event for event in summary["_events"] if event["event_type"] == "prohibited_tool_attempt"], [])
                self.assertEqual(
                    [event for event in summary["_events"] if event["event_type"] == "completion_phase_started"],
                    [],
                )
                requests = _requests(summary["_transcripts"])
                self.assertIn("read_file", [tool["function"]["name"] for tool in requests[5]["tools"]])
                self.assertEqual(summary["agent_results"][0]["stop_reason"], "submitted")

    def test_generation_one_policies_keep_their_bypassable_semantics(self):
        """convergent_v1/scheduler_only stay advisory at dispatch, as frozen."""
        for policy in ("convergent_v1", "scheduler_only"):
            with self.subTest(policy=policy):
                llm = MockLLMClient(
                    scripts={
                        "agent_001": [
                            _response(_tool_call("read_file", {"path": "target/README.md"}, f"c{step}"))
                            for step in range(1, STEPS_BEFORE_FINALIZATION + 1)
                        ]
                        + [
                            _response(_tool_call("read_file", {"path": "target/README.md"}, "c5")),
                            _response(_tool_call("submit_findings", {"findings": []}, "c6")),
                        ]
                    }
                )
                summary = self._run(llm, completion_policy=policy)
                # The read inside the finalization window still executes.
                self.assertEqual(
                    len([event for event in summary["_events"] if event["event_type"] == "file_read"]),
                    STEPS_BEFORE_FINALIZATION + 1,
                )
                self.assertEqual([event for event in summary["_events"] if event["event_type"] == "prohibited_tool_attempt"], [])
                self.assertEqual(summary["agent_results"][0]["stop_reason"], "submitted")

    def test_manager_worker_coordination_tools_are_gated(self):
        llm = MockLLMClient(
            scripts={
                "agent_001": [
                    _response(_tool_call("manager_create_task", {"worker_id": "agent_002", "description": "check files"}, "c1")),
                    _response(_tool_call("manager_list_tasks", {}, "c2")),
                    _response(_tool_call("read_file", {"path": "target/README.md"}, "c3")),
                    _response(_tool_call("read_file", {"path": "target/README.md"}, "c4")),
                    _response(_tool_call("manager_list_tasks", {}, "c5")),
                    _response(_tool_call("submit_findings", {"findings": []}, "c6")),
                ],
                "agent_002": [
                    _response(_tool_call("worker_get_assignment", {}, "w1")),
                    _response(_tool_call("read_file", {"path": "target/README.md"}, "w2")),
                    _response(_tool_call("read_file", {"path": "target/README.md"}, "w3")),
                    _response(_tool_call("worker_report_task", {"task_id": "t1", "result": "done", "evidence_refs": []}, "w4")),
                    _response(_tool_call("read_file", {"path": "target/README.md"}, "w5")),
                    _response(_tool_call("submit_findings", {"findings": []}, "w6")),
                ],
            }
        )
        summary = self._run(llm, completion_policy="convergent_v2", mode="manager_worker", agent_count=2, max_steps=12)
        events = summary["_events"]
        prohibited = [event for event in events if event["event_type"] == "prohibited_tool_attempt"]
        self.assertEqual(
            sorted((event["agent_id"], event["payload"]["requested_tool"]) for event in prohibited),
            [("agent_001", "manager_list_tasks"), ("agent_002", "read_file")],
        )
        self.assertEqual(
            sorted(result["stop_reason"] for result in summary["agent_results"]),
            ["submitted", "submitted"],
        )

    def test_completion_metrics_report_binding_candidates(self):
        llm = MockLLMClient(
            scripts={
                "agent_001": [
                    _response(_tool_call("read_file", {"path": "target/README.md"}, f"c{step}"))
                    for step in range(1, STEPS_BEFORE_FINALIZATION + 1)
                ]
                + [
                    _response(_tool_call("read_file", {"path": "target/README.md"}, "c5")),
                    _response(_tool_call("submit_findings", {"findings": []}, "c6")),
                ]
            }
        )
        summary = self._run(llm, completion_policy="scheduler_only_v2")
        completion = summary["_metrics"]["completion"]
        agent = completion["per_agent"]["agent_001"]
        self.assertEqual(completion["generation"], "hard_gate")
        self.assertEqual(agent["finalization_start_step"], 5)
        self.assertEqual(agent["prohibited_tool_attempts_after_finalization"], 1)
        self.assertEqual(agent["prohibited_tool_names"], ["read_file"])
        self.assertEqual(agent["had_submit_attempt_before_finalization"], False)
        self.assertEqual(agent["submit_attempts_after_finalization"], 1)
        self.assertTrue(agent["successful_submit_after_finalization"])
        self.assertEqual(agent["steps_from_finalization_to_submit"], 1)
        self.assertEqual(agent["hard_finalization_binding_candidate"], "binding_strong")

    def test_completion_metrics_report_non_binding_when_converged_before_finalization(self):
        llm = MockLLMClient(
            scripts={
                "agent_001": [
                    _response(_tool_call("read_file", {"path": "target/README.md"}, "c1")),
                    _response(_tool_call("read_file", {"path": "target/README.md"}, "c2")),
                    _response(_tool_call("read_file", {"path": "target/README.md"}, "c3")),
                    _response(
                        _tool_call("read_file", {"path": "target/README.md"}, "c4"),
                        content="I have enough evidence to consolidate my findings.",
                    ),
                    _response(_tool_call("submit_findings", {"findings": []}, "c5")),
                ]
            }
        )
        summary = self._run(llm, completion_policy="convergent_v2")
        agent = summary["_metrics"]["completion"]["per_agent"]["agent_001"]
        self.assertEqual(agent["first_convergence_candidate_step"], 4)
        self.assertTrue(agent["had_convergence_candidate_before_finalization"])
        self.assertTrue(agent["last_exploration_before_finalization"])
        self.assertEqual(agent["hard_finalization_binding_candidate"], "non_binding_strong")
        self.assertEqual(agent["exploration_calls_after_first_convergence"], 0)
        self.assertEqual(agent["successful_submit_step"], 5)
        self.assertEqual(agent["steps_from_finalization_to_submit"], 0)

    def test_negated_convergence_cues_are_not_candidates(self):
        llm = MockLLMClient(
            scripts={
                "agent_001": [
                    _response(_tool_call("read_file", {"path": "target/README.md"}, "c1"), content="I do not have enough evidence yet."),
                    _response(_tool_call("read_file", {"path": "target/README.md"}, "c2")),
                    _response(_tool_call("read_file", {"path": "target/README.md"}, "c3")),
                    _response(_tool_call("read_file", {"path": "target/README.md"}, "c4")),
                    _response(_tool_call("submit_findings", {"findings": []}, "c5")),
                ]
            }
        )
        summary = self._run(llm, completion_policy="scheduler_only_v2")
        agent = summary["_metrics"]["completion"]["per_agent"]["agent_001"]
        self.assertIsNone(agent["first_convergence_candidate_step"])


if __name__ == "__main__":
    unittest.main()
