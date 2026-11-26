"""Live: the keyless fallback model takes over when Foundry is unreachable (REQUIREMENTS N5).

The fallback needs no key, so this test needs no settings, only an internet connection; Foundry
is pointed at a host that does not exist. It uses the default fallback (OVHcloud AI Endpoints),
or the model chosen by the optional FALLBACK_ENDPOINT and FALLBACK_MODEL. OVHcloud's anonymous
mode allows 2 requests per minute, so the run takes a minute or two. Run with::

    pytest -m live --no-cov
"""

import pytest

from it_equipment.agent.llm import ChatCompletionsLLM, FallbackLLM, FoundryLLM
from it_equipment.agent.mcp_client import McpToolClient
from it_equipment.agent.react import run_agent
from it_equipment.config import FallbackSettings, FoundrySettings

pytestmark = [pytest.mark.live, pytest.mark.anyio]

REQUEST = (
    "Hi, this is E002. My laptop is about 2.5 years old and really slow now. Can I get a new one?"
)

#: A Foundry endpoint whose host never resolves (``.invalid`` is reserved for that).
UNREACHABLE_FOUNDRY = FoundrySettings(
    endpoint="https://no-such-resource.invalid/openai/v1", api_key="unused", deployment="unused"
)


async def test_keyless_fallback_decides_the_run_when_foundry_is_unreachable(
    live_env, server_url, spans
):
    fallback = ChatCompletionsLLM.from_settings(FallbackSettings.from_env(live_env))
    llm = FallbackLLM(FoundryLLM.from_settings(UNREACHABLE_FOUNDRY), fallback)

    async with McpToolClient(server_url) as mcp:
        result = await run_agent(llm, mcp, REQUEST)

    assert result.stop == "decided", result.decision_thought
    assert (result.decision.decision, result.decision.reason_code) == ("approve", "REFRESH_DUE")
    answered_by = {
        span.attributes["gen_ai.response.model"]
        for span in spans.get_finished_spans()
        if span.name == "llm.generate"
    }
    assert answered_by == {fallback.model_name}
