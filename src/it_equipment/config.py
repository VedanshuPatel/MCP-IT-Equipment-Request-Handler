"""Application settings, read from environment variables.

Each phase adds only the settings it needs. Values come from the process environment;
``.env`` file support arrives with the agent in Phase 7.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

#: Hosts the MCP server may bind to. Any other address would expose it beyond this machine
#: (requirement N1).
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

DEFAULT_SERVER_URL = "http://127.0.0.1:8000/mcp"


@dataclass(frozen=True, slots=True)
class ServerSettings:
    """Where the MCP server listens.

    Attributes:
        host: Interface to bind to. Must be a loopback address.
        port: TCP port, from 1 to 65535.
        path: URL path of the Streamable HTTP endpoint.

    Raises:
        ValueError: If ``host`` is not a loopback address or ``port`` is out of range.
    """

    host: str = "127.0.0.1"
    port: int = 8000
    path: str = "/mcp"

    def __post_init__(self) -> None:
        """Reject settings that are unsafe or cannot work."""
        if self.host not in LOOPBACK_HOSTS:
            allowed = ", ".join(sorted(LOOPBACK_HOSTS))
            raise ValueError(f"MCP_HOST must be a loopback address ({allowed}), got {self.host!r}")
        if not 1 <= self.port <= 65535:
            raise ValueError(f"MCP_PORT must be between 1 and 65535, got {self.port}")

    @property
    def url(self) -> str:
        """The full URL clients use to reach the server."""
        host = f"[{self.host}]" if ":" in self.host else self.host
        return f"http://{host}:{self.port}{self.path}"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> ServerSettings:
        """Build settings from ``MCP_HOST`` and ``MCP_PORT``.

        Args:
            env: Variables to read. Defaults to the process environment.

        Returns:
            The validated settings; unset variables keep their defaults.

        Raises:
            ValueError: If a variable has an invalid value.
        """
        env = os.environ if env is None else env
        raw_port = env.get("MCP_PORT", "8000")
        try:
            port = int(raw_port)
        except ValueError:
            raise ValueError(f"MCP_PORT must be an integer, got {raw_port!r}") from None
        return cls(host=env.get("MCP_HOST", "127.0.0.1"), port=port)


def mcp_server_url(env: Mapping[str, str] | None = None) -> str:
    """Return the URL a client should connect to, from ``MCP_SERVER_URL``.

    Args:
        env: Variables to read. Defaults to the process environment.

    Returns:
        The configured URL, or ``http://127.0.0.1:8000/mcp`` when unset.
    """
    env = os.environ if env is None else env
    return env.get("MCP_SERVER_URL", DEFAULT_SERVER_URL)
