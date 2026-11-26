"""Live: a real run's spans record the outcome and nothing private (REQUIREMENTS N4, AC-22).

The real Foundry model handles demo request 3, whose escalation ticket carries the whole
request text. Opt-in and skipped without Foundry settings; run with::

    pytest -m live --no-cov
"""

import pytest

from it_equipment.agent.mcp_client import McpToolClient
from it_equipment.agent.react import run_agent

pytestmark = [pytest.mark.live, pytest.mark.anyio]

REQUEST = "E004 here. I spilled coffee on my laptop and now it won't boot. It's only 8 months old."


async def test_real_run_spans_hold_the_outcome_but_no_private_text(foundry_llm, server_url, spans):
    async with McpToolClient(server_url) as mcp:
        result = await run_agent(foundry_llm, mcp, REQUEST)

    finished = spans.get_finished_spans()
    (run,) = [span for span in finished if span.name == "agent.run"]
    assert run.attributes["agent.decision"] == result.decision.decision
    models = {
        span.attributes["gen_ai.request.model"] for span in finished if span.name == "llm.generate"
    }
    assert models == {foundry_llm.model_name}

    texts = []
    for span in finished:
        texts += [span.name, span.status.description or ""]
        texts += [str(value) for value in span.attributes.values()]
        for event in span.events:
            texts += [str(value) for value in event.attributes.values()]
    private = [REQUEST, "spilled coffee", result.decision.response]
    private += [step.call.thought for step in result.steps if len(step.call.thought) > 20]
    assert [(phrase, text) for phrase in private for text in texts if phrase in text] == []
