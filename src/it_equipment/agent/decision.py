"""The agent's final decision (REQUIREMENTS 6.1) and the ``submit_decision`` tool.

The model finishes a run by calling ``submit_decision``. Its schema is generated from the
``Decision`` model, so the strict tool schema and the validation of the reply cannot drift
apart. The tool is local to the agent: it never reaches the MCP server.
"""

from __future__ import annotations

from typing import Literal

from mcp.types import Tool, ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field

from it_equipment.agent.catalog import ToolSpec

#: The name of the agent-local tool that ends a run.
SUBMIT_DECISION = "submit_decision"

#: The codes the model may give (REQUIREMENTS 6.2 and 6.3). The codes only the agent's own code
#: files (missing ID, guardrail, agent error) are not offered to the model.
DecisionReasonCode = Literal[
    "NEW_ALLOCATION",
    "REFRESH_DUE",
    "LIMIT_REACHED",
    "ROLE_NOT_ELIGIBLE",
    "EXCEPTION_REQUESTED",
    "UNKNOWN_ITEM",
    "EMPLOYEE_NOT_FOUND",
    "AMBIGUOUS_REQUEST",
]


class Decision(BaseModel):
    """The decision record the model submits (REQUIREMENTS 6.1)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    employee_id: str = Field(description="The employee ID from the request, for example 'E002'.")
    item: str = Field(
        description="The catalog item requested, or the item as the employee wrote it."
    )
    decision: Literal["approve", "deny", "escalate"] = Field(
        description="approve, deny or escalate, following the decision table."
    )
    reason_code: DecisionReasonCode = Field(
        description="The eligibility reason code, or the escalation code for an escalation."
    )
    response: str = Field(
        description="The message to the employee: plain language, at most 120 words."
    )
    ticket_id: str | None = Field(
        description="The ticket ID from flag_for_human_review when escalating, otherwise null."
    )


#: ``submit_decision`` as the model sees it: the ``Decision`` fields plus the usual ``thought``.
SUBMIT_DECISION_TOOL = ToolSpec.from_mcp(
    Tool(
        name=SUBMIT_DECISION,
        description=(
            "Submit the final decision. Call it once, as the last step, after the tools have "
            "given you the facts the decision rests on."
        ),
        input_schema=Decision.model_json_schema(),
        annotations=ToolAnnotations(read_only_hint=True),
    )
)
