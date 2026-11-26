"""Shared pytest fixtures."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Iterator, Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from it_equipment.repositories import (
    JsonEmployeeRepository,
    JsonlEscalationRepository,
    JsonPolicyRepository,
)
from it_equipment.tools import EquipmentTools

if TYPE_CHECKING:  # agent types are only needed for annotations here
    from it_equipment.agent.catalog import ToolSpec
    from it_equipment.agent.llm import ToolCall

#: The repository's mock data (REQUIREMENTS 2.3, 2.4 and 3).
DATA_DIR = Path(__file__).resolve().parents[1] / "data"

#: "Today" for every test, as REQUIREMENTS fixes it.
TODAY = date(2026, 11, 24)

#: The fixed "now" stamped on escalation tickets in tests.
NOW = datetime(2026, 11, 24, 9, 30, tzinfo=UTC)

#: Seconds a server process gets to start listening.
STARTUP_TIMEOUT_SECONDS = 20


@pytest.fixture
def anyio_backend() -> str:
    """Run ``@pytest.mark.anyio`` tests on asyncio only (the MCP SDK's default backend)."""
    return "asyncio"


@pytest.fixture
def mock_data_dir() -> Path:
    """The folder that holds the mock data files."""
    return DATA_DIR


@pytest.fixture
def employee_repository() -> JsonEmployeeRepository:
    """The mock employees from ``data/employees.json``."""
    return JsonEmployeeRepository(DATA_DIR / "employees.json")


@pytest.fixture
def policy_repository() -> JsonPolicyRepository:
    """The policy table from ``data/policies.json``."""
    return JsonPolicyRepository(DATA_DIR / "policies.json")


@pytest.fixture
def escalation_repository(tmp_path) -> JsonlEscalationRepository:
    """An empty escalation store in a temporary folder, so tests never write to data/."""
    return JsonlEscalationRepository(tmp_path / "escalations.jsonl")


@pytest.fixture
def tools(employee_repository, policy_repository, escalation_repository) -> EquipmentTools:
    """Tools over the mock data; today is 2026-11-24 and tickets are stamped with ``NOW``."""
    return EquipmentTools(
        employee_repository,
        policy_repository,
        escalation_repository,
        clock=lambda: TODAY,
        now=lambda: NOW,
    )


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_until_listening(port: int, process: subprocess.Popen) -> None:
    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Server exited early with code {process.returncode}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.1)
    raise TimeoutError(f"Server did not listen on port {port} within {STARTUP_TIMEOUT_SECONDS}s")


@pytest.fixture(scope="module")
def server_data_dir(tmp_path_factory) -> Path:
    """A copy of the mock data, so escalations written by a server process never touch data/."""
    folder = tmp_path_factory.mktemp("data")
    for name in ("employees.json", "policies.json"):
        shutil.copy(DATA_DIR / name, folder / name)
    return folder


@pytest.fixture(scope="module")
def server_url(server_data_dir) -> Iterator[str]:
    """Run ``python -m it_equipment.server`` on a free port and yield its URL.

    One server process per test module; it reads and writes ``server_data_dir``.
    """
    port = _free_port()
    env = {
        **os.environ,
        "MCP_HOST": "127.0.0.1",
        "MCP_PORT": str(port),
        "DATA_DIR": str(server_data_dir),
    }
    process = subprocess.Popen(
        [sys.executable, "-m", "it_equipment.server"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_until_listening(port, process)
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        process.terminate()
        process.wait(timeout=10)


class ScriptedLLM:
    """A stand-in for the real model: returns prepared tool calls in order, records each request.

    A prepared exception is raised instead of returned, to script invalid replies or a model
    that cannot be reached. The real model is a network service, so agent tests use this to
    stay fast, deterministic and free of API keys.
    """

    model_name = "scripted"

    def __init__(self, calls: list[ToolCall | Exception]) -> None:
        """Queue the tool calls (or exceptions) to return, first one first."""
        self._calls = list(calls)
        self.requests: list[tuple[str, str, list[ToolSpec], list[tuple[ToolCall, str]]]] = []

    def next_call(
        self,
        instructions: str,
        prompt: str,
        tools: Sequence[ToolSpec],
        history: Sequence[tuple[ToolCall, str]] = (),
    ) -> ToolCall:
        """Record the request, including the history, and return the next prepared call."""
        self.requests.append((instructions, prompt, list(tools), list(history)))
        if not self._calls:
            raise AssertionError("ScriptedLLM ran out of tool calls")
        reply = self._calls.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


@pytest.fixture
def scripted_llm() -> Callable[..., ScriptedLLM]:
    """Factory: ``scripted_llm(call_1, error, call_2)`` builds a model that replays those."""
    return lambda *calls: ScriptedLLM(list(calls))
