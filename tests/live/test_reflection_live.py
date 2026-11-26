"""Live tests for reflection: the real Foundry model reviews drafts against real tool results.

AC-19: a draft that promises something the tools did not return is sent back, and a correct
draft is confirmed. Opt-in and skipped without Foundry settings; run with::

    pytest -m live --no-cov
"""

import pytest

from it_equipment.agent.decision import SubmittedDecision
from it_equipment.agent.llm import ToolCall
from it_equipment.agent.mcp_client import McpToolClient
from it_equipment.agent.reflection import review_draft
from it_equipment.agent.trace import Step

pytestmark = [pytest.mark.live, pytest.mark.anyio]

REQUEST = (
    "Hi, this is E002. My laptop is about 2.5 years old and really slow now. Can I get a new one?"
)

CORRECT = SubmittedDecision(
    employee_id="E002",
    item="laptop",
    decision="approve",
    reason_code="REFRESH_DUE",
    response=(
        "Your laptop replacement is approved. Your current laptop became due for replacement "
        "on 2026-05-20, so you can get a new one."
    ),
    ticket_id=None,
)
PROMISING = CORRECT.model_copy(
    update={"response": "Your laptop replacement is approved. Your new laptop arrives on Friday."}
)


@pytest.fixture
async def eligibility_step(server_url) -> Step:
    """The real eligibility check for E002's laptop, recorded as the run's only step."""
    arguments = {"employee_id": "E002", "item": "laptop"}
    async with McpToolClient(server_url) as mcp:
        observation = await mcp.call_tool("check_request_eligibility", arguments)
    call = ToolCall("check_request_eligibility", "Check the laptop against policy.", arguments)
    return Step(1, call, observation)


async def test_reviewer_confirms_a_correct_draft(foundry_llm, eligibility_step):
    review = review_draft(foundry_llm, REQUEST, [eligibility_step], CORRECT)

    assert review.verdict == "confirmed", review.issues


async def test_reviewer_sends_back_a_draft_that_promises_a_delivery_date(
    foundry_llm, eligibility_step
):
    review = review_draft(foundry_llm, REQUEST, [eligibility_step], PROMISING)

    assert review.verdict == "revise"
    assert review.issues
