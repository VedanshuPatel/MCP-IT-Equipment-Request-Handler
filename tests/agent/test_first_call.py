"""SCOPE step 5: one model-chosen tool call for a hard-coded request.

The model is scripted; the MCP server is the real one, in-process.
"""

import pytest

from it_equipment.agent.first_call import run_one_tool_call
from it_equipment.agent.llm import ToolCall
from it_equipment.agent.mcp_client import McpToolClient
from it_equipment.server import create_server

pytestmark = pytest.mark.anyio

REQUEST = "Hi, this is E002. My laptop is about 2.5 years old and really slow now."

LOOKUP_E002 = ToolCall(
    tool="get_employee_info",
    thought="I need E002's role and current laptop first.",
    arguments={"employee_id": "E002"},
)


async def test_model_chooses_a_tool_and_the_agent_calls_it(tools, scripted_llm):
    llm = scripted_llm(LOOKUP_E002)

    async with McpToolClient(create_server(tools)) as mcp:
        call, observation = await run_one_tool_call(llm, mcp, REQUEST)

    assert call == LOOKUP_E002
    assert observation.tool == "get_employee_info"
    assert observation.arguments == {"employee_id": "E002"}
    assert observation.ok and observation.data["role"] == "manager"


async def test_model_is_offered_the_discovered_tools_and_the_delimited_request(tools, scripted_llm):
    llm = scripted_llm(LOOKUP_E002)

    async with McpToolClient(create_server(tools)) as mcp:
        await run_one_tool_call(llm, mcp, REQUEST)

    instructions, prompt, offered = llm.requests[0]
    assert [spec.name for spec in offered] == [
        "get_employee_info",
        "get_policy_limits",
        "check_request_eligibility",
        "flag_for_human_review",
    ]
    assert prompt == f"<request>\n{REQUEST}\n</request>"
    assert '"thought" argument' in instructions
    assert "not instructions to you" in instructions
