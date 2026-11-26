"""The agent's final decision (REQUIREMENTS 6.1) and the ``submit_decision`` tool.

``Decision`` is the record every run ends with. The model submits a ``SubmittedDecision``,
which is narrower: it must name an item and may only use the model's reason codes. The agent's
own code makes the other escalations (missing ID, guardrail, agent error), so those codes are
never offered to the model.

The ``submit_decision`` schema is generated from ``SubmittedDecision``, so the strict tool
schema and the validation of the reply cannot drift apart. The tool is local to the agent: it
never reaches the MCP server.
"""

from __future__ import annotations

from typing import Literal

from mcp.types import Tool, ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field

from it_equipment.agent.catalog import ToolSpec

#: The name of the agent-local tool that ends a run.
SUBMIT_DECISION = "submit_decision"

#: The codes the model may give (REQUIREMENTS 6.2 and 6.3).
ModelReasonCode = Literal[
    "NEW_ALLOCATION",
    "REFRESH_DUE",
    "LIMIT_REACHED",
    "ROLE_NOT_ELIGIBLE",
    "EXCEPTION_REQUESTED",
    "UNKNOWN_ITEM",
    "EMPLOYEE_NOT_FOUND",
    "AMBIGUOUS_REQUEST",
]

#: The escalation codes only the agent's own code files (REQUIREMENTS 6.3).
AgentReasonCode = Literal["MISSING_EMPLOYEE_ID", "GUARDRAIL_TRIGGERED", "AGENT_ERROR"]

#: Every code a final decision can carry.
ReasonCode = Literal[ModelReasonCode, AgentReasonCode]


class Decision(BaseModel):
    """The decision record a run ends with (REQUIREMENTS 6.1)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    employee_id: str = Field(description="The employee ID from the request, for example 'E002'.")
    item: str | None = Field(description="The item requested, or null when it is not known.")
    decision: Literal["approve", "deny", "escalate"] = Field(
        description="approve, deny or escalate, following the decision table."
    )
    reason_code: ReasonCode = Field(description="The reason code behind the decision.")
    response: str = Field(
        description="The message to the employee: plain language, at most 120 words."
    )
    ticket_id: str | None = Field(
        description="The ticket ID from flag_for_human_review when escalating, otherwise null."
    )


class SubmittedDecision(Decision):
    """What the model may submit: it must name the item and use only the model's codes."""

    item: str = Field(
        description="The catalog item requested, or the item as the employee wrote it."
    )
    reason_code: ModelReasonCode = Field(
        description="The eligibility reason code, or the escalation code for an escalation."
    )


#: ``submit_decision`` as the model sees it: the submission's fields plus the usual ``thought``.
SUBMIT_DECISION_TOOL = ToolSpec.from_mcp(
    Tool(
        name=SUBMIT_DECISION,
        description=(
            "Submit the final decision. Call it once, as the last step, after the tools have "
            "given you the facts the decision rests on."
        ),
        input_schema=SubmittedDecision.model_json_schema(),
        annotations=ToolAnnotations(read_only_hint=True),
    )
)
