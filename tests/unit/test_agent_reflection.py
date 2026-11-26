"""Unit tests for reflection (REQUIREMENTS 8): the reviewer's tool, input and verdict."""

import json

import pytest
from pydantic import ValidationError

from it_equipment.agent.decision import SubmittedDecision
from it_equipment.agent.llm import LLMError, ToolCall
from it_equipment.agent.mcp_client import Observation
from it_equipment.agent.prompts import (
    AGENT_INSTRUCTIONS,
    DECISION_RULES,
    RESPONSE_RULES,
    REVIEW_INSTRUCTIONS,
)
from it_equipment.agent.reflection import (
    SUBMIT_REVIEW_TOOL,
    Review,
    review_draft,
    review_observation,
    review_prompt,
)
from it_equipment.agent.trace import Step

REQUEST = "Hi, this is E002. My laptop is slow. Can I get a new one?"

CONFIRMED = ToolCall(
    "submit_review", "The draft matches the results.", {"verdict": "confirmed", "issues": []}
)
REVISE = ToolCall(
    "submit_review",
    "The draft promises a delivery date.",
    {"verdict": "revise", "issues": ["'arrives Friday': no tool returned a delivery date."]},
)


@pytest.fixture
def eligible_step() -> Step:
    """The eligibility check for E002's laptop, as recorded in a run."""
    arguments = {"employee_id": "E002", "item": "laptop"}
    result = {**arguments, "status": "eligible", "reason_code": "REFRESH_DUE"}
    return Step(
        1,
        ToolCall("check_request_eligibility", "Check the laptop.", arguments),
        Observation(
            "check_request_eligibility", arguments, ok=True, data=result, text=json.dumps(result)
        ),
    )


@pytest.fixture
def draft() -> SubmittedDecision:
    """An approval of E002's laptop."""
    return SubmittedDecision(
        employee_id="E002",
        item="laptop",
        decision="approve",
        reason_code="REFRESH_DUE",
        response="Your laptop replacement is approved.",
        ticket_id=None,
    )


def test_review_takes_a_verdict_and_issues():
    review = Review.model_validate(REVISE.arguments)

    assert review.verdict == "revise"
    assert review.issues == ["'arrives Friday': no tool returned a delivery date."]


@pytest.mark.parametrize(
    "arguments",
    [{"verdict": "maybe", "issues": []}, {"verdict": "confirmed"}, {**CONFIRMED.arguments, "x": 1}],
    ids=["unknown verdict", "no issues list", "extra field"],
)
def test_invalid_review_is_rejected(arguments):
    with pytest.raises(ValidationError):
        Review.model_validate(arguments)


def test_submit_review_tool_is_strict_with_a_thought():
    parameters = SUBMIT_REVIEW_TOOL.parameters

    assert SUBMIT_REVIEW_TOOL.name == "submit_review"
    assert parameters["required"] == ["thought", "verdict", "issues"]
    assert parameters["properties"]["verdict"]["enum"] == ["confirmed", "revise"]
    assert parameters["properties"]["issues"]["items"] == {"type": "string"}


def test_agent_and_reviewer_share_the_same_rules():
    for rules in (DECISION_RULES, RESPONSE_RULES):
        assert rules in AGENT_INSTRUCTIONS
        assert rules in REVIEW_INSTRUCTIONS


def test_reviewer_input_holds_the_request_the_numbered_results_and_the_draft(eligible_step, draft):
    prompt = review_prompt(REQUEST, [eligible_step], draft)

    assert prompt.startswith(f"<request>\n{REQUEST}\n</request>\n\n<tool_results>\n")
    assert (
        '1. check_request_eligibility({"employee_id": "E002", "item": "laptop"}) -> '
        f"{eligible_step.observation.text}"
    ) in prompt
    assert prompt.endswith(f"<draft>\n{draft.model_dump_json(indent=2)}\n</draft>")


def test_reviewer_input_says_when_there_are_no_results(draft):
    assert "<tool_results>\n(none)\n</tool_results>" in review_prompt(REQUEST, [], draft)


def test_review_draft_asks_the_reviewer_with_only_its_own_tool(scripted_llm, eligible_step, draft):
    llm = scripted_llm(REVISE)

    review = review_draft(llm, REQUEST, [eligible_step], draft)

    assert review.verdict == "revise"
    ((instructions, prompt, tools, history),) = llm.requests
    assert instructions == REVIEW_INSTRUCTIONS
    assert prompt == review_prompt(REQUEST, [eligible_step], draft)
    assert tools == [SUBMIT_REVIEW_TOOL]
    assert history == []


def test_review_draft_retries_once_after_an_invalid_reply(scripted_llm, draft):
    llm = scripted_llm(LLMError("no tool call"), CONFIRMED)

    assert review_draft(llm, REQUEST, [], draft).verdict == "confirmed"
    assert len(llm.requests) == 2


@pytest.mark.parametrize(
    ("reply", "message"),
    [
        (ToolCall("submit_decision", "Oops.", {}), "called 'submit_decision' instead"),
        (ToolCall("submit_review", "Unsure.", {"verdict": "maybe", "issues": []}), "invalid"),
    ],
    ids=["wrong tool", "invalid verdict"],
)
def test_review_draft_rejects_a_reply_that_is_not_a_valid_review(
    scripted_llm, draft, reply, message
):
    with pytest.raises(LLMError, match=message):
        review_draft(scripted_llm(reply), REQUEST, [], draft)


def test_confirmed_review_becomes_a_short_observation():
    call = ToolCall("submit_decision", "Approve.", {"decision": "approve"})

    observation = review_observation(call, Review.model_validate(CONFIRMED.arguments))

    assert (observation.ok, observation.text) == (True, "Review: confirmed.")
    assert observation.data == {"verdict": "confirmed", "issues": []}


def test_revise_review_tells_the_agent_what_to_fix():
    call = ToolCall("submit_decision", "Approve.", {"decision": "approve"})

    observation = review_observation(call, Review.model_validate(REVISE.arguments))

    assert observation.text == (
        "Review: revise. Fix these issues, then call submit_decision again:\n"
        "- 'arrives Friday': no tool returned a delivery date."
    )
    assert observation.data == REVISE.arguments
