"""Application settings, read from environment variables.

Each phase adds only the settings it needs. Values come from the process environment.
``load_env_file()`` copies a local ``.env`` file into it first, without overriding variables
that are already set; ``.env`` is git-ignored and holds the Foundry secrets.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

#: Hosts the MCP server may bind to. Any other address would expose it beyond this machine
#: (requirement N1).
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

DEFAULT_SERVER_URL = "http://127.0.0.1:8000/mcp"
DEFAULT_DATA_DIR = "data"

#: Model calls the agent may make per request (REQUIREMENTS G6).
DEFAULT_AGENT_MAX_STEPS = 8

#: Retries for a failed Foundry request: the SDK's default. Kept low so that, during an outage,
#: the agent switches to the fallback after a few seconds instead of waiting.
DEFAULT_FOUNDRY_MAX_RETRIES = 2

#: The default fallback model (REQUIREMENTS N5): OVHcloud AI Endpoints in anonymous mode, which
#: needs no API key. Its function-calling guide uses this model.
DEFAULT_FALLBACK_ENDPOINT = "https://oai.endpoints.kepler.ai.cloud.ovh.net/v1"
DEFAULT_FALLBACK_MODEL = "Qwen3.5-397B-A17B"

#: OVHcloud's anonymous mode allows 2 requests per minute; the SDK retries a 429 with back-off,
#: so eight retries wait up to about 40 seconds for the next free slot.
DEFAULT_FALLBACK_MAX_RETRIES = 8

#: Values of OTEL_ENABLED that switch telemetry on, compared ignoring case.
TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


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


def data_dir(env: Mapping[str, str] | None = None) -> Path:
    """Return the folder that holds the mock data, from ``DATA_DIR``.

    Args:
        env: Variables to read. Defaults to the process environment.

    Returns:
        The configured folder, or ``data`` (relative to the working directory) when unset.
    """
    env = os.environ if env is None else env
    return Path(env.get("DATA_DIR", DEFAULT_DATA_DIR))


def _whole_number(env: Mapping[str, str], name: str, default: int, minimum: int) -> int:
    """Read an optional whole-number setting; unset or blank gives ``default``.

    Raises:
        ValueError: If the value is not a whole number of at least ``minimum``.
    """
    raw = env.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from None
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}, got {value}")
    return value


def agent_max_steps(env: Mapping[str, str] | None = None) -> int:
    """Return how many steps the agent may take per request, from ``AGENT_MAX_STEPS``.

    Args:
        env: Variables to read. Defaults to the process environment.

    Returns:
        The configured limit, or 8 when unset or blank.

    Raises:
        ValueError: If the value is not a whole number of at least 1.
    """
    env = os.environ if env is None else env
    return _whole_number(env, "AGENT_MAX_STEPS", DEFAULT_AGENT_MAX_STEPS, minimum=1)


def otel_enabled(env: Mapping[str, str] | None = None) -> bool:
    """Return whether OpenTelemetry spans should be exported, from ``OTEL_ENABLED``.

    Args:
        env: Variables to read. Defaults to the process environment.

    Returns:
        True for ``1``, ``true``, ``yes`` or ``on`` (any case); False when unset or anything else.
    """
    env = os.environ if env is None else env
    return env.get("OTEL_ENABLED", "").strip().lower() in TRUE_VALUES


def load_env_file(path: Path | None = None) -> bool:
    """Load variables from a ``.env`` file into the process environment.

    Variables that are already set win, so a real environment (CI, a shell export) is never
    overridden by the file.

    Args:
        path: The file to read. Defaults to ``.env`` in the working directory.

    Returns:
        True if the file existed and was read.
    """
    return load_dotenv(path or Path(".env"), override=False)


@dataclass(frozen=True, slots=True)
class FoundrySettings:
    """How to reach the Microsoft Foundry deployment that the agent uses.

    Attributes:
        endpoint: OpenAI-compatible base URL, ``https://<resource>.services.ai.azure.com/openai/v1``.
        api_key: The Foundry key. Hidden from ``repr``, so it never appears in logs or tracebacks.
        deployment: The deployment (model) name, for example ``gpt-6-astra``.
        max_retries: How often the SDK retries a failed request (timeout, rate limit, server
            error) before the agent switches to the fallback.
    """

    endpoint: str
    api_key: str = field(repr=False)
    deployment: str
    max_retries: int = DEFAULT_FOUNDRY_MAX_RETRIES

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> FoundrySettings:
        """Build settings from ``FOUNDRY_ENDPOINT``, ``FOUNDRY_API_KEY`` and ``FOUNDRY_DEPLOYMENT``.

        The optional ``FOUNDRY_MAX_RETRIES`` defaults to 2.

        Args:
            env: Variables to read. Defaults to the process environment.

        Returns:
            The settings.

        Raises:
            ValueError: If any of the three required variables is missing or empty (the message
                names them, never their values), or ``FOUNDRY_MAX_RETRIES`` is not a whole
                number of at least 0.
        """
        env = os.environ if env is None else env
        names = ("FOUNDRY_ENDPOINT", "FOUNDRY_API_KEY", "FOUNDRY_DEPLOYMENT")
        missing = [name for name in names if not env.get(name, "").strip()]
        if missing:
            raise ValueError(f"Missing Foundry settings: {', '.join(missing)} (see .env.example)")
        return cls(
            endpoint=env["FOUNDRY_ENDPOINT"].strip(),
            api_key=env["FOUNDRY_API_KEY"].strip(),
            deployment=env["FOUNDRY_DEPLOYMENT"].strip(),
            max_retries=_whole_number(
                env, "FOUNDRY_MAX_RETRIES", DEFAULT_FOUNDRY_MAX_RETRIES, minimum=0
            ),
        )


@dataclass(frozen=True, slots=True)
class FallbackSettings:
    """Which hosted model takes over when Foundry has an outage (REQUIREMENTS N5).

    The fallback is always called without an API key, so nobody is asked for a secret: any
    replacement must be a keyless, OpenAI-compatible Chat Completions endpoint. Every setting is
    optional; the defaults use OVHcloud AI Endpoints in anonymous mode.

    Attributes:
        endpoint: The service's OpenAI-compatible base URL.
        model: The model name the service expects.
        max_retries: How often the SDK retries a failed request, such as a rate limit (429).
    """

    endpoint: str = DEFAULT_FALLBACK_ENDPOINT
    model: str = DEFAULT_FALLBACK_MODEL
    max_retries: int = DEFAULT_FALLBACK_MAX_RETRIES

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> FallbackSettings:
        """Build settings from the optional ``FALLBACK_*`` variables.

        Reads ``FALLBACK_ENDPOINT``, ``FALLBACK_MODEL`` and ``FALLBACK_MAX_RETRIES``.

        Args:
            env: Variables to read. Defaults to the process environment.

        Returns:
            The settings; an unset or blank variable keeps its default.

        Raises:
            ValueError: If ``FALLBACK_MAX_RETRIES`` is not a whole number of at least 0.
        """
        env = os.environ if env is None else env
        return cls(
            endpoint=env.get("FALLBACK_ENDPOINT", "").strip() or DEFAULT_FALLBACK_ENDPOINT,
            model=env.get("FALLBACK_MODEL", "").strip() or DEFAULT_FALLBACK_MODEL,
            max_retries=_whole_number(
                env, "FALLBACK_MAX_RETRIES", DEFAULT_FALLBACK_MAX_RETRIES, minimum=0
            ),
        )
