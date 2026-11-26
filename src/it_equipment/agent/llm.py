"""Language-model clients (Strategy pattern).

The agent talks to any model through ``LLMClient``: instructions, the request, the tools and
the steps so far in, exactly one ``ToolCall`` out. Every turn ends in a tool call, so there is
no free text to parse.

- ``FoundryLLM``: Microsoft Foundry, native function calling on the Responses API.
- ``ChatCompletionsLLM``: a hosted model on an OpenAI-compatible Chat Completions service,
  called without an API key: the fallback. Nothing is downloaded and nothing is configured.
- ``FallbackLLM``: Foundry first, the fallback when Foundry has an outage (REQUIREMENTS N5).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from openai import (
    APIConnectionError,
    APIError,
    InternalServerError,
    Omit,
    OpenAI,
    RateLimitError,
)
from openai.types.chat import ChatCompletionMessageFunctionToolCall
from opentelemetry import trace

from it_equipment.agent.catalog import THOUGHT, ToolSpec
from it_equipment.config import FallbackSettings, FoundrySettings

_tracer = trace.get_tracer(__name__)

#: Seconds to wait for Foundry; the SDK's default read timeout is 10 minutes.
DEFAULT_TIMEOUT_SECONDS = 60.0

#: Reply budget. Reasoning models spend part of it on hidden reasoning before the call.
DEFAULT_MAX_OUTPUT_TOKENS = 4096

#: SDK errors a second model can work around: no connection or a timeout, a rate limit, or a
#: server error. Every other error is a configuration problem (key, endpoint, model, request).
_OUTAGES = (APIConnectionError, RateLimitError, InternalServerError)


class LLMError(Exception):
    """The model's reply could not be used, for example it held no tool call."""


class LLMCallError(Exception):
    """The request to the model failed: network, timeout, rate limit, authentication or server.

    The message names the error and its cause, never the API key.

    Attributes:
        outage: True when a second model could work around it (no connection, a timeout, a
            rate limit, a server error); False for configuration errors such as a wrong key.
    """

    def __init__(self, message: str, *, outage: bool = False) -> None:
        """Keep the message and whether the problem is an outage."""
        super().__init__(message)
        self.outage = outage


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


#: The steps so far: each tool call the model made and the text its tool returned.
History = Sequence[tuple[ToolCall, str]]


class LLMClient(Protocol):
    """Anything that picks the next tool call for the agent."""

    @property
    def model_name(self) -> str:
        """The model or deployment name, for traces."""
        ...

    def next_call(
        self, instructions: str, prompt: str, tools: Sequence[ToolSpec], history: History = ()
    ) -> ToolCall:
        """Return the tool call the model chooses next.

        Args:
            instructions: System instructions (the rules).
            prompt: The user turn: the delimited request.
            tools: The tools the model may call.
            history: The calls made so far in this run, each with the text its tool returned.
        """
        ...


def next_call_with_retry(
    llm: LLMClient,
    instructions: str,
    prompt: str,
    tools: Sequence[ToolSpec],
    history: History = (),
) -> ToolCall:
    """Ask for the next tool call, and ask once more after an invalid reply (REQUIREMENTS G4).

    Raises:
        LLMError: If the second reply is invalid too.
        LLMCallError: If the model cannot be reached.
    """
    try:
        return generate(llm, instructions, prompt, tools, history)
    except LLMError:
        return generate(llm, instructions, prompt, tools, history)


def generate(
    llm: LLMClient,
    instructions: str,
    prompt: str,
    tools: Sequence[ToolSpec],
    history: History = (),
) -> ToolCall:
    """One model call, recorded as an ``llm.generate`` span: the model and the tool it chose.

    A failed call marks the span as an error with the exception's type and message, which
    name the problem but never contain the prompt or the reply.
    """
    attributes = {"gen_ai.request.model": llm.model_name}
    with _tracer.start_as_current_span("llm.generate", attributes=attributes) as span:
        call = llm.next_call(instructions, prompt, tools, history)
        span.set_attributes({"agent.action": call.tool, "gen_ai.response.model": llm.model_name})
        return call


