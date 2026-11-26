"""Unit tests for ``FoundryLLM`` and ``ChatCompletionsLLM`` with the real OpenAI SDK.

Only the network is replaced: the ``foundry_llm`` fixture builds a real ``openai.OpenAI``
client whose ``httpx2.MockTransport`` answers with a real Responses API body. The SDK's
request building and reply parsing are both exercised, without a network or a key. The tools
offered are the real server's, adapted by the real catalog.
"""

import json
from collections.abc import Callable

import anyio
import httpx2
import pytest
from mcp.types import Tool
from openai import OpenAI

from it_equipment.agent.catalog import ToolSpec, build_catalog
from it_equipment.agent.llm import (
    DEFAULT_MAX_OUTPUT_TOKENS,
    DEFAULT_TIMEOUT_SECONDS,
    ChatCompletionsLLM,
    FoundryLLM,
    LLMCallError,
    LLMError,
    ToolCall,
    next_call_with_retry,
)
from it_equipment.config import DEFAULT_FALLBACK_ENDPOINT, FallbackSettings, FoundrySettings
from it_equipment.server import create_server

ENDPOINT = "https://example.services.ai.azure.com/openai/v1"
CHAT_SERVICE = "https://chat.example.com/v1"
LOOKUP_E002 = ("get_employee_info", '{"thought": "I need the role first.", "employee_id": "E002"}')


@pytest.fixture
def catalog(tools) -> list[ToolSpec]:
    """The agent's view of the real server's tools."""
    return build_catalog(anyio.run(create_server(tools).list_tools))


@pytest.fixture
def http_requests() -> list[httpx2.Request]:
    """Every HTTP request the OpenAI SDK sent during the test, in order."""
    return []


@pytest.fixture
def foundry_llm(http_requests) -> Callable[..., FoundryLLM]:
    """Factory: ``foundry_llm((name, arguments_json), ...)`` replies by calling those tools.

    The reply is a real Responses API body: a reasoning item first, then one
    ``function_call`` item per call. Each request is recorded in ``http_requests``.
    """

    def make(*calls: tuple[str, str]) -> FoundryLLM:
        def handler(request: httpx2.Request) -> httpx2.Response:
            http_requests.append(request)
            function_calls = [
                {
                    "type": "function_call",
                    "id": f"fc_{number}",
                    "call_id": f"call_{number}",
                    "name": name,
                    "arguments": arguments,
                    "status": "completed",
                }
                for number, (name, arguments) in enumerate(calls, start=1)
            ]
            return httpx2.Response(
                200,
                json={
                    "id": "resp_1",
                    "object": "response",
                    "created_at": 0,
                    "model": "gpt-6-astra",
                    "status": "completed",
                    "output": [{"type": "reasoning", "id": "rs_1", "summary": []}, *function_calls],
                    "parallel_tool_calls": False,
                    "tool_choice": "required",
                    "tools": [],
                },
            )

        client = OpenAI(
            base_url=ENDPOINT,
            api_key="test-key",
            http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
        )
        return FoundryLLM(client, "gpt-6-astra")

    return make


def test_posts_one_request_that_requires_exactly_one_tool_call(foundry_llm, http_requests, catalog):
    foundry_llm(LOOKUP_E002).next_call("be helpful", "<request>hi</request>", catalog)

    (request,) = http_requests
    assert request.method == "POST"
    assert str(request.url) == f"{ENDPOINT}/responses"
    assert request.headers["authorization"] == "Bearer test-key"
    body = json.loads(request.content)
    assert {key: value for key, value in body.items() if key != "tools"} == {
        "model": "gpt-6-astra",
        "instructions": "be helpful",
        "input": [{"role": "user", "content": "<request>hi</request>"}],
        "tool_choice": "required",
        "parallel_tool_calls": False,
        "max_output_tokens": DEFAULT_MAX_OUTPUT_TOKENS,
        "store": False,
    }


def test_replays_each_earlier_call_with_its_thought_and_result(foundry_llm, http_requests, catalog):
    """Nothing is stored on the service, so every request carries the whole run so far."""
    earlier = ToolCall(
        tool="get_employee_info",
        thought="I need the role first.",
        arguments={"employee_id": "E002"},
    )

    foundry_llm(LOOKUP_E002).next_call(
        "x", "<request>hi</request>", catalog, [(earlier, '{"role": "manager"}')]
    )

    assert json.loads(http_requests[0].content)["input"] == [
        {"role": "user", "content": "<request>hi</request>"},
        {
            "type": "function_call",
            "call_id": "call_1",
            "name": "get_employee_info",
            "arguments": '{"thought": "I need the role first.", "employee_id": "E002"}',
        },
        {"type": "function_call_output", "call_id": "call_1", "output": '{"role": "manager"}'},
    ]


def test_offers_every_catalog_tool_as_a_strict_function(foundry_llm, http_requests, catalog):
    foundry_llm(LOOKUP_E002).next_call("x", "y", catalog)

    sent = json.loads(http_requests[0].content)["tools"]
    assert sent == [
        {
            "type": "function",
            "name": spec.name,
            "description": spec.description,
            "parameters": spec.parameters,
            "strict": True,
        }
        for spec in catalog
    ]


