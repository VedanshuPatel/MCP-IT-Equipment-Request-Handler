"""Connect to the running MCP server, list its tools and call ``ping``.

Usage::

    python -m it_equipment.server      # terminal 1
    python scripts/hello_client.py     # terminal 2

The server URL comes from ``MCP_SERVER_URL`` (default ``http://127.0.0.1:8000/mcp``).
"""

import anyio
from mcp import Client

from it_equipment.config import mcp_server_url


async def main() -> None:
    """Connect, print the registered tools, and print the ``ping`` result."""
    url = mcp_server_url()
    async with Client(url) as client:
        tools = await client.list_tools()
        print(f"Connected to {url}")
        print("Tools:", ", ".join(tool.name for tool in tools.tools))
        result = await client.call_tool("ping", {})
        print("ping ->", result.content[0].text)


if __name__ == "__main__":
    anyio.run(main)
