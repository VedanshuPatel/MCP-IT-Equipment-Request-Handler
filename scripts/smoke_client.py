"""Call ``get_employee_info`` on the running MCP server (SCOPE Suggested Approach step 3).

Usage::

    python -m it_equipment.server              # terminal 1
    python scripts/smoke_client.py             # terminal 2: looks up E002 and E999
    python scripts/smoke_client.py E004 E006   # or any IDs you choose

The server URL comes from ``MCP_SERVER_URL`` (default ``http://127.0.0.1:8000/mcp``).
"""

import json
import sys

import anyio
from mcp import Client

from it_equipment.config import mcp_server_url

DEFAULT_EMPLOYEE_IDS = ("E002", "E999")


async def main(employee_ids: tuple[str, ...]) -> None:
    """Connect, list the tools, and print ``get_employee_info`` for each ID.

    Args:
        employee_ids: IDs to look up. A missing employee prints the tool error.
    """
    url = mcp_server_url()
    async with Client(url) as client:
        tools = await client.list_tools()
        print(f"Connected to {url}")
        print("Tools:", ", ".join(sorted(tool.name for tool in tools.tools)))
        for employee_id in employee_ids:
            result = await client.call_tool("get_employee_info", {"employee_id": employee_id})
            print(f"\nget_employee_info({employee_id!r}) ->")
            if result.is_error:
                print("  error:", result.content[0].text)
            else:
                print(json.dumps(result.structured_content, indent=2))


if __name__ == "__main__":
    anyio.run(main, tuple(sys.argv[1:]) or DEFAULT_EMPLOYEE_IDS)
