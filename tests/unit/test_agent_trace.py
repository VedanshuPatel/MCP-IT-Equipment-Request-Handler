"""Unit tests for the ReAct trace: console text and JSON."""

import json

import pytest

from it_equipment.agent.decision import Decision
from it_equipment.agent.llm import ToolCall
from it_equipment.agent.mcp_client import Observation
from it_equipment.agent.trace import AgentResult, Step, format_result, format_step

REQUEST = "Hi, this is E002. My laptop is slow. Can I get a new one?"


@pytest.fixture
def ok_step() -> Step:
    """A successful eligibility check for E002's laptop."""
    arguments = {"employee_id": "E002", "item": "laptop"}
    return Step(
        number=1,
        call=ToolCall("check_request_eligibility", "Check the laptop against policy.", arguments),
        observation=Observation(
            "check_request_eligibility",
            arguments,
            ok=True,
            data={"status": "eligible", "reason_code": "REFRESH_DUE"},
            text='{"status": "eligible", "reason_code": "REFRESH_DUE"}',
        ),
    )


@pytest.fixture
def error_step() -> Step:
    """A lookup of an unknown employee, which the server rejects."""
    arguments = {"employee_id": "E999"}
    return Step(
        number=2,
        call=ToolCall("get_employee_info", "Look up the employee.", arguments),
        observation=Observation(
            "get_employee_info",
            arguments,
            ok=False,
            data=None,
            text="Error executing tool get_employee_info: EMPLOYEE_NOT_FOUND: no employee E999",
        ),
    )


@pytest.fixture
def approval() -> Decision:
    """An approval of E002's laptop."""
    return Decision(
        employee_id="E002",
        item="laptop",
        decision="approve",
        reason_code="REFRESH_DUE",
        response="Your laptop replacement is approved.",
        ticket_id=None,
    )


def test_step_shows_thought_action_and_observation(ok_step):
    assert format_step(ok_step) == (
        "Step 1\n"
        "  Thought: Check the laptop against policy.\n"
        '  Action: check_request_eligibility({"employee_id": "E002", "item": "laptop"})\n'
        '  Observation: {"status": "eligible", "reason_code": "REFRESH_DUE"}'
    )


def test_failed_step_shows_the_error_text(error_step):
    assert format_step(error_step).endswith(
        "  Observation (error): Error executing tool get_employee_info: "
        "EMPLOYEE_NOT_FOUND: no employee E999"
    )


def test_result_shows_the_final_thought_and_decision(ok_step, approval):
    result = AgentResult(REQUEST, (ok_step,), "decided", approval, "Eligible, so I approve.")

    assert format_result(result) == (
        "Final\n"
        "  Thought: Eligible, so I approve.\n"
        "  Decision: approve (REFRESH_DUE)\n"
        "  Employee: E002, item: laptop\n"
        "  Response: Your laptop replacement is approved."
    )


def test_escalation_shows_its_ticket(ok_step, approval):
    escalation = approval.model_copy(
        update={"decision": "escalate", "reason_code": "EXCEPTION_REQUESTED", "ticket_id": "ESC-1"}
    )
    result = AgentResult(REQUEST, (ok_step,), "decided", escalation, "Damaged, so escalate.")

    assert "  Ticket: ESC-1\n" in format_result(result)


def test_run_without_a_decision_says_why(ok_step, error_step):
    result = AgentResult(REQUEST, (ok_step, error_step), "step_limit")

    assert format_result(result) == "No decision: the run stopped (step_limit) after 2 steps."


def test_trace_is_saved_as_json(ok_step, error_step, approval):
    result = AgentResult(REQUEST, (ok_step, error_step), "decided", approval, "Approve.")

    saved = json.loads(json.dumps(result.to_dict()))

    assert saved["request"] == REQUEST
    assert saved["stop"] == "decided"
    assert saved["decision"]["reason_code"] == "REFRESH_DUE"
    assert saved["decision_thought"] == "Approve."
    assert saved["steps"][0] == {
        "number": 1,
        "thought": "Check the laptop against policy.",
        "action": "check_request_eligibility",
        "arguments": {"employee_id": "E002", "item": "laptop"},
        "ok": True,
        "observation": {"status": "eligible", "reason_code": "REFRESH_DUE"},
    }
    assert saved["steps"][1]["ok"] is False
    assert "EMPLOYEE_NOT_FOUND" in saved["steps"][1]["observation"]


def test_trace_without_a_decision_saves_null(ok_step):
    saved = AgentResult(REQUEST, (ok_step,), "step_limit").to_dict()

    assert saved["decision"] is None
