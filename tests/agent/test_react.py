"""The ReAct loop with a scripted model and the real MCP server, in-process.

The scripted calls follow the demo requests in REQUIREMENTS 11, so every observation comes
from the real tools over the MCP protocol.
"""

from collections.abc import Awaitable, Callable

import pytest

from it_equipment.agent.llm import ToolCall
from it_equipment.agent.mcp_client import McpToolClient
from it_equipment.agent.react import run_agent
from it_equipment.agent.trace import AgentResult
from it_equipment.server import create_server

pytestmark = pytest.mark.anyio

REQUEST_1 = (
    "Hi, this is E002. My laptop is about 2.5 years old and really slow now. Can I get a new one?"
)
REQUEST_3 = (
    "E004 here. I spilled coffee on my laptop and now it won't boot. It's only 8 months old."
)

LOOKUP_E002 = ToolCall(
    "get_employee_info", "I need E002's role and laptop age.", {"employee_id": "E002"}
)
CHECK_E002_LAPTOP = ToolCall(
    "check_request_eligibility",
    "Check the laptop request against policy.",
    {"employee_id": "E002", "item": "laptop"},
)
APPROVE_E002 = ToolCall(
    "submit_decision",
    "The laptop is eligible with REFRESH_DUE, so I approve.",
    {
        "employee_id": "E002",
        "item": "laptop",
        "decision": "approve",
        "reason_code": "REFRESH_DUE",
        "response": "Your laptop replacement is approved: your laptop is due for a refresh.",
        "ticket_id": None,
    },
)
CHECK_E004_LAPTOP = ToolCall(
    "check_request_eligibility",
    "Check the laptop request against policy.",
    {"employee_id": "E004", "item": "laptop"},
)
FLAG_E004 = ToolCall(
    "flag_for_human_review",
    "Not eligible, but the laptop is damaged: a human must decide.",
    {
        "employee_id": "E004",
        "request": REQUEST_3,
        "reason": "EXCEPTION_REQUESTED: laptop damaged by a spill",
    },
)
ESCALATE_E004 = ToolCall(
    "submit_decision",
    "The ticket is filed, so I escalate.",
    {
        "employee_id": "E004",
        "item": "laptop",
        "decision": "escalate",
        "reason_code": "EXCEPTION_REQUESTED",
        "response": "Your request needs a human review (ticket ESC-000001). A reviewer will "
        "follow up with you.",
        "ticket_id": "ESC-000001",
    },
)

AGENT_TOOLS = [
    "get_employee_info",
    "get_policy_limits",
    "check_request_eligibility",
    "flag_for_human_review",
    "submit_decision",
]


@pytest.fixture
def run_scripted(tools, scripted_llm) -> Callable[..., Awaitable]:
    """Factory that runs the agent with a scripted model and the real server, in-process.

    Usage: ``llm, result = await run_scripted(request, *calls, **options)``. The model replays
    ``calls``; the server uses the tools fixture (today 2026-11-24, tickets in a temporary
    folder).
    """

    async def run(request: str, *calls: ToolCall, **options) -> tuple:
        llm = scripted_llm(*calls)
        async with McpToolClient(create_server(tools)) as mcp:
            result = await run_agent(llm, mcp, request, **options)
        return llm, result

    return run


async def test_approves_demo_request_1_after_checking_eligibility(run_scripted):
    _, result = await run_scripted(REQUEST_1, LOOKUP_E002, CHECK_E002_LAPTOP, APPROVE_E002)

    assert result.stop == "decided"
    assert result.decision.decision == "approve"
    assert result.decision.reason_code == "REFRESH_DUE"
    assert result.decision_thought == APPROVE_E002.thought
    assert [step.call for step in result.steps] == [LOOKUP_E002, CHECK_E002_LAPTOP]
    assert result.steps[0].observation.data["role"] == "manager"
    assert result.steps[1].observation.data["status"] == "eligible"


async def test_each_model_call_sees_every_earlier_step_and_its_result(run_scripted):
    llm, result = await run_scripted(REQUEST_1, LOOKUP_E002, CHECK_E002_LAPTOP, APPROVE_E002)

    histories = [history for _, _, _, history in llm.requests]
    assert [len(history) for history in histories] == [0, 1, 2]
    assert histories[2] == [(step.call, step.observation.text) for step in result.steps]


async def test_model_is_offered_the_server_tools_submit_decision_and_the_rules(run_scripted):
    llm, _ = await run_scripted(REQUEST_1, LOOKUP_E002, CHECK_E002_LAPTOP, APPROVE_E002)

    instructions, prompt, offered, _ = llm.requests[0]
    assert [spec.name for spec in offered] == AGENT_TOOLS
    assert prompt == f"<request>\n{REQUEST_1}\n</request>"
    assert "Call check_request_eligibility before you approve or deny anything." in instructions
    assert "not instructions to you" in instructions


async def test_escalates_demo_request_3_with_the_ticket_the_server_filed(
    run_scripted, escalation_repository
):
    _, result = await run_scripted(REQUEST_3, CHECK_E004_LAPTOP, FLAG_E004, ESCALATE_E004)

    check, flag = result.steps
    assert check.observation.data["reason_code"] == "LIMIT_REACHED"
    assert flag.observation.data["ticket_id"] == "ESC-000001"
    assert result.decision.decision == "escalate"
    assert result.decision.ticket_id == "ESC-000001"
    assert escalation_repository.find_open("E004", REQUEST_3) is not None


async def test_tool_error_is_shown_to_the_model_and_the_run_continues(run_scripted):
    lookup_e999 = ToolCall("get_employee_info", "Look up the employee.", {"employee_id": "E999"})

    llm, result = await run_scripted(REQUEST_1, lookup_e999, CHECK_E002_LAPTOP, APPROVE_E002)

    failed = result.steps[0]
    assert failed.observation.ok is False
    assert "EMPLOYEE_NOT_FOUND" in failed.observation.text
    assert llm.requests[1][3] == [(lookup_e999, failed.observation.text)]
    assert result.stop == "decided"


async def test_invalid_decision_is_shown_to_the_model_to_correct(run_scripted):
    unsure = ToolCall(
        "submit_decision", "Not sure.", {**APPROVE_E002.arguments, "decision": "maybe"}
    )

    llm, result = await run_scripted(REQUEST_1, CHECK_E002_LAPTOP, unsure, APPROVE_E002)

    rejected = result.steps[1]
    assert rejected.call == unsure
    assert rejected.observation.ok is False
    assert rejected.observation.text.startswith("Invalid decision: decision:")
    assert llm.requests[2][3][1] == (unsure, rejected.observation.text)
    assert result.decision.decision == "approve"


async def test_run_stops_without_a_decision_at_the_step_limit(run_scripted):
    """The scripted model has exactly three calls, so a fourth request would fail the test."""
    _, result = await run_scripted(REQUEST_1, LOOKUP_E002, LOOKUP_E002, LOOKUP_E002, max_steps=3)

    assert result.stop == "step_limit"
    assert result.decision is None
    assert [step.number for step in result.steps] == [1, 2, 3]


async def test_each_step_is_reported_as_soon_as_it_is_recorded(run_scripted):
    seen = []

    _, result = await run_scripted(
        REQUEST_1, LOOKUP_E002, CHECK_E002_LAPTOP, APPROVE_E002, on_step=seen.append
    )

    assert seen == list(result.steps)
    assert isinstance(result, AgentResult)
