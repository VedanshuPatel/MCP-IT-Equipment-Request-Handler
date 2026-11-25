"""``McpToolClient`` against the real server, in-process (no network)."""

import pytest

from it_equipment.agent.mcp_client import McpToolClient
from it_equipment.server import create_server

pytestmark = pytest.mark.anyio


async def test_lists_the_four_agent_tools_without_ping(tools):
    async with McpToolClient(create_server(tools)) as mcp:
        specs = await mcp.list_tools()

    assert {spec.name: spec.read_only for spec in specs} == {
        "get_employee_info": True,
        "get_policy_limits": True,
        "check_request_eligibility": True,
        "flag_for_human_review": False,
    }


async def test_successful_call_becomes_an_ok_observation_with_data(tools):
    async with McpToolClient(create_server(tools)) as mcp:
        observation = await mcp.call_tool("get_employee_info", {"employee_id": "E002"})

    assert observation.ok is True
    assert observation.data["role"] == "manager"
    assert '"role":"manager"' in observation.text.replace(" ", "")


async def test_tool_error_becomes_a_failed_observation_with_the_code(tools):
    async with McpToolClient(create_server(tools)) as mcp:
        observation = await mcp.call_tool("get_employee_info", {"employee_id": "E999"})

    assert observation.ok is False
    assert observation.data is None
    assert "EMPLOYEE_NOT_FOUND" in observation.text
