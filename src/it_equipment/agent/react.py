"""The ReAct loop (SCOPE Part 4): Thought, Action, Observation until a decision.

Each step, the model sees the request, the tools and every earlier step, and makes exactly
one tool call. MCP tools are called on the server; ``submit_decision`` ends the run. Tool
errors and invalid decisions become observations, so the model can correct itself.
"""

from __future__ import annotations

from collections.abc import Callable

from pydantic import ValidationError

from it_equipment.agent.decision import SUBMIT_DECISION, SUBMIT_DECISION_TOOL, Decision
from it_equipment.agent.llm import LLMClient, ToolCall
from it_equipment.agent.mcp_client import McpToolClient, Observation
from it_equipment.agent.prompts import AGENT_INSTRUCTIONS, request_block
from it_equipment.agent.trace import AgentResult, Step

#: Model calls allowed per request (REQUIREMENTS G6).
DEFAULT_MAX_STEPS = 8


async def run_agent(
    llm: LLMClient,
    mcp: McpToolClient,
    request: str,
    *,
    max_steps: int = DEFAULT_MAX_STEPS,
    on_step: Callable[[Step], None] | None = None,
) -> AgentResult:
    """Handle one request with the ReAct loop.

    Args:
        llm: The model.
        mcp: An open connection to the MCP server.
        request: The employee's request.
        max_steps: Model calls allowed before the run stops without a decision.
        on_step: Called with each step as soon as it is recorded, for a live trace.

    Returns:
        The trace and, if the model submitted a valid one, the decision.
    """
    tools = [*await mcp.list_tools(), SUBMIT_DECISION_TOOL]
    prompt = request_block(request)
    steps: list[Step] = []
    for number in range(1, max_steps + 1):
        history = [(step.call, step.observation.text) for step in steps]
        call = llm.next_call(AGENT_INSTRUCTIONS, prompt, tools, history)
        if call.tool == SUBMIT_DECISION:
            try:
                decision = Decision.model_validate(call.arguments)
            except ValidationError as error:
                observation = _rejected(call, error)
            else:
                return AgentResult(request, tuple(steps), "decided", decision, call.thought)
        else:
            observation = await mcp.call_tool(call.tool, call.arguments)
        step = Step(number, call, observation)
        steps.append(step)
        if on_step is not None:
            on_step(step)
    return AgentResult(request, tuple(steps), "step_limit")


def _rejected(call: ToolCall, error: ValidationError) -> Observation:
    """An error observation that tells the model what was wrong with its decision."""
    problems = "; ".join(
        f"{'.'.join(str(part) for part in issue['loc'])}: {issue['msg']}"
        for issue in error.errors()
    )
    return Observation(
        call.tool, call.arguments, ok=False, data=None, text=f"Invalid decision: {problems}"
    )
