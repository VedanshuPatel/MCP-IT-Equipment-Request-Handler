"""End-to-end tests: the real server process over Streamable HTTP.

The fixture starts ``python -m it_equipment.server`` on a free port, waits until it accepts
connections, and stops it after the test module.
"""

import http.client
import json
import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from mcp import Client

pytestmark = pytest.mark.anyio

ROOT = Path(__file__).resolve().parents[2]
STARTUP_TIMEOUT_SECONDS = 20


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
def server_url() -> Iterator[str]:
    """Run the MCP server in a subprocess and yield its URL."""
    port = _free_port()
    env = {**os.environ, "MCP_HOST": "127.0.0.1", "MCP_PORT": str(port)}
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


async def test_client_calls_ping_over_http(server_url):
    async with Client(server_url) as client:
        tools = await client.list_tools()
        result = await client.call_tool("ping", {})

    assert "ping" in [tool.name for tool in tools.tools]
    assert result.content[0].text == "pong"


def _post_initialize(server_url: str, host_header: str) -> int:
    """Send a valid MCP ``initialize`` request with the given Host header; return the status."""
    url = urlsplit(server_url)
    body = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "rebinding-test", "version": "1"},
            },
        }
    )
    headers = {
        "Host": host_header,
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    connection = http.client.HTTPConnection(url.hostname, url.port, timeout=10)
    try:
        connection.request("POST", url.path, body=body, headers=headers)
        return connection.getresponse().status
    finally:
        connection.close()


def test_request_with_own_host_header_is_accepted(server_url):
    """Control case for the test below: the same request with the real Host succeeds."""
    assert _post_initialize(server_url, urlsplit(server_url).netloc) == 200


def test_request_with_foreign_host_header_is_rejected(server_url):
    """DNS-rebinding protection: the same request claiming another Host is refused."""
    assert _post_initialize(server_url, "evil.example") == 421


def test_hello_client_script_prints_pong(server_url):
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "hello_client.py")],
        env={**os.environ, "MCP_SERVER_URL": server_url},
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )

    assert "Tools: ping" in result.stdout
    assert "ping -> pong" in result.stdout
