"""Unit tests for the agent's tool catalog, built from the real server's tool definitions.

``MCPServer.list_tools()`` returns the same definitions a client receives, without a
network or a client session, so these tests follow any change to the real tools.
"""

import pytest
from mcp.types import Tool

from it_equipment.agent.catalog import THOUGHT_SCHEMA, ToolSpec, build_catalog
from it_equipment.server import create_server

pytestmark = pytest.mark.anyio


@pytest.fixture
async def server_tools(tools) -> list[Tool]:
    """The real server's tool definitions, exactly as a client would receive them."""
    return await create_server(tools).list_tools()


async def test_catalog_has_the_four_tools_without_ping_in_server_order(server_tools):
    specs = build_catalog(server_tools)

    assert [spec.name for spec in specs] == [
        "get_employee_info",
        "get_policy_limits",
        "check_request_eligibility",
        "flag_for_human_review",
    ]


async def test_spec_adds_a_required_thought_before_the_real_arguments(server_tools):
    eligibility = next(tool for tool in server_tools if tool.name == "check_request_eligibility")
    server_properties = eligibility.input_schema["properties"]

    spec = ToolSpec.from_mcp(eligibility)

    assert spec.parameters == {
        "type": "object",
        "properties": {
            "thought": THOUGHT_SCHEMA,
            "employee_id": server_properties["employee_id"],
            "item": server_properties["item"],
        },
        "required": ["thought", "employee_id", "item"],
        "additionalProperties": False,
    }


async def test_spec_keeps_a_one_line_description_and_the_read_only_hint(server_tools):
    by_name = {spec.name: spec for spec in build_catalog(server_tools)}
    spec = by_name["check_request_eligibility"]

    assert spec.description.startswith("Check whether the employee may receive one unit")
    assert "\n" not in spec.description
    assert spec.read_only is True


async def test_only_flag_for_human_review_changes_data(server_tools):
    specs = build_catalog(server_tools)

    assert [spec.name for spec in specs if not spec.read_only] == ["flag_for_human_review"]


async def test_tool_without_arguments_gets_only_the_thought(server_tools):
    """``ping`` takes no arguments; its schema has no ``required`` list at all."""
    ping = next(tool for tool in server_tools if tool.name == "ping")

    parameters = ToolSpec.from_mcp(ping).parameters

    assert parameters["properties"] == {"thought": THOUGHT_SCHEMA}
    assert parameters["required"] == ["thought"]


async def test_tool_without_annotations_is_not_read_only(server_tools):
    """Every server tool is annotated, so drop the annotations from a real one to test it."""
    ping = next(tool for tool in server_tools if tool.name == "ping")
    unannotated = ping.model_copy(update={"annotations": None})

    assert ToolSpec.from_mcp(unannotated).read_only is False
