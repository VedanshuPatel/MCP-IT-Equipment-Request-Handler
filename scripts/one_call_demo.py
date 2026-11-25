"""SCOPE Suggested Approach step 5: one tool call for a hard-coded request, with Foundry.

Usage::

    python -m it_equipment.server        # terminal 1
    python scripts/one_call_demo.py      # terminal 2 (needs FOUNDRY_* in .env)

Prints the model's Thought, the tool call it chose (Action) and what the MCP server returned
(Observation). The API key is never printed.
"""

import json

import anyio

from it_equipment.agent.first_call import run_one_tool_call
from it_equipment.agent.llm import FoundryLLM
from it_equipment.agent.mcp_client import McpToolClient
from it_equipment.config import FoundrySettings, load_env_file, mcp_server_url

REQUEST = (
    "Hi, this is E002. My laptop is about 2.5 years old and really slow now. Can I get a new one?"
)


async def main() -> None:
    """Run the hard-coded request through one model-chosen tool call."""
    load_env_file()
    llm = FoundryLLM.from_settings(FoundrySettings.from_env())
    url = mcp_server_url()
    async with McpToolClient(url) as mcp:
        print(f"Connected to {url}; model: {llm.model_name}")
        print(f"Request: {REQUEST}\n")
        call, observation = await run_one_tool_call(llm, mcp, REQUEST)
    print(f"Thought: {call.thought}")
    print(f"Action: {call.tool}({json.dumps(call.arguments)})")
    print(f"Observation (ok={observation.ok}):")
    print(json.dumps(observation.data, indent=2) if observation.ok else observation.text)


if __name__ == "__main__":
    anyio.run(main)