def test_tool_with_an_optional_argument_is_offered_without_strict_mode(foundry_llm, http_requests):
    """Strict mode needs every argument to be required, so it is switched off here."""
    search = Tool(
        name="search",
        description="Search the catalog.",
        input_schema={
            "type": "object",
            "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}},
            "required": ["query"],
        },
    )

    foundry_llm(LOOKUP_E002).next_call("x", "y", [ToolSpec.from_mcp(search)])

    (sent,) = json.loads(http_requests[0].content)["tools"]
    assert sent["strict"] is False


def test_returns_the_call_with_the_thought_moved_out_of_the_arguments(foundry_llm, catalog):
    """The call is found by type: ``output[0]`` is the reasoning item here."""
    call = foundry_llm(LOOKUP_E002).next_call("x", "y", catalog)

    assert call == ToolCall(
        tool="get_employee_info",
        thought="I need the role first.",
        arguments={"employee_id": "E002"},
    )


@pytest.mark.parametrize(
    ("calls", "count"),
    [((), 0), ((LOOKUP_E002, LOOKUP_E002), 2)],
    ids=["no call", "two calls"],
)
def test_reply_must_hold_exactly_one_tool_call(foundry_llm, catalog, calls, count):
    with pytest.raises(LLMError, match=f"gpt-6-astra returned {count} tool calls, expected 1"):
        foundry_llm(*calls).next_call("x", "y", catalog)


@pytest.mark.parametrize(
    "arguments",
    ['{"thought": "cut off', '["E002"]'],
    ids=["invalid JSON", "not an object"],
)
def test_arguments_must_be_a_json_object(foundry_llm, catalog, arguments):
    with pytest.raises(LLMError, match="get_employee_info arguments are not a JSON object"):
        foundry_llm(("get_employee_info", arguments)).next_call("x", "y", catalog)


@pytest.fixture
def failing_llm() -> Callable[..., FoundryLLM]:
    """Factory: ``failing_llm(handler)`` gives a ``FoundryLLM`` whose HTTP layer runs ``handler``.

    The client makes no retries, so a failure surfaces at once.
    """

    def make(handler: Callable[[httpx2.Request], httpx2.Response]) -> FoundryLLM:
        client = OpenAI(
            base_url=ENDPOINT,
            api_key="test-key",
            max_retries=0,
            http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
        )
        return FoundryLLM(client, "gpt-6-astra")

    return make


