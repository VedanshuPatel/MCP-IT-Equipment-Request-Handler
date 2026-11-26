"""The ReAct loop (SCOPE Part 4): Thought, Action, Observation until a decision.

Each step, the model sees the request, the tools and every earlier step, and makes exactly
one tool call. MCP tools are called on the server; ``submit_decision`` ends the run. Tool
errors, blocked calls and invalid decisions become observations, so the model can correct
itself.

Guardrails (REQUIREMENTS 9) surround the loop, and escalation is the safety default: a
blocked request, a second invalid reply, the step limit, a model that cannot be reached, or a
draft the output checks reject all end in an escalation that the agent's own code files with
``flag_for_human_review``. A run therefore always ends with a decision.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from pydantic import ValidationError

from it_equipment.agent.catalog import ToolSpec
from it_equipment.agent.decision import (
    SUBMIT_DECISION,
    SUBMIT_DECISION_TOOL,
    AgentReasonCode,
    Decision,
    SubmittedDecision,
)
from it_equipment.agent.guardrails import (
    FLAG_FOR_HUMAN_REVIEW,
    MAX_REQUEST_LENGTH,
    check_input,
    check_output,
    check_step,
    employee_id_in,
)
from it_equipment.agent.llm import History, LLMCallError, LLMClient, LLMError, ToolCall
from it_equipment.agent.mcp_client import McpToolClient, Observation
from it_equipment.agent.prompts import AGENT_INSTRUCTIONS, request_block
from it_equipment.agent.trace import AgentResult, Step, StopReason
from it_equipment.config import DEFAULT_AGENT_MAX_STEPS

#: The longest ticket reason the escalation store accepts.
MAX_REASON_LENGTH = 500

#: Plain-language reasons for the escalations the agent files itself (rule R6: no codes).
_WHY = {
    "MISSING_EMPLOYEE_ID": "because it does not include your employee ID",
    "GUARDRAIL_TRIGGERED": "because it could not be decided automatically",
    "AGENT_ERROR": "because the automatic review could not be completed",
}


async def run_agent(
    llm: LLMClient,
    mcp: McpToolClient,
    request: str,
    *,
    max_steps: int = DEFAULT_AGENT_MAX_STEPS,
    on_step: Callable[[Step], None] | None = None,
) -> AgentResult:
    """Handle one request with the ReAct loop and its guardrails.

    Args:
        llm: The model.
        mcp: An open connection to the MCP server.
        request: The employee's request.
        max_steps: Steps allowed before the agent escalates (G6).
        on_step: Called with each step as soon as it is recorded, for a live trace.

    Returns:
        The trace and the final decision: the model's, or the agent's escalation.
    """
    escalate = _Escalator(mcp, request, on_step)
    violation = check_input(request)
    if violation:
        return await escalate([], "input_guardrail", violation.code, str(violation))

    tools = [*await mcp.list_tools(), SUBMIT_DECISION_TOOL]
    allowed = [spec.name for spec in tools]
    prompt = request_block(request)
    steps: list[Step] = []
    for number in range(1, max_steps + 1):
        history = [(step.call, step.observation.text) for step in steps]
        try:
            call = _next_call(llm, prompt, tools, history)
        except LLMError as error:
            reason = f"G4: two invalid model replies in a row ({error})"
            return await escalate(steps, "invalid_output", "AGENT_ERROR", reason)
        except LLMCallError as error:
            return await escalate(
                steps, "model_error", "AGENT_ERROR", f"model unavailable: {error}"
            )

        if call.tool == SUBMIT_DECISION:
            try:
                draft = SubmittedDecision.model_validate(call.arguments)
            except ValidationError as error:
                observation = _rejected(call, error)
            else:
                violation = check_output(draft, steps)
                if violation:
                    reason = str(violation)
                    return await escalate(steps, "output_guardrail", violation.code, reason)
                return AgentResult(request, tuple(steps), "decided", draft, call.thought)
        elif problem := check_step(call, allowed, steps):
            observation = Observation(call.tool, call.arguments, ok=False, data=None, text=problem)
        else:
            observation = await mcp.call_tool(call.tool, _arguments_to_send(call, request))
        steps.append(Step(number, call, observation))
        if on_step is not None:
            on_step(steps[-1])

    return await escalate(
        steps, "step_limit", "AGENT_ERROR", f"G6: no decision in {max_steps} steps"
    )


def _next_call(
    llm: LLMClient, prompt: str, tools: Sequence[ToolSpec], history: History
) -> ToolCall:
    """Ask the model for its next call, with one retry after an invalid reply (G4)."""
    try:
        return llm.next_call(AGENT_INSTRUCTIONS, prompt, tools, history)
    except LLMError:
        return llm.next_call(AGENT_INSTRUCTIONS, prompt, tools, history)


def _arguments_to_send(call: ToolCall, request: str) -> dict:
    """The model's arguments, except that a ticket always holds the employee's own words."""
    if call.tool == FLAG_FOR_HUMAN_REVIEW:
        return {**call.arguments, "request": request}
    return call.arguments


def _rejected(call: ToolCall, error: ValidationError) -> Observation:
    """An error observation that tells the model what was wrong with its decision."""
    problems = "; ".join(
        f"{'.'.join(str(part) for part in issue['loc'])}: {issue['msg']}"
        for issue in error.errors()
    )
    return Observation(
        call.tool, call.arguments, ok=False, data=None, text=f"Invalid decision: {problems}"
    )


class _Escalator:
    """Files an escalation from the agent's own code and builds the final result.

    Used when the model cannot be trusted to escalate: the request was blocked, the model
    misbehaved or could not be reached, or its draft failed the output guardrails. If this run
    already filed a ticket for the same request, the store's duplicate guard returns it.
    """

    def __init__(
        self, mcp: McpToolClient, request: str, on_step: Callable[[Step], None] | None
    ) -> None:
        """Remember the connection, the request and the trace callback."""
        self._mcp = mcp
        self._request = request
        self._on_step = on_step

    async def __call__(
        self, steps: list[Step], stop: StopReason, code: AgentReasonCode, reason: str
    ) -> AgentResult:
        """File the ticket, record the call as a step and return the escalation."""
        employee_id = employee_id_in(self._request)
        arguments = {
            "employee_id": employee_id,
            "request": self._request[:MAX_REQUEST_LENGTH] if self._request.strip() else "(empty)",
            "reason": f"{code}: {reason}"[:MAX_REASON_LENGTH],
        }
        observation = await self._mcp.call_tool(FLAG_FOR_HUMAN_REVIEW, arguments)
        call = ToolCall(FLAG_FOR_HUMAN_REVIEW, f"(agent) {reason}", arguments)
        step = Step(len(steps) + 1, call, observation)
        if self._on_step is not None:
            self._on_step(step)
        ticket_id = (observation.data or {}).get("ticket_id") if observation.ok else None
        decision = Decision(
            employee_id=employee_id,
            item=None,
            decision="escalate",
            reason_code=code,
            response=_escalation_response(code, ticket_id),
            ticket_id=ticket_id,
        )
        return AgentResult(
            self._request, (*steps, step), stop, decision, reason, decided_by="agent"
        )


def _escalation_response(code: AgentReasonCode, ticket_id: str | None) -> str:
    """The employee's message for an escalation the agent filed (rules R1, R5, R6)."""
    if ticket_id is None:
        return (
            "Your request could not be decided automatically, and it could not be recorded for "
            "review. Please submit it again later."
        )
    return (
        f"Your request has been passed to a human reviewer {_WHY[code]}. Your ticket is "
        f"{ticket_id}, and a reviewer will follow up with you."
    )
