from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from experiments.emergent_coordination.harness.budget import TokenUsage
from experiments.emergent_coordination.harness.events import EventLog
from experiments.emergent_coordination.harness.llm.client import LLMResponse, MockLLMClient
from experiments.emergent_coordination.harness.manager_board import ManagerBoard
from experiments.emergent_coordination.harness.paths import TARGET_ROOT
from experiments.emergent_coordination.harness.runner import RunConfig, run_experiment
from experiments.emergent_coordination.harness.tools.sandbox import AgentSandbox, ToolError
from experiments.emergent_coordination.harness.tools.specs import tools_for_mode
from experiments.emergent_coordination.harness.workspace import prepare_run_workspace


def _tool_call(name: str, arguments: dict, call_id: str) -> dict[str, str]:
    return {"id": call_id, "name": name, "arguments": json.dumps(arguments)}


def _response(*calls: dict[str, str]) -> LLMResponse:
    return LLMResponse(
        content=None,
        tool_calls=list(calls),
        usage=TokenUsage(input_tokens=2, output_tokens=2, model="mock"),
        raw={"mock": True},
    )


def _valid_finding(evidence_ref: str) -> dict[str, object]:
    return {
        "title": "Potential debug disclosure",
        "category": "information_disclosure",
        "severity": "low",
        "source": {"file": "app/main.py", "function": "create_app", "anchor": "request.args"},
        "sink": {"file": "app/main.py", "function": "create_app", "anchor": "return response"},
        "reasoning_summary": "The reported code path exposes a response to a request.",
        "evidence_refs": [evidence_ref],
        "reproduction": {"attempted": False, "successful": False, "artifact_ref": None},
        "confidence": 0.4,
    }