def create_llm(foundry: FoundrySettings, fallback: FallbackSettings) -> LLMClient:
    """The agent's model: Foundry, with the keyless fallback model behind it."""
    return FallbackLLM(
        FoundryLLM.from_settings(foundry), ChatCompletionsLLM.from_settings(fallback)
    )


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
            base_url=settings.endpoint,
            api_key=settings.api_key,
            timeout=timeout,
            max_retries=settings.max_retries,
        )
        return cls(client, settings.deployment)

    @property
    def model_name(self) -> str:
        """The Foundry deployment name."""
        return self._deployment

    def next_call(
        self, instructions: str, prompt: str, tools: Sequence[ToolSpec], history: History = ()
    ) -> ToolCall:
        """Send one request and return the single tool call in the reply.

        ``tool_choice="required"`` makes the model call a tool and ``parallel_tool_calls=False``
        limits it to one, so every reply is exactly one ReAct step. Reasoning models put a
        reasoning item before the call, so the call is found by its type, not its position.

        The history is sent again on every request (``store=False`` keeps nothing on the
        service). Each earlier call goes back with its ``thought``, so the model sees its own
        reasoning from the previous steps.

        Args:
            instructions: System instructions.
            prompt: The user turn.
            tools: The tools the model may call.
            history: The calls made so far, each with the text its tool returned.

        Returns:
            The call, with the ``thought`` argument moved into ``ToolCall.thought``.

        Raises:
            LLMError: If the reply does not hold exactly one tool call, or the call's
                arguments are not a JSON object.
            LLMCallError: If the request fails: connection, timeout, rate limit, auth or a
                server error, after the SDK's retries.
        """
        try:
            response = self._client.responses.create(
                model=self._deployment,
                instructions=instructions,
                input=_input_items(prompt, history),
                tools=[_function_tool(spec) for spec in tools],
                tool_choice="required",
                parallel_tool_calls=False,
                max_output_tokens=self._max_output_tokens,
                store=False,
            )
        except APIError as error:
            raise _call_error(self._deployment, error) from error
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


def _input_items(prompt: str, history: History) -> list[dict[str, Any]]:
    """The conversation in the Responses API format: the request, then each call and result.

    Calls are numbered here (``call_1``, ...) only to pair each result with its call.
    """
    items: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
    for number, (call, output) in enumerate(history, start=1):
        call_id = f"call_{number}"
        arguments = _with_thought(call)
        items.append(
            {"type": "function_call", "call_id": call_id, "name": call.tool, "arguments": arguments}
        )
        items.append({"type": "function_call_output", "call_id": call_id, "output": output})
    return items


class ChatCompletionsLLM:
    """A hosted model on an OpenAI-compatible Chat Completions service, called without a key.

    The fallback: the model runs on the service, so nothing is downloaded, and requests carry
    no ``Authorization`` header, so no key is needed. Strict schemas are not sent, because not
    every service supports them; the agent's own checks still validate every call.

    Args:
        client: An ``openai.OpenAI`` client pointed at the service.
        model: The model name to send.
        max_tokens: Upper bound on the reply.
    """

    def __init__(
        self, client: Any, model: str, max_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS
    ) -> None:
        """Store the client and request settings."""
        self._client = client
        self._model = model
        self._max_tokens = max_tokens

    @classmethod
    def from_settings(
        cls, settings: FallbackSettings, timeout: float = DEFAULT_TIMEOUT_SECONDS
    ) -> ChatCompletionsLLM:
        """Create the keyless client for the configured model; no network call is made yet.

        The OpenAI client will not start without some key, so it gets a placeholder; every
        request then omits the ``Authorization`` header, so the placeholder is never sent.
        """
        client = OpenAI(
            base_url=settings.endpoint,
            api_key="anonymous",
            timeout=timeout,
            max_retries=settings.max_retries,
        )
        return cls(client, settings.model)

    @property
    def model_name(self) -> str:
        """The model name."""
        return self._model

    def next_call(
        self, instructions: str, prompt: str, tools: Sequence[ToolSpec], history: History = ()
    ) -> ToolCall:
        """Send one Chat Completions request and return the single tool call in the reply.

        Raises:
            LLMError: If the reply does not hold exactly one tool call, or the call's
                arguments are not a JSON object.
            LLMCallError: If the request fails.
        """
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=_chat_messages(instructions, prompt, history),
                tools=[
                    {
                        "type": "function",
                        "function": {
                            "name": spec.name,
                            "description": spec.description,
                            "parameters": spec.parameters,
                        },
                    }
                    for spec in tools
                ],
                tool_choice="required",
                max_tokens=self._max_tokens,
                extra_headers={"Authorization": Omit()},
            )
        except APIError as error:
            raise _call_error(self._model, error) from error
        tool_calls = response.choices[0].message.tool_calls if response.choices else None
        calls = [
            call
            for call in tool_calls or []
            if isinstance(call, ChatCompletionMessageFunctionToolCall)
        ]
        if len(calls) != 1:
            raise LLMError(f"{self._model} returned {len(calls)} tool calls, expected 1")
        return _to_tool_call(calls[0].function.name, calls[0].function.arguments)


