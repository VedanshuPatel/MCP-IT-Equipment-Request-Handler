"""Reflection (REQUIREMENTS 8): a separate review of every draft decision before it is final.

The reviewer is a second, independent model call with its own instructions. It sees the
request, the tool results recorded in this run and the draft, and answers through the strict
``submit_review`` tool: ``confirmed``, or ``revise`` with a list of issues. The ReAct loop
shows the review to the agent as the observation of its ``submit_decision`` call, so after a
``revise`` the agent fixes the issues and submits again.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Literal

from mcp.types import Tool, ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from it_equipment.agent.catalog import ToolSpec
from it_equipment.agent.decision import SubmittedDecision
from it_equipment.agent.llm import LLMClient, LLMError, ToolCall, next_call_with_retry
from it_equipment.agent.mcp_client import Observation
from it_equipment.agent.prompts import REVIEW_INSTRUCTIONS, request_block
from it_equipment.agent.trace import Step

#: The name of the reviewer's only tool.
SUBMIT_REVIEW = "submit_review"


class Review(BaseModel):
    """The reviewer's verdict on one draft decision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    verdict: Literal["confirmed", "revise"] = Field(
        description="confirmed when the draft is correct, otherwise revise."
    )
    issues: list[str] = Field(
        description="One entry per problem: quote the wrong words and say why. Empty when "
        "confirmed."
    )


#: ``submit_review`` as the reviewer sees it: the ``Review`` fields plus the usual ``thought``.
SUBMIT_REVIEW_TOOL = ToolSpec.from_mcp(
    Tool(
        name=SUBMIT_REVIEW,
        description="Submit your review of the draft decision. Call it once.",
        input_schema=Review.model_json_schema(),
        annotations=ToolAnnotations(read_only_hint=True),
    )
)


def review_prompt(request: str, steps: Sequence[Step], draft: SubmittedDecision) -> str:
    """The reviewer's input: the request, every recorded tool result, and the draft."""
    results = "\n".join(
        f"{step.number}. {step.call.tool}({json.dumps(step.call.arguments)}) -> "
        f"{step.observation.text}"
        for step in steps
    )
    return (
        f"{request_block(request)}\n\n"
        f"<tool_results>\n{results or '(none)'}\n</tool_results>\n\n"
        f"<draft>\n{draft.model_dump_json(indent=2)}\n</draft>"
    )


def review_draft(
    llm: LLMClient, request: str, steps: Sequence[Step], draft: SubmittedDecision
) -> Review:
    """Ask the reviewer for its verdict on a draft decision.

    Args:
        llm: The model that reviews.
        request: The employee's request.
        steps: The steps recorded so far in this run: the evidence.
        draft: The decision the agent submitted.

    Returns:
        The verdict, with the issues to fix when it is ``revise``.

    Raises:
        LLMError: If the reviewer's reply is invalid twice, or is not a valid review.
        LLMCallError: If the model cannot be reached.
    """
    prompt = review_prompt(request, steps, draft)
    call = next_call_with_retry(llm, REVIEW_INSTRUCTIONS, prompt, [SUBMIT_REVIEW_TOOL])
    if call.tool != SUBMIT_REVIEW:
        raise LLMError(f"the reviewer called {call.tool!r} instead of {SUBMIT_REVIEW}")
    try:
        return Review.model_validate(call.arguments)
    except ValidationError as error:
        raise LLMError(
            f"the reviewer's verdict is invalid ({error.error_count()} problems)"
        ) from error


def review_observation(call: ToolCall, review: Review) -> Observation:
    """The review, as the observation of the agent's ``submit_decision`` call."""
    if review.verdict == "confirmed":
        text = "Review: confirmed."
    else:
        issues = "\n".join(f"- {issue}" for issue in review.issues)
        text = f"Review: revise. Fix these issues, then call submit_decision again:\n{issues}"
    return Observation(call.tool, call.arguments, ok=True, data=review.model_dump(), text=text)