class ManagerWorkerHarnessTest(unittest.TestCase):
    def test_m4_mock_runs_one_manager_and_n_minus_one_workers_on_one_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            llm = MockLLMClient(
                scripts={
                    "agent_001": [
                        _response(_tool_call("manager_create_task", {"worker_id": "agent_002", "description": "review routes"}, "m1")),
                        _response(_tool_call("manager_create_task", {"worker_id": "agent_003", "description": "review helpers"}, "m2")),
                        _response(_tool_call("manager_list_tasks", {}, "m3")),
                        _response(_tool_call("submit_findings", {"findings": []}, "m4")),
                    ],
                    "agent_002": [
                        _response(_tool_call("worker_get_assignment", {}, "w21")),
                        _response(_tool_call("worker_report_task", {"task_id": "manager_task_0001", "result": "route reviewed", "evidence_refs": []}, "w22")),
                    ],
                    "agent_003": [
                        _response(_tool_call("worker_get_assignment", {}, "w31")),
                        _response(_tool_call("worker_report_task", {"task_id": "manager_task_0002", "result": "helper reviewed", "evidence_refs": []}, "w32")),
                    ],
                }
            )
            summary = run_experiment(
                RunConfig(
                    mode="manager_worker", agent_count=4, model="mock", max_steps=4,
                    budgets={"hard_team_call_permits": 8}, runs_dir=Path(tmp),
                ),
                llm,
            )

            events = [
                json.loads(line)
                for line in (Path(summary["run_dir"]) / "logs" / "events.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(summary["agent_results"][0]["agent_id"], "agent_001")
            self.assertEqual(summary["agent_results"][0]["stop_reason"], "submitted")
            self.assertEqual(summary["agent_results"][-1]["stop_reason"], "waiting_for_assignment")
            self.assertEqual(summary["budget"]["attempted_llm_calls"], 8)
            self.assertLessEqual(summary["budget"]["attempted_llm_calls"], 8)
            self.assertEqual(
                {entry["agent_id"] for entry in summary["budget"]["permit_ledger"]},
                {"agent_001", "agent_002", "agent_003"},
            )
            self.assertEqual(
                [event["event_type"] for event in events if event["event_type"] == "manager_task_created"],
                ["manager_task_created", "manager_task_created"],
            )
            self.assertEqual(len([event for event in events if event["event_type"] == "manager_worker_reported"]), 2)

    def test_manager_can_submit_only_worker_evidence_it_explicitly_observed(self):
        with tempfile.TemporaryDirectory() as tmp:
            layout = prepare_run_workspace(Path(tmp) / "run", TARGET_ROOT, agent_count=2)
            log = EventLog(layout.logs / "events.jsonl", run_id="manager-evidence")
            board = ManagerBoard(log, "agent_001", ["agent_002"])
            manager = AgentSandbox("agent_001", layout, log, manager_board=board)
            worker = AgentSandbox("agent_002", layout, log, manager_board=board)

            task = manager.manager_create_task("agent_002", "inspect the request handler")
            evidence_ref = worker.read_file("target/app/main.py")["evidence_ref"]
            worker.worker_report_task(task["id"], "handler reviewed", [evidence_ref])

            rejected = manager.submit_findings([_valid_finding(evidence_ref)])
            self.assertFalse(rejected["ok"])
            self.assertFalse(any(event["event_type"] == "finding_submitted" for event in log.read_all()))

            manager.manager_list_tasks()
            accepted = manager.submit_findings([_valid_finding(evidence_ref)])
            self.assertTrue(accepted["ok"])
            observed = [event for event in log.read_all() if event["event_type"] == "manager_report_observed"]
            self.assertEqual(observed[0]["payload"]["evidence_refs"], [evidence_ref])

    def test_manager_worker_run_stops_cleanly_when_team_permits_run_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            llm = MockLLMClient(
                scripts={
                    "agent_001": [_response(_tool_call("manager_create_task", {"worker_id": "agent_002", "description": "review"}, "m1"))],
                    "agent_002": [_response(_tool_call("worker_get_assignment", {}, "w21"))],
                }
            )
            summary = run_experiment(
                RunConfig(
                    mode="manager_worker", agent_count=2, model="mock", max_steps=6,
                    budgets={"hard_team_call_permits": 2}, runs_dir=Path(tmp),
                ),
                llm,
            )

            self.assertEqual(summary["budget"]["attempted_llm_calls"], 2)
            stop_reasons = {entry["agent_id"]: entry["stop_reason"] for entry in summary["agent_results"]}
            self.assertEqual(stop_reasons, {"agent_001": "budget_exhausted", "agent_002": "budget_exhausted"})
            events = [
                json.loads(line)
                for line in (Path(summary["run_dir"]) / "logs" / "events.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            exhausted = [event for event in events if event["event_type"] == "budget_exhausted"]
            self.assertEqual({entry["payload"]["reason"] for entry in exhausted}, {"hard_team_call_permits"})
            self.assertEqual(len(exhausted), 2)
            self.assertFalse(any(event["event_type"] == "error" for event in events))

    def test_manager_and_worker_tool_surfaces_and_board_calls_are_role_isolated(self):
        manager_tools = {item["function"]["name"] for item in tools_for_mode("manager_worker", role="manager")}
        worker_tools = {item["function"]["name"] for item in tools_for_mode("manager_worker", role="worker")}
        self.assertIn("manager_create_task", manager_tools)
        self.assertNotIn("worker_get_assignment", manager_tools)
        self.assertIn("worker_get_assignment", worker_tools)
        self.assertNotIn("manager_create_task", worker_tools)
        self.assertFalse(manager_tools & {"shared_create", "claim_task", "send_message", "list_messages"})
        self.assertFalse(worker_tools & {"shared_create", "claim_task", "send_message", "list_messages"})

        with tempfile.TemporaryDirectory() as tmp:
            layout = prepare_run_workspace(Path(tmp) / "run", TARGET_ROOT, agent_count=2)
            log = EventLog(layout.logs / "events.jsonl", run_id="manager-roles")
            board = ManagerBoard(log, "agent_001", ["agent_002"])
            manager = AgentSandbox("agent_001", layout, log, manager_board=board)
            worker = AgentSandbox("agent_002", layout, log, manager_board=board)
            with self.assertRaises(ToolError):
                worker.manager_create_task("agent_002", "forbidden")
            with self.assertRaises(ToolError):
                manager.worker_get_assignment()


if __name__ == "__main__":
    unittest.main()
