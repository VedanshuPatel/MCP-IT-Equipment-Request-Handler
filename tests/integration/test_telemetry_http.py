"""End-to-end: the server process's spans join the client's trace over Streamable HTTP.

The server runs with ``OTEL_ENABLED=true``, so it prints its spans to its log. The client's
``MCP send`` span puts the trace context in the request, and the server's span must name that
client span as its parent: one trace per request across both processes (REQUIREMENTS N4).
"""

import json
import time
from collections.abc import Callable

import pytest
from opentelemetry import trace

from it_equipment.agent.mcp_client import McpToolClient

pytestmark = pytest.mark.anyio


@pytest.fixture(scope="module")
def server_env() -> dict[str, str]:
    """Switch on the server's telemetry, and print each span as soon as it ends."""
    return {"OTEL_ENABLED": "true", "PYTHONUNBUFFERED": "1"}


@pytest.fixture
def server_spans(server_data_dir) -> Callable[[], list[dict]]:
    """Reader: ``server_spans()`` gives the spans the server has printed to its log so far."""

    def read() -> list[dict]:
        log = (server_data_dir / "server.log").read_text()
        decoder, found, start = json.JSONDecoder(), [], log.find('{\n    "name"')
        while start != -1:
            span, end = decoder.raw_decode(log, start)
            found.append(span)
            start = log.find('{\n    "name"', end)
        return found

    return read


async def test_server_span_is_a_child_of_the_clients_span(server_url, server_spans, spans):
    with trace.get_tracer("test").start_as_current_span("agent.run"):
        async with McpToolClient(server_url) as mcp:
            await mcp.call_tool("get_employee_info", {"employee_id": "E002"})
    (client,) = [
        span
        for span in spans.get_finished_spans()
        if span.name == "MCP send tools/call get_employee_info"
    ]

    for _ in range(50):
        server = [span for span in server_spans() if span["name"] == "tools/call get_employee_info"]
        if server:
            break
        time.sleep(0.1)

    (span,) = server
    assert span["context"]["trace_id"] == f"0x{client.context.trace_id:032x}"
    assert span["parent_id"] == f"0x{client.context.span_id:016x}"
    assert span["resource"]["attributes"]["service.name"] == "it-equipment-mcp-server"
