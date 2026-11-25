"""The tool catalog: MCP tool definitions adapted for the model (Adapter pattern).

The agent discovers tools at runtime with ``list_tools()``; nothing about the server's tools
is hard-coded here. Each tool's argument schema gets one extra required argument,
``thought``, so every tool call carries the model's reason for making it: the Thought of the
ReAct trace. The agent removes it again before the call reaches the MCP server.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mcp.types import Tool

#: Server tools the agent should not see (``ping`` is only a connectivity check).
HIDDEN_TOOLS = frozenset({"ping"})

#: The argument added to every tool: why the model is making this call.
THOUGHT = "thought"
THOUGHT_SCHEMA = {
    "type": "string",
    "description": "One sentence: why you are calling this tool now.",
}


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """What the model is told about one tool.

    Attributes:
        name: Tool name.
        description: What the tool does, from its docstring.
        parameters: JSON Schema of the arguments: the server's, with ``thought`` added first.
        read_only: True if the tool only reads data.
    """

    name: str
    description: str
    parameters: dict[str, Any]
    read_only: bool

    @classmethod
    def from_mcp(cls, tool: Tool) -> ToolSpec:
        """Adapt an MCP ``Tool`` definition."""
        schema = tool.input_schema
        return cls(
            name=tool.name,
            description=" ".join((tool.description or "").split()),
            parameters={
                "type": "object",
                "properties": {THOUGHT: dict(THOUGHT_SCHEMA), **schema.get("properties", {})},
                "required": [THOUGHT, *schema.get("required", [])],
                "additionalProperties": False,
            },
            read_only=bool(tool.annotations and tool.annotations.read_only_hint),
        )


def build_catalog(tools: list[Tool]) -> list[ToolSpec]:
    """Return the agent-visible tools, without ``HIDDEN_TOOLS``, in server order."""
    return [ToolSpec.from_mcp(tool) for tool in tools if tool.name not in HIDDEN_TOOLS]
