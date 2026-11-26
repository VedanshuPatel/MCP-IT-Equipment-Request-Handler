"""Fixtures for the agent tests: a scripted model against the real MCP server, in-process."""

from collections.abc import Awaitable, Callable

import pytest

from it_equipment.agent.llm import ToolCall
from it_equipment.agent.mcp_client import McpToolClient
from it_equipment.agent.react import run_agent
from it_equipment.server import create_server


@pytest.fixture
def run_scripted(tools, scripted_llm) -> Callable[..., Awaitable]:
    """Factory that runs the agent with a scripted model and the real server, in-process.

    Usage: ``llm, result = await run_scripted(request, *calls, **options)``. The model replays
    ``calls``; the server uses the tools fixture (today 2026-11-24, tickets in a temporary
    folder).
    """

    async def run(request: str, *calls: ToolCall | Exception, **options) -> tuple:
        llm = scripted_llm(*calls)
        async with McpToolClient(create_server(tools)) as mcp:
            result = await run_agent(llm, mcp, request, **options)
        return llm, result

    return run