def test_unreachable_endpoint_raises_a_call_error_naming_the_cause(failing_llm, catalog):
    def unreachable(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("[Errno 8] nodename nor servname provided, or not known")

    with pytest.raises(LLMCallError, match=r"APIConnectionError: \[Errno 8\] nodename") as caught:
        failing_llm(unreachable).next_call("x", "y", catalog)

    assert "test-key" not in str(caught.value)
    assert caught.value.outage is True


def test_rejected_key_raises_a_call_error(failing_llm, catalog):
    def rejected(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(401, json={"error": {"message": "Access denied", "code": "401"}})

    with pytest.raises(LLMCallError, match="gpt-6-astra request failed: AuthenticationError"):
        failing_llm(rejected).next_call("x", "y", catalog)


@pytest.mark.parametrize(
    ("status", "outage"),
    [(400, False), (401, False), (403, False), (404, False), (429, True), (500, True), (503, True)],
)
def test_status_error_says_whether_it_is_an_outage(failing_llm, catalog, status, outage):
    """Rate limits and server errors are outages; the rest are configuration errors."""

    def reply(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(status, json={"error": {"message": "failed", "code": str(status)}})

    with pytest.raises(LLMCallError) as caught:
        failing_llm(reply).next_call("x", "y", catalog)

    assert caught.value.outage is outage


def test_retry_asks_once_more_after_an_invalid_reply(scripted_llm, catalog):
    call = ToolCall("get_employee_info", "Look up.", {"employee_id": "E002"})
    llm = scripted_llm(LLMError("no tool call"), call)

    assert next_call_with_retry(llm, "x", "y", catalog) == call
    assert len(llm.requests) == 2


def test_retry_gives_up_after_a_second_invalid_reply(scripted_llm, catalog):
    llm = scripted_llm(LLMError("no tool call"), LLMError("still no tool call"))

    with pytest.raises(LLMError, match="still no tool call"):
        next_call_with_retry(llm, "x", "y", catalog)


def test_from_settings_points_the_client_at_foundry_without_calling_it():
    settings = FoundrySettings(endpoint=ENDPOINT, api_key="test-key", deployment="gpt-6-astra")

    llm = FoundryLLM.from_settings(settings)

    assert llm.model_name == "gpt-6-astra"
    assert str(llm._client.base_url) == f"{ENDPOINT}/"
    assert llm._client.timeout == DEFAULT_TIMEOUT_SECONDS
    assert llm._client.max_retries == 2


def test_from_settings_uses_the_configured_foundry_retries():
    settings = FoundrySettings(ENDPOINT, "test-key", "gpt-6-astra", max_retries=5)

    assert FoundryLLM.from_settings(settings)._client.max_retries == 5


# ------------------------------------------------------------- fallback: Chat Completions


@pytest.fixture
def chat_llm(http_requests) -> Callable[..., ChatCompletionsLLM]:
    """Factory: ``chat_llm((name, arguments_json), ..., status=200)`` for the fallback model.

    The reply is a real Chat Completions body with those tool calls, or an error body when
    ``status`` is not 200. The client is set up like ``ChatCompletionsLLM.from_settings()``,
    with a placeholder key, but makes no retries; it records each request.
    """

    def make(*calls: tuple[str, str], status: int = 200) -> ChatCompletionsLLM:
        def handler(request: httpx2.Request) -> httpx2.Response:
            http_requests.append(request)
            if status != 200:
                return httpx2.Response(status, json={"error": {"message": "unavailable"}})
            tool_calls = [
                {
                    "id": f"call_{number}",
                    "type": "function",
                    "function": {"name": n, "arguments": a},
                }
                for number, (n, a) in enumerate(calls, start=1)
            ]
            message = {"role": "assistant", "content": None, "tool_calls": tool_calls or None}
            choice = {"index": 0, "finish_reason": "tool_calls", "message": message}
            return httpx2.Response(
                200,
                json={
                    "id": "chatcmpl-1",
                    "object": "chat.completion",
                    "created": 0,
                    "model": "open-model",
                    "choices": [choice],
                },
            )

        client = OpenAI(
            base_url=CHAT_SERVICE,
            api_key="anonymous",
            max_retries=0,
            http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
        )
        return ChatCompletionsLLM(client, "open-model")

    return make


def test_fallback_posts_the_rules_the_request_and_the_tools(chat_llm, http_requests, catalog):
    chat_llm(LOOKUP_E002).next_call("be helpful", "<request>hi</request>", catalog)

    (request,) = http_requests
    assert str(request.url) == f"{CHAT_SERVICE}/chat/completions"
    assert "authorization" not in request.headers, "the fallback must not send a key"
    assert json.loads(request.content) == {
        "model": "open-model",
        "messages": [
            {"role": "system", "content": "be helpful"},
            {"role": "user", "content": "<request>hi</request>"},
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": spec.parameters,
                },
            }
            for spec in catalog
        ],
        "tool_choice": "required",
        "max_tokens": DEFAULT_MAX_OUTPUT_TOKENS,
    }


def test_fallback_replays_each_earlier_call_and_its_result(chat_llm, http_requests, catalog):
    earlier = ToolCall("get_employee_info", "I need the role first.", {"employee_id": "E002"})

    chat_llm(LOOKUP_E002).next_call("x", "y", catalog, [(earlier, '{"role": "manager"}')])

    messages = json.loads(http_requests[0].content)["messages"]
    assert messages[2:] == [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "get_employee_info",
                        "arguments": '{"thought": "I need the role first.", "employee_id": "E002"}',
                    },
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": '{"role": "manager"}'},
    ]


def test_fallback_returns_the_call_with_the_thought_moved_out(chat_llm, catalog):
    call = chat_llm(LOOKUP_E002).next_call("x", "y", catalog)

    assert call == ToolCall("get_employee_info", "I need the role first.", {"employee_id": "E002"})


@pytest.mark.parametrize(("calls", "count"), [((), 0), ((LOOKUP_E002, LOOKUP_E002), 2)])
def test_fallback_reply_must_hold_exactly_one_tool_call(chat_llm, catalog, calls, count):
    with pytest.raises(LLMError, match=f"open-model returned {count} tool calls, expected 1"):
        chat_llm(*calls).next_call("x", "y", catalog)


@pytest.mark.parametrize(("status", "outage"), [(503, True), (401, False)])
def test_fallback_errors_say_whether_they_are_outages(chat_llm, catalog, status, outage):
    with pytest.raises(LLMCallError, match="open-model request failed") as caught:
        chat_llm(status=status).next_call("x", "y", catalog)

    assert caught.value.outage is outage


def test_fallback_from_default_settings_is_the_keyless_ovhcloud_model():
    llm = ChatCompletionsLLM.from_settings(FallbackSettings())

    assert llm.model_name == "Qwen3.5-397B-A17B"
    assert str(llm._client.base_url) == f"{DEFAULT_FALLBACK_ENDPOINT}/"
    assert llm._client.timeout == DEFAULT_TIMEOUT_SECONDS
    assert llm._client.max_retries == 8


def test_fallback_from_changed_settings_calls_the_chosen_model():
    llm = ChatCompletionsLLM.from_settings(FallbackSettings(CHAT_SERVICE, "other-model", 2))

    assert llm.model_name == "other-model"
    assert str(llm._client.base_url) == f"{CHAT_SERVICE}/"
    assert llm._client.max_retries == 2
