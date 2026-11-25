"""SCOPE Suggested Approach step 5: one tool call for a hard-coded request.

The agent discovers the tools over MCP, the model picks one through native function calling,
and the agent calls it over MCP. The ReAct loop in Phase 8 repeats this step until a
decision is reached.
"""

from __future__ import annotations

from it_equipment.agent.llm import LLMClient, ToolCall
from it_equipment.agent.mcp_client import McpToolClient, Observation
from it_equipment.agent.prompts import FIRST_CALL_INSTRUCTIONS, request_block


async def run_one_tool_call(
    llm: LLMClient, mcp: McpToolClient, request: str
) -> tuple[ToolCall, Observation]:
    """Discover the tools, let the model pick one, call it, and return both.

    Args:
        llm: The model.
        mcp: An open connection to the MCP server.
        request: The employee's request.

    Returns:
        The model's choice (Thought and Action) and what the tool returned (Observation).
    """
    tools = await mcp.list_tools()
    call = llm.next_call(FIRST_CALL_INSTRUCTIONS, request_block(request), tools)
    return call, await mcp.call_tool(call.tool, call.arguments)