class FallbackLLM:
    """Foundry first, a second hosted model when Foundry has an outage (REQUIREMENTS N5).

    Only an outage switches models: no connection, a timeout, a rate limit or a server error.
    A configuration error, such as a wrong key, is raised, so it gets fixed instead of hidden.
    After an outage the fallback answers for the rest of this client's life, so later steps do
    not wait for Foundry's retries again.

    Args:
        primary: The model to try first.
        fallback: The model to use once the primary has had an outage.
    """

    def __init__(self, primary: LLMClient, fallback: LLMClient) -> None:
        """Start with the primary model."""
        self._primary = primary
        self._fallback = fallback
        self._active = primary

    @property
    def model_name(self) -> str:
        """The model answering now: the primary until an outage, then the fallback."""
        return self._active.model_name

    def next_call(
        self, instructions: str, prompt: str, tools: Sequence[ToolSpec], history: History = ()
    ) -> ToolCall:
        """Ask the active model; switch to the fallback when the primary has an outage."""
        if self._active is self._primary:
            try:
                return self._primary.next_call(instructions, prompt, tools, history)
            except LLMCallError as error:
                if not error.outage:
                    raise
                self._active = self._fallback
                trace.get_current_span().add_event(
                    "llm.fallback",
                    {"llm.from": self._primary.model_name, "llm.to": self._fallback.model_name},
                )
        return self._fallback.next_call(instructions, prompt, tools, history)


def _call_error(model: str, error: APIError) -> LLMCallError:
    """Wrap an SDK error: name it and its cause, and say whether it is an outage."""
    cause = error.__cause__ or error
    message = f"{model} request failed: {type(error).__name__}: {cause}"
    return LLMCallError(message, outage=isinstance(error, _OUTAGES))


def _with_thought(call: ToolCall) -> str:
    """A replayed call's arguments as JSON, with its ``thought`` put back first."""
    return json.dumps({THOUGHT: call.thought, **call.arguments})


def _chat_messages(instructions: str, prompt: str, history: History) -> list[dict[str, Any]]:
    """The conversation in the Chat Completions format: rules, request, then calls and results."""
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": instructions},
        {"role": "user", "content": prompt},
    ]
    for number, (call, output) in enumerate(history, start=1):
        call_id = f"call_{number}"
        function = {"name": call.tool, "arguments": _with_thought(call)}
        messages.append(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{"id": call_id, "type": "function", "function": function}],
            }
        )
        messages.append({"role": "tool", "tool_call_id": call_id, "content": output})
    return messages


def _to_tool_call(name: str, raw_arguments: str) -> ToolCall:
    """Parse a call's JSON arguments and move the required ``thought`` out of them (G4)."""
    try:
        arguments = json.loads(raw_arguments)
    except json.JSONDecodeError:
        arguments = None
    if not isinstance(arguments, dict):
        raise LLMError(f"{name} arguments are not a JSON object")
    thought = str(arguments.pop(THOUGHT, "")).strip()
    if not thought:
        raise LLMError(f"{name} call has no thought")
    return ToolCall(tool=name, thought=thought, arguments=arguments)
