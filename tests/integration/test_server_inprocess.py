"""MCP protocol tests against an in-process server (no network).

``mcp.Client`` accepts the server object itself and talks to it through in-memory streams,
so these tests check tool registration and calls exactly as a real client sees them.
"""

import pytest
from mcp import Client

from it_equipment.server import create_server

pytestmark = pytest.mark.anyio


async def test_server_registers_ping_tool_with_description():
    async with Client(create_server()) as client:
        result = await client.list_tools()

    tools = {tool.name: tool for tool in result.tools}
    assert "ping" in tools
    assert "reachable" in (tools["ping"].description or "")


async def test_ping_call_returns_pong():
    async with Client(create_server()) as client:
        result = await client.call_tool("ping", {})

    assert not result.is_error
    assert result.content[0].text == "pong"


async def test_unknown_tool_is_an_error():
    async with Client(create_server()) as client:
        result = await client.call_tool("does_not_exist", {})

    assert result.is_error


async def test_get_employee_info_is_listed_with_input_schema(tools):
    async with Client(create_server(tools)) as client:
        result = await client.list_tools()

    tool = next(tool for tool in result.tools if tool.name == "get_employee_info")
    assert tool.input_schema["required"] == ["employee_id"]
    assert "E002" in tool.input_schema["properties"]["employee_id"]["description"]


async def test_get_employee_info_returns_structured_profile(tools):
    async with Client(create_server(tools)) as client:
        result = await client.call_tool("get_employee_info", {"employee_id": "E002"})

    assert not result.is_error
    assert result.structured_content["role"] == "manager"
    assert result.structured_content["tenure_years"] == 7


async def test_unknown_employee_is_a_tool_error_carrying_the_code(tools):
    async with Client(create_server(tools)) as client:
        result = await client.call_tool("get_employee_info", {"employee_id": "E999"})

    assert result.is_error
    assert "EMPLOYEE_NOT_FOUND: no employee with ID E999" in result.content[0].text


async def test_malformed_id_is_a_tool_error_carrying_the_code(tools):
    async with Client(create_server(tools)) as client:
        result = await client.call_tool("get_employee_info", {"employee_id": "12"})

    assert result.is_error
    assert "INVALID_EMPLOYEE_ID:" in result.content[0].text


async def test_get_policy_limits_is_listed_with_input_schema(tools):
    async with Client(create_server(tools)) as client:
        result = await client.list_tools()

    tool = next(tool for tool in result.tools if tool.name == "get_policy_limits")
    assert tool.input_schema["required"] == ["role"]


async def test_get_policy_limits_returns_structured_limits(tools):
    async with Client(create_server(tools)) as client:
        result = await client.call_tool("get_policy_limits", {"role": "Manager"})

    assert not result.is_error
    laptop = result.structured_content["items"][0]
    assert laptop == {"item": "laptop", "max_quantity": 1, "replacement_years": 2, "eligible": True}


async def test_unknown_role_is_a_tool_error_carrying_the_code(tools):
    async with Client(create_server(tools)) as client:
        result = await client.call_tool("get_policy_limits", {"role": "intern"})

    assert result.is_error
    assert "UNKNOWN_ROLE:" in result.content[0].text


async def test_check_request_eligibility_returns_structured_decision(tools):
    async with Client(create_server(tools)) as client:
        result = await client.call_tool(
            "check_request_eligibility", {"employee_id": "E003", "item": "monitor"}
        )

    assert not result.is_error
    assert result.structured_content["status"] == "not_eligible"
    assert result.structured_content["reason_code"] == "LIMIT_REACHED"
    assert result.structured_content["next_eligible_date"] == "2028-11-03"


async def test_unknown_employee_eligibility_is_needs_review_not_an_error(tools):
    async with Client(create_server(tools)) as client:
        result = await client.call_tool(
            "check_request_eligibility", {"employee_id": "E999", "item": "laptop"}
        )

    assert not result.is_error
    assert result.structured_content["status"] == "needs_review"


async def test_empty_item_is_a_tool_error_carrying_the_code(tools):
    async with Client(create_server(tools)) as client:
        result = await client.call_tool(
            "check_request_eligibility", {"employee_id": "E002", "item": ""}
        )

    assert result.is_error
    assert "INVALID_INPUT:" in result.content[0].text


async def test_lookup_tools_are_read_only_and_flagging_is_idempotent(tools):
    async with Client(create_server(tools)) as client:
        result = await client.list_tools()

    hints = {tool.name: tool.annotations for tool in result.tools}
    for name in ("get_employee_info", "get_policy_limits", "check_request_eligibility"):
        assert hints[name].read_only_hint is True
    assert hints["flag_for_human_review"].read_only_hint is False
    assert hints["flag_for_human_review"].idempotent_hint is True


async def test_flag_for_human_review_creates_a_ticket(tools, tmp_path):
    async with Client(create_server(tools)) as client:
        result = await client.call_tool(
            "flag_for_human_review",
            {"employee_id": "E001", "request": "Standing desk?", "reason": "UNKNOWN_ITEM: desk"},
        )

    assert not result.is_error
    assert result.structured_content == {
        "ticket_id": "ESC-000001",
        "status": "open",
        "duplicate": False,
    }
    assert (tmp_path / "escalations.jsonl").exists()


async def test_empty_reason_is_a_tool_error_carrying_the_code(tools):
    async with Client(create_server(tools)) as client:
        result = await client.call_tool(
            "flag_for_human_review", {"employee_id": "E001", "request": "Desk?", "reason": ""}
        )

    assert result.is_error
    assert "INVALID_INPUT:" in result.content[0].text
