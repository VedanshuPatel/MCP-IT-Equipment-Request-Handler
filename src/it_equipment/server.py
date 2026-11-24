"""MCP server for the IT equipment request handler.

Start it with ``python -m it_equipment.server``. It serves the MCP protocol over Streamable
HTTP at ``http://MCP_HOST:MCP_PORT/mcp`` (default ``http://127.0.0.1:8000/mcp``).

Each MCP tool here is a thin wrapper: it calls the matching ``EquipmentTools`` method and
turns domain errors into MCP tool errors. The business logic lives in ``tools.py``.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import Annotated

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from it_equipment import __version__
from it_equipment.config import ServerSettings, data_dir
from it_equipment.errors import DomainError
from it_equipment.models import EligibilityResult, EmployeeInfo, PolicyLimits
from it_equipment.tools import EquipmentTools

SERVER_NAME = "it-equipment"

EmployeeIdArg = Annotated[
    str, Field(description="Employee ID: 'E' followed by 3 digits, for example 'E002'.")
]
RoleArg = Annotated[
    str, Field(description="Role name, for example 'manager'; returned by get_employee_info.")
]
ItemArg = Annotated[
    str, Field(description="Catalog item requested: laptop, monitor, headset or keyboard.")
]


def ping() -> str:
    """Check that the server is reachable.

    Returns:
        Always ``"pong"``.
    """
    return "pong"


@contextmanager
def _as_tool_error() -> Generator[None, None, None]:
    """Re-raise a ``DomainError`` as an MCP ``ToolError``, keeping its ``CODE: message`` text.

    A ``ToolError`` is reported to the client as ``is_error=True`` with that text, while any
    other exception is treated as a crash and its details are hidden from the client.
    """
    try:
        yield
    except DomainError as exc:
        raise ToolError(str(exc)) from exc


def create_server(tools: EquipmentTools | None = None) -> MCPServer:
    """Build the MCP server and register its tools.

    Args:
        tools: The tool implementations. Defaults to tools backed by the JSON files in
            ``DATA_DIR``; tests pass their own, for example with a fixed date.

    Returns:
        A configured server that is not running yet. Tests connect to it in-process;
        ``main`` serves it over HTTP.
    """
    tools = tools or EquipmentTools.from_data_dir(data_dir())
    server = MCPServer(
        name=SERVER_NAME,
        version=__version__,
        instructions="Tools for checking IT equipment requests against company policy.",
    )
    server.tool()(ping)

    @server.tool()
    def get_employee_info(employee_id: EmployeeIdArg) -> EmployeeInfo:
        """Look up an employee's role, tenure and current equipment on file."""
        with _as_tool_error():
            return tools.get_employee_info(employee_id)

    @server.tool()
    def get_policy_limits(role: RoleArg) -> PolicyLimits:
        """List what a role is eligible for: maximum quantity and replacement interval per item."""
        with _as_tool_error():
            return tools.get_policy_limits(role)

    @server.tool()
    def check_request_eligibility(employee_id: EmployeeIdArg, item: ItemArg) -> EligibilityResult:
        """Check whether the employee may receive one unit of the item today under policy.

        Returns eligible, not_eligible or needs_review, with a reason code. An unknown
        employee or item returns needs_review, which means a human must decide.
        """
        with _as_tool_error():
            return tools.check_request_eligibility(employee_id, item)

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