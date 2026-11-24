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
    assert "reachable" in tools["ping"].description


async def test_ping_call_returns_pong():
    async with Client(create_server()) as client:
        result = await client.call_tool("ping", {})

    assert not result.is_error
    assert result.content[0].text == "pong"


async def test_unknown_tool_is_an_error():
    async with Client(create_server()) as client:
        result = await client.call_tool("does_not_exist", {})

    assert result.is_error
