"""Live end-to-end tests: the real Foundry model and the real MCP server over HTTP.

Opt-in, because they call a paid service and the model is not deterministic: ``pytest``
deselects them (``-m "not live"`` in ``pyproject.toml``). Run them with::

    pytest -m live --no-cov

They need ``FOUNDRY_ENDPOINT``, ``FOUNDRY_API_KEY`` and ``FOUNDRY_DEPLOYMENT`` in the
environment or in ``.env``, and are skipped without them. The assertions accept any sensible
first step, not one exact reply. A passing run also proves Foundry accepts the strict tool
schemas.
"""

import pytest

from it_equipment.agent.first_call import run_one_tool_call
from it_equipment.agent.mcp_client import McpToolClient

pytestmark = [pytest.mark.live, pytest.mark.anyio]

#: Sensible first tools for a request that names an employee and an item.
LOOKUPS = {"get_employee_info", "check_request_eligibility"}


async def test_model_starts_the_e002_laptop_request_with_a_lookup_of_e002(foundry_llm, server_url):
    request = (
        "Hi, this is E002. My laptop is about 2.5 years old and really slow now. "
        "Can I get a new one?"
    )

    async with McpToolClient(server_url) as mcp:
        call, observation = await run_one_tool_call(foundry_llm, mcp, request)

    assert call.tool in LOOKUPS, call
    assert call.arguments["employee_id"] == "E002", call
    assert call.thought.strip(), "the model gave no thought"
    assert observation.ok, observation.text


async def test_model_looks_up_an_unknown_employee_and_sees_not_found(foundry_llm, server_url):
    request = "Hi, this is E999. Can I get a new headset?"

    async with McpToolClient(server_url) as mcp:
        call, observation = await run_one_tool_call(foundry_llm, mcp, request)

    assert call.tool in LOOKUPS, call
    assert call.arguments["employee_id"] == "E999", call
    assert call.thought.strip(), "the model gave no thought"
    assert "EMPLOYEE_NOT_FOUND" in observation.text, observation.text
