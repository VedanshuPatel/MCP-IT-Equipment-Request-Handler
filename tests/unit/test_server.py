"""Unit tests for the server module, without any network."""

from mcp.server.mcpserver import MCPServer
from opentelemetry import trace

from it_equipment import server
from it_equipment.config import ServerSettings


def test_ping_returns_pong():
    assert server.ping() == "pong"


def test_create_server_returns_named_mcp_server():
    mcp_server = server.create_server()

    assert isinstance(mcp_server, MCPServer)
    assert mcp_server.name == server.SERVER_NAME


def test_main_serves_streamable_http_with_given_settings(monkeypatch):
    calls = []
    monkeypatch.setattr(MCPServer, "run", lambda self, **kwargs: calls.append(kwargs))

    server.main(ServerSettings(host="localhost", port=9001))

    assert calls == [
        {
            "transport": "streamable-http",
            "host": "localhost",
            "port": 9001,
            "streamable_http_path": "/mcp",
        }
    ]


def test_main_reads_settings_from_environment(monkeypatch):
    calls = []
    monkeypatch.setattr(MCPServer, "run", lambda self, **kwargs: calls.append(kwargs))
    monkeypatch.setenv("MCP_PORT", "9002")

    server.main()

    assert calls[0]["port"] == 9002


def test_main_switches_on_telemetry_for_the_server_when_enabled(monkeypatch):
    installed = []
    monkeypatch.setattr(trace, "set_tracer_provider", installed.append)
    monkeypatch.setattr(MCPServer, "run", lambda self, **kwargs: None)
    monkeypatch.setenv("OTEL_ENABLED", "true")

    server.main(ServerSettings())

    (provider,) = installed
    assert provider.resource.attributes["service.name"] == "it-equipment-mcp-server"
