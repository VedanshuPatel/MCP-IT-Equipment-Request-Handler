"""Unit tests for reading and validating settings."""

from pathlib import Path

import pytest

from it_equipment.config import (
    DEFAULT_SERVER_URL,
    ServerSettings,
    agent_max_steps,
    data_dir,
    mcp_server_url,
    otel_enabled,
)


def test_defaults_listen_on_localhost_port_8000():
    settings = ServerSettings.from_env({})

    assert (settings.host, settings.port, settings.path) == ("127.0.0.1", 8000, "/mcp")
    assert settings.url == "http://127.0.0.1:8000/mcp"


def test_host_and_port_come_from_environment():
    settings = ServerSettings.from_env({"MCP_HOST": "localhost", "MCP_PORT": "9123"})

    assert settings.url == "http://localhost:9123/mcp"


def test_ipv6_loopback_is_bracketed_in_url():
    assert ServerSettings(host="::1", port=8000).url == "http://[::1]:8000/mcp"


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.10", "example.com"])
def test_non_loopback_host_is_rejected(host):
    with pytest.raises(ValueError, match="loopback"):
        ServerSettings.from_env({"MCP_HOST": host})


@pytest.mark.parametrize("port", ["0", "65536", "-1"])
def test_out_of_range_port_is_rejected(port):
    with pytest.raises(ValueError, match="between 1 and 65535"):
        ServerSettings.from_env({"MCP_PORT": port})


def test_non_numeric_port_is_rejected():
    with pytest.raises(ValueError, match="must be an integer"):
        ServerSettings.from_env({"MCP_PORT": "eighty"})


def test_server_url_defaults_to_local_server():
    assert mcp_server_url({}) == DEFAULT_SERVER_URL == "http://127.0.0.1:8000/mcp"


def test_server_url_comes_from_environment():
    assert mcp_server_url({"MCP_SERVER_URL": "http://localhost:9000/mcp"}) == (
        "http://localhost:9000/mcp"
    )


def test_data_dir_defaults_to_data_folder():
    assert data_dir({}) == Path("data")


def test_data_dir_comes_from_environment(tmp_path):
    assert data_dir({"DATA_DIR": str(tmp_path)}) == tmp_path


def test_agent_step_limit_defaults_to_8():
    assert agent_max_steps({}) == 8


def test_agent_step_limit_comes_from_environment():
    assert agent_max_steps({"AGENT_MAX_STEPS": "12"}) == 12


@pytest.mark.parametrize(
    ("raw", "message"),
    [("eight", "must be an integer"), ("0", "must be at least 1"), ("-3", "must be at least 1")],
)
def test_invalid_agent_step_limit_is_rejected(raw, message):
    with pytest.raises(ValueError, match=f"AGENT_MAX_STEPS {message}"):
        agent_max_steps({"AGENT_MAX_STEPS": raw})


@pytest.mark.parametrize("raw", ["1", "true", "TRUE", " yes ", "on"])
def test_telemetry_is_on_for_true_values(raw):
    assert otel_enabled({"OTEL_ENABLED": raw}) is True


@pytest.mark.parametrize(
    "env", [{}, {"OTEL_ENABLED": "false"}, {"OTEL_ENABLED": "0"}, {"OTEL_ENABLED": ""}]
)
def test_telemetry_is_off_by_default_and_for_other_values(env):
    assert otel_enabled(env) is False


def test_blank_agent_step_limit_keeps_the_default():
    assert agent_max_steps({"AGENT_MAX_STEPS": " "}) == 8
