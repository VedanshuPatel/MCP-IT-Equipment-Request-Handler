"""Unit tests for ``FallbackLLM`` (REQUIREMENTS N5) and ``create_llm``, with scripted models."""

import pytest

from it_equipment.agent.llm import (
    FallbackLLM,
    LLMCallError,
    LLMError,
    ToolCall,
    create_llm,
)
from it_equipment.config import FallbackSettings, FoundrySettings

LOOKUP = ToolCall("get_employee_info", "Look up the employee.", {"employee_id": "E002"})


#: The error FoundryLLM raises when Foundry cannot be reached.
OUTAGE = LLMCallError("gpt-6-astra request failed: APIConnectionError: [Errno 8]", outage=True)


def test_primary_answers_while_it_works(scripted_llm):
    primary = scripted_llm(LOOKUP, model_name="gpt-6-astra")
    fallback = scripted_llm(model_name="open-model")
    llm = FallbackLLM(primary, fallback)

    assert llm.next_call("x", "y", []) == LOOKUP
    assert llm.model_name == "gpt-6-astra"
    assert fallback.requests == []


def test_outage_switches_to_the_fallback_for_the_rest_of_the_run(scripted_llm):
    """The primary has one scripted reply, so asking it a second time would fail the test."""
    primary = scripted_llm(OUTAGE, model_name="gpt-6-astra")
    fallback = scripted_llm(LOOKUP, LOOKUP, model_name="open-model")
    llm = FallbackLLM(primary, fallback)

    assert llm.next_call("x", "y", []) == LOOKUP
    assert llm.model_name == "open-model"
    assert llm.next_call("x", "y", []) == LOOKUP
    assert (len(primary.requests), len(fallback.requests)) == (1, 2)


def test_fallback_gets_the_same_request(scripted_llm):
    primary = scripted_llm(OUTAGE, model_name="gpt-6-astra")
    fallback = scripted_llm(LOOKUP, model_name="open-model")

    FallbackLLM(primary, fallback).next_call("rules", "<request>hi</request>", [], [])

    assert fallback.requests == primary.requests


def test_configuration_error_is_raised_not_hidden(scripted_llm):
    wrong_key = LLMCallError("gpt-6-astra request failed: AuthenticationError", outage=False)
    fallback = scripted_llm(model_name="open-model")
    llm = FallbackLLM(scripted_llm(wrong_key), fallback)

    with pytest.raises(LLMCallError, match="AuthenticationError"):
        llm.next_call("x", "y", [])
    assert fallback.requests == []


def test_invalid_reply_is_not_an_outage(scripted_llm):
    """Guardrail G4 retries an invalid reply; the fallback is only for outages."""
    fallback = scripted_llm(model_name="open-model")
    llm = FallbackLLM(scripted_llm(LLMError("no tool call")), fallback)

    with pytest.raises(LLMError):
        llm.next_call("x", "y", [])
    assert fallback.requests == []


def test_fallback_failure_is_raised(scripted_llm):
    fallback_down = LLMCallError("open-model request failed: InternalServerError", outage=True)
    llm = FallbackLLM(scripted_llm(OUTAGE), scripted_llm(fallback_down))

    with pytest.raises(LLMCallError, match="open-model request failed"):
        llm.next_call("x", "y", [])


FOUNDRY = FoundrySettings(
    endpoint="https://example.services.ai.azure.com/openai/v1", api_key="k", deployment="astra"
)


def test_create_llm_puts_the_keyless_fallback_behind_foundry():
    llm = create_llm(FOUNDRY, FallbackSettings())

    assert isinstance(llm, FallbackLLM)
    assert llm.model_name == "astra"
