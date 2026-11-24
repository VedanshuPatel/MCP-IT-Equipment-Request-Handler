"""MCP protocol tests against an in-process server (no network).

``mcp.Client`` accepts the server object itself and talks to it through in-memory streams,
so these tests check tool registration and calls exactly as a real client sees them.
"""

import pytest
from mcp import Client

from it_equipment.server import create_server

pytestmark = pytest.mark.anyio


async def test_server_registers_ping_tool_with_description():
    async with Client(create_server()) as client:
        result = await client.list_tools()

    tools = {tool.name: tool for tool in result.tools}
    assert "ping" in tools
    assert "reachable" in (tools["ping"].description or "")


async def test_ping_call_returns_pong():
    async with Client(create_server()) as client:
        result = await client.call_tool("ping", {})

    assert not result.is_error
    assert result.content[0].text == "pong"


async def test_unknown_tool_is_an_error():
    async with Client(create_server()) as client:
        result = await client.call_tool("does_not_exist", {})

    assert result.is_error


async def test_get_employee_info_is_listed_with_input_schema(tools):
    async with Client(create_server(tools)) as client:
        result = await client.list_tools()

    tool = next(tool for tool in result.tools if tool.name == "get_employee_info")
    assert tool.input_schema["required"] == ["employee_id"]
    assert "E002" in tool.input_schema["properties"]["employee_id"]["description"]


async def test_get_employee_info_returns_structured_profile(tools):
    async with Client(create_server(tools)) as client:
        result = await client.call_tool("get_employee_info", {"employee_id": "E002"})

    assert not result.is_error
    assert result.structured_content["role"] == "manager"
    assert result.structured_content["tenure_years"] == 7


async def test_unknown_employee_is_a_tool_error_carrying_the_code(tools):
    async with Client(create_server(tools)) as client:
        result = await client.call_tool("get_employee_info", {"employee_id": "E999"})

    assert result.is_error
    assert "EMPLOYEE_NOT_FOUND: no employee with ID E999" in result.content[0].text


async def test_malformed_id_is_a_tool_error_carrying_the_code(tools):
    async with Client(create_server(tools)) as client:
        result = await client.call_tool("get_employee_info", {"employee_id": "12"})

    assert result.is_error
    assert "INVALID_EMPLOYEE_ID:" in result.content[0].text
