"""Language-model clients (Strategy pattern).

The agent talks to any model through ``LLMClient``: instructions, a prompt and the tools in,
exactly one ``ToolCall`` out. Every turn ends in a tool call, so there is no free text to
parse. ``FoundryLLM`` implements it with native function calling on the Microsoft Foundry
Responses API. A local fallback model plugs in later as another implementation.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from openai import OpenAI

from it_equipment.agent.catalog import THOUGHT, ToolSpec
from it_equipment.config import FoundrySettings

#: Seconds to wait for Foundry; the SDK's default read timeout is 10 minutes.
DEFAULT_TIMEOUT_SECONDS = 60.0

#: Reply budget. Reasoning models spend part of it on hidden reasoning before the call.
DEFAULT_MAX_OUTPUT_TOKENS = 4096


class LLMError(Exception):
    """The model's reply could not be used, for example it held no tool call."""


@dataclass(frozen=True, slots=True)
class ToolCall:
    """One tool call chosen by the model: the Thought and Action of a ReAct step.

    Attributes:
        tool: The tool to call.
        thought: Why the model chose it, in its own words.
        arguments: The tool's arguments, without ``thought``.
    """

    tool: str
    thought: str
    arguments: dict[str, Any]


class LLMClient(Protocol):
    """Anything that picks the next tool call for the agent."""

    @property
    def model_name(self) -> str:
        """The model or deployment name, for traces."""
        ...

    def next_call(self, instructions: str, prompt: str, tools: Sequence[ToolSpec]) -> ToolCall:
        """Return the tool call the model chooses.

        Args:
            instructions: System instructions (the rules).
            prompt: The user turn (the request and what the agent has seen so far).
            tools: The tools the model may call.
        """
        ...


class FoundryLLM:
    """A Microsoft Foundry deployment, called through the OpenAI Responses API.

    Args:
        client: An ``openai.OpenAI`` client pointed at the Foundry endpoint.
        deployment: The deployment name to send as ``model``.
        max_output_tokens: Upper bound on the reply, reasoning included.
    """

    def __init__(
        self, client: Any, deployment: str, max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS
    ) -> None:
        """Store the client and request settings."""
        self._client = client
        self._deployment = deployment
        self._max_output_tokens = max_output_tokens

    @classmethod
    def from_settings(
        cls, settings: FoundrySettings, timeout: float = DEFAULT_TIMEOUT_SECONDS
    ) -> FoundryLLM:
        """Create a client for the configured Foundry endpoint.

        Args:
            settings: Endpoint, key and deployment.
            timeout: Seconds before a request is abandoned.

        Returns:
            A ready ``FoundryLLM``. No network call is made until ``next_call``.
        """
        client = OpenAI(
            base_url=settings.endpoint, api_key=settings.api_key, timeout=timeout, max_retries=2
        )
        return cls(client, settings.deployment)

    @property
    def model_name(self) -> str:
        """The Foundry deployment name."""
        return self._deployment

    def next_call(self, instructions: str, prompt: str, tools: Sequence[ToolSpec]) -> ToolCall:
        """Send one request and return the single tool call in the reply.

        ``tool_choice="required"`` makes the model call a tool and ``parallel_tool_calls=False``
        limits it to one, so every reply is exactly one ReAct step. Reasoning models put a
        reasoning item before the call, so the call is found by its type, not its position.

        Args:
            instructions: System instructions.
            prompt: The user turn.
            tools: The tools the model may call.

        Returns:
            The call, with the ``thought`` argument moved into ``ToolCall.thought``.

        Raises:
            LLMError: If the reply does not hold exactly one tool call, or the call's
                arguments are not a JSON object.
            openai.APIError: For connection, timeout, rate-limit, auth and server errors.
        """
        response = self._client.responses.create(
            model=self._deployment,
            instructions=instructions,
            input=prompt,
            tools=[_function_tool(spec) for spec in tools],
            tool_choice="required",
            parallel_tool_calls=False,
            max_output_tokens=self._max_output_tokens,
            store=False,
        )
        calls = [item for item in response.output if item.type == "function_call"]
        if len(calls) != 1:
            raise LLMError(
                f"{self._deployment} returned {len(calls)} tool calls, expected 1 "
                f"(response status: {response.status})"
            )
        return _to_tool_call(calls[0].name, calls[0].arguments)


def _function_tool(spec: ToolSpec) -> dict[str, Any]:
    """Describe a tool in the Responses API format.

    In strict mode the API makes the arguments match the schema exactly. Strict mode needs
    every argument to be required, so a tool with optional arguments is sent without it.
    """
    parameters = spec.parameters
    return {
        "type": "function",
        "name": spec.name,
        "description": spec.description,
        "parameters": parameters,
        "strict": set(parameters["required"]) == set(parameters["properties"]),
    }


def _to_tool_call(name: str, raw_arguments: str) -> ToolCall:
    """Parse a call's JSON arguments and move ``thought`` out of them."""
    try:
        arguments = json.loads(raw_arguments)
    except json.JSONDecodeError:
        arguments = None
    if not isinstance(arguments, dict):
        raise LLMError(f"{name} arguments are not a JSON object")
    thought = str(arguments.pop(THOUGHT, "")).strip()
    return ToolCall(tool=name, thought=thought, arguments=arguments)
