"""End-to-end tests: the real server process over Streamable HTTP.

The ``server_url`` fixture (``tests/conftest.py``) starts ``python -m it_equipment.server`` on a
free port, waits until it accepts connections, and stops it after the test module.
"""

import http.client
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from mcp import Client

pytestmark = pytest.mark.anyio

ROOT = Path(__file__).resolve().parents[2]


async def test_client_calls_get_policy_limits_over_http(server_url):
    async with Client(server_url) as client:
        result = await client.call_tool("get_policy_limits", {"role": "manager"})

    assert not result.is_error
    assert result.structured_content["role"] == "manager"


async def test_client_calls_check_request_eligibility_over_http(server_url):
    async with Client(server_url) as client:
        result = await client.call_tool(
            "check_request_eligibility", {"employee_id": "E001", "item": "standing desk"}
        )

    assert not result.is_error
    assert result.structured_content["reason_code"] == "UNKNOWN_ITEM"


async def test_all_four_tools_are_listed_and_callable_over_http(server_url, server_data_dir):
    """AC-14."""
    calls = {
        "get_employee_info": {"employee_id": "E002"},
        "get_policy_limits": {"role": "manager"},
        "check_request_eligibility": {"employee_id": "E002", "item": "laptop"},
        "flag_for_human_review": {
            "employee_id": "E001",
            "request": "Can I get a standing desk?",
            "reason": "UNKNOWN_ITEM: standing desk is not in the catalog",
        },
    }
    async with Client(server_url) as client:
        listed = {tool.name: tool for tool in (await client.list_tools()).tools}
        results = {name: await client.call_tool(name, args) for name, args in calls.items()}

    for name, args in calls.items():
        assert set(listed[name].input_schema["required"]) == set(args)
        assert not results[name].is_error, name
    assert (server_data_dir / "escalations.jsonl").exists()


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
    assert url.hostname is not None
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

    assert "ping" in result.stdout.split("Tools:")[1].splitlines()[0]
    assert "ping -> pong" in result.stdout


def test_smoke_client_script_prints_employee_and_not_found_error(server_url):
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "smoke_client.py")],
        env={**os.environ, "MCP_SERVER_URL": server_url},
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )

    tools_line = result.stdout.split("Tools:")[1].splitlines()[0]
    assert "get_employee_info" in tools_line
    assert '"role": "manager"' in result.stdout
    assert "EMPLOYEE_NOT_FOUND: no employee with ID E999" in result.stdout
