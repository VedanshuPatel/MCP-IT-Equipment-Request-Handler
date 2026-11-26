"""Run the ReAct agent on one request with Foundry and print its trace.

Usage::

    python -m it_equipment.server                       # terminal 1
    python scripts/run_agent.py                         # terminal 2: demo request 1
    python scripts/run_agent.py "Hi, I'm E003 and ..."  # any request

Prints each step (Thought, Action, Observation) as it happens, then the final decision.
Needs FOUNDRY_* in .env; the API key is never printed.
"""

import sys

import anyio

from it_equipment.agent.llm import FoundryLLM
from it_equipment.agent.mcp_client import McpToolClient
from it_equipment.agent.react import run_agent
from it_equipment.agent.trace import Step, format_result, format_step
from it_equipment.config import FoundrySettings, load_env_file, mcp_server_url

#: Demo request 1 (REQUIREMENTS 11), used when no request is given.
DEFAULT_REQUEST = (
    "Hi, this is E002. My laptop is about 2.5 years old and really slow now. Can I get a new one?"
)


def print_step(step: Step) -> None:
    """Print one step as soon as the agent records it."""
    print(format_step(step), end="\n\n", flush=True)


async def main(request: str) -> None:
    """Run the agent on ``request`` against the running MCP server."""
    load_env_file()
    llm = FoundryLLM.from_settings(FoundrySettings.from_env())
    url = mcp_server_url()
    async with McpToolClient(url) as mcp:
        print(f"Connected to {url}; model: {llm.model_name}")
        print(f"Request: {request}\n")
        result = await run_agent(llm, mcp, request, on_step=print_step)
    print(format_result(result))


if __name__ == "__main__":
    anyio.run(main, " ".join(sys.argv[1:]) or DEFAULT_REQUEST)
