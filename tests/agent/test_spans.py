"""The agent's OpenTelemetry spans (REQUIREMENTS N4, AC-22), with a scripted model.

The ``spans`` fixture keeps every span of the run in memory: the agent's own spans and the
ones the ``mcp`` library records for each request the in-process server handles. (Over HTTP
the client also records an ``MCP send`` span; see ``tests/integration/test_telemetry_http.py``.)
"""

from collections.abc import Callable

import pytest
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.trace import StatusCode

from it_equipment.agent.llm import LLMError, ToolCall

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
CHECK_E002 = ToolCall(
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
CHECK_E004 = ToolCall(
    "check_request_eligibility",
    "Check the damaged laptop against policy.",
    {"employee_id": "E004", "item": "laptop"},
)
FLAG_E004 = ToolCall(
    "flag_for_human_review",
    "Not eligible, but the laptop was damaged by a spill: a human must decide.",
    {"employee_id": "E004", "request": REQUEST_3, "reason": "EXCEPTION_REQUESTED: spill"},
)
ESCALATE_E004 = ToolCall(
    "submit_decision",
    "The ticket is filed, so I escalate the spilled-coffee request.",
    {
        "employee_id": "E004",
        "item": "laptop",
        "decision": "escalate",
        "reason_code": "EXCEPTION_REQUESTED",
        "response": "Your request needs a human review (ticket ESC-000001). A reviewer will "
        "follow up with you about your spilled coffee laptop.",
        "ticket_id": "ESC-000001",
    },
)
CONFIRMED = ToolCall("submit_review", "The draft matches.", {"verdict": "confirmed", "issues": []})


@pytest.fixture
def named(spans) -> Callable[[str], list[ReadableSpan]]:
    """Lookup: ``named("agent.step")`` gives this test's finished spans with that name."""
    return lambda name: [span for span in spans.get_finished_spans() if span.name == name]


async def test_run_is_one_trace_with_steps_model_calls_and_mcp_calls(run_scripted, spans, named):
    await run_scripted(REQUEST_1, LOOKUP_E002, CHECK_E002, APPROVE_E002, CONFIRMED)

    finished = spans.get_finished_spans()
    (run,) = named("agent.run")
    steps = sorted(named("agent.step"), key=lambda span: span.attributes["agent.step"])
    (server,) = named("tools/call get_employee_info")
    (reflection,) = named("agent.reflection")

    # Opening the MCP session (server/discover) happens before the run, in its own trace.
    in_run = [span for span in finished if span.name != "server/discover"]
    assert {span.context.trace_id for span in in_run} == {run.context.trace_id}
    assert [step.parent.span_id for step in steps] == [run.context.span_id] * 3
    assert server.parent.span_id == steps[0].context.span_id
    assert reflection.parent.span_id == steps[2].context.span_id
    assert len(named("llm.generate")) == 4


async def test_spans_record_the_outcome_actions_model_and_verdict(run_scripted, named):
    await run_scripted(REQUEST_1, LOOKUP_E002, CHECK_E002, APPROVE_E002, CONFIRMED)

    (run,) = named("agent.run")
    assert dict(run.attributes) == {
        "agent.stop": "decided",
        "agent.steps": 3,
        "agent.employee_id": "E002",
        "agent.decision": "approve",
        "agent.reason_code": "REFRESH_DUE",
        "agent.ticket_id": "",
    }
    steps = sorted(named("agent.step"), key=lambda span: span.attributes["agent.step"])
    assert [step.attributes["agent.action"] for step in steps] == [
        "get_employee_info",
        "check_request_eligibility",
        "submit_decision",
    ]
    models = {span.attributes["gen_ai.request.model"] for span in named("llm.generate")}
    assert models == {"scripted"}
    (reflection,) = named("agent.reflection")
    assert dict(reflection.attributes) == {
        "agent.review.verdict": "confirmed",
        "agent.review.issues": 0,
    }


async def test_agent_escalation_is_a_span_without_any_model_call(run_scripted, named):
    await run_scripted("Can I get a new keyboard?")

    (escalation,) = named("agent.escalation")
    (flag,) = named("tools/call flag_for_human_review")
    assert dict(escalation.attributes) == {
        "agent.stop": "input_guardrail",
        "agent.reason_code": "MISSING_EMPLOYEE_ID",
    }
    assert flag.parent.span_id == escalation.context.span_id
    assert named("llm.generate") == []


async def test_invalid_model_reply_marks_its_span_as_an_error(run_scripted, named):
    await run_scripted(REQUEST_1, LLMError("no tool call"), CHECK_E002, APPROVE_E002, CONFIRMED)

    failed = named("llm.generate")[0]
    assert failed.status.status_code == StatusCode.ERROR
    assert failed.events[0].attributes["exception.type"].endswith("LLMError")


async def test_no_span_holds_the_request_the_thoughts_or_the_response(run_scripted, spans):
    """AC-22: the ticket call sends the whole request, yet no span may contain any of it."""
    await run_scripted(REQUEST_3, CHECK_E004, FLAG_E004, ESCALATE_E004, CONFIRMED)

    texts = []
    for span in spans.get_finished_spans():
        texts += [span.name, span.status.description or ""]
        texts += [str(value) for value in span.attributes.values()]
        for event in span.events:
            texts += [str(value) for value in event.attributes.values()]
    private = [
        REQUEST_3,
        "spilled coffee",
        "spill",
        ESCALATE_E004.arguments["response"],
        *(call.thought for call in (CHECK_E004, FLAG_E004, ESCALATE_E004, CONFIRMED)),
    ]
    assert [(phrase, text) for phrase in private for text in texts if phrase in text] == []
