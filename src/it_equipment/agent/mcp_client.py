"""The agent's connection to the MCP server.

``McpToolClient`` wraps ``mcp.Client`` and turns every tool result, success or error, into a
plain ``Observation`` the agent can record and show to the model.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import TracebackType
from typing import Any

from mcp import Client
from mcp.server.mcpserver import MCPServer
from mcp.types import CallToolResult, TextContent

from it_equipment.agent.catalog import ToolSpec, build_catalog


@dataclass(frozen=True, slots=True)
class Observation:
    """What one tool call returned.

    Attributes:
        tool: The tool that was called.
        arguments: The arguments it was called with.
        ok: False if the tool reported an error.
        data: The structured result, when the call succeeded.
        text: The result as text: JSON for successes, the error message for failures.
    """

    tool: str
    arguments: dict[str, Any]
    ok: bool
    data: dict[str, Any] | None
    text: str


def _to_observation(tool: str, arguments: dict[str, Any], result: CallToolResult) -> Observation:
    first = result.content[0] if result.content else None
    text = first.text if isinstance(first, TextContent) else ""
    if result.is_error:
        return Observation(tool, arguments, ok=False, data=None, text=text)
    return Observation(tool, arguments, ok=True, data=result.structured_content, text=text)


class McpToolClient:
    """An async context manager connected to the MCP server.

    Args:
        target: The server URL (Streamable HTTP), or an ``MCPServer`` instance for
            in-process tests.
    """

    def __init__(self, target: str | MCPServer) -> None:
        """Remember what to connect to."""
        self._client = Client(target)

    async def __aenter__(self) -> McpToolClient:
        """Connect and initialize the MCP session."""
        await self._client.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Close the MCP session."""
        await self._client.__aexit__(exc_type, exc, tb)

    async def list_tools(self) -> list[ToolSpec]:
        """Return the agent-visible tools the server offers."""
        result = await self._client.list_tools()
        return build_catalog(result.tools)

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Observation:
        """Call a tool and return what it produced; tool errors become ``ok=False``."""
        result = await self._client.call_tool(name, arguments)
        return _to_observation(name, arguments, result)
