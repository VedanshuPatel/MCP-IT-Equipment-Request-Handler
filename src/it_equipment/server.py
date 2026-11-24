"""MCP server for the IT equipment request handler.

Start it with ``python -m it_equipment.server``. It serves the MCP protocol over Streamable
HTTP at ``http://MCP_HOST:MCP_PORT/mcp`` (default ``http://127.0.0.1:8000/mcp``).
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from it_equipment import __version__
from it_equipment.config import ServerSettings

SERVER_NAME = "it-equipment"


def ping() -> str:
    """Check that the server is reachable.

    Returns:
        Always ``"pong"``.
    """
    return "pong"


def create_server() -> MCPServer:
    """Build the MCP server and register its tools.

    Returns:
        A configured server that is not running yet. Tests connect to it in-process;
        ``main`` serves it over HTTP.
    """
    server = MCPServer(
        name=SERVER_NAME,
        version=__version__,
        instructions="Tools for checking IT equipment requests against company policy.",
    )
    server.tool()(ping)
    return server


def main(settings: ServerSettings | None = None) -> None:
    """Serve the MCP server over Streamable HTTP until the process is stopped.

    Args:
        settings: Where to listen. Defaults to ``ServerSettings.from_env()``.
    """
    settings = settings or ServerSettings.from_env()
    create_server().run(
        transport="streamable-http",
        host=settings.host,
        port=settings.port,
        streamable_http_path=settings.path,
    )


if __name__ == "__main__":  # pragma: no cover
    main()
