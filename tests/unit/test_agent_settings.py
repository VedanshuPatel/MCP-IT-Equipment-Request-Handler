"""Unit tests for the Foundry and fallback settings and ``.env`` loading."""

import os

import pytest

from it_equipment.config import (
    DEFAULT_FALLBACK_ENDPOINT,
    DEFAULT_FALLBACK_MAX_RETRIES,
    DEFAULT_FALLBACK_MODEL,
    FallbackSettings,
    FoundrySettings,
    load_env_file,
)

FULL = {
    "FOUNDRY_ENDPOINT": "https://example.services.ai.azure.com/openai/v1",
    "FOUNDRY_API_KEY": "secret-key-123",
    "FOUNDRY_DEPLOYMENT": "gpt-6-astra",
}


def test_reads_the_three_foundry_variables():
    settings = FoundrySettings.from_env(FULL)

    assert settings.endpoint == FULL["FOUNDRY_ENDPOINT"]
    assert settings.deployment == "gpt-6-astra"
    assert settings.api_key == "secret-key-123"


def test_foundry_retries_default_to_2_and_can_be_changed():
    assert FoundrySettings.from_env(FULL).max_retries == 2
    assert FoundrySettings.from_env({**FULL, "FOUNDRY_MAX_RETRIES": "5"}).max_retries == 5


@pytest.mark.parametrize(
    ("raw", "message"), [("often", "must be an integer"), ("-2", "must be at least 0")]
)
def test_invalid_foundry_retries_are_rejected(raw, message):
    with pytest.raises(ValueError, match=f"FOUNDRY_MAX_RETRIES {message}"):
        FoundrySettings.from_env({**FULL, "FOUNDRY_MAX_RETRIES": raw})


def test_api_key_never_appears_in_repr():
    assert "secret-key-123" not in repr(FoundrySettings.from_env(FULL))


@pytest.mark.parametrize("name", sorted(FULL))
def test_missing_or_blank_variable_is_named_but_no_value_leaks(name):
    env = {**FULL, name: "   "}

    with pytest.raises(ValueError, match=name) as raised:
        FoundrySettings.from_env(env)

    assert "secret-key-123" not in str(raised.value)


def test_load_env_file_does_not_override_existing_variables(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("FOUNDRY_DEPLOYMENT=from-file\nIT_EQUIPMENT_TEST_ONLY=loaded\n")
    monkeypatch.setenv("FOUNDRY_DEPLOYMENT", "from-shell")
    monkeypatch.delenv("IT_EQUIPMENT_TEST_ONLY", raising=False)

    assert load_env_file(env_file) is True
    assert os.environ["FOUNDRY_DEPLOYMENT"] == "from-shell"
    assert os.environ["IT_EQUIPMENT_TEST_ONLY"] == "loaded"
    monkeypatch.delenv("IT_EQUIPMENT_TEST_ONLY")


def test_missing_env_file_is_not_an_error(tmp_path):
    assert load_env_file(tmp_path / "absent.env") is False


def test_fallback_defaults_to_the_keyless_ovhcloud_model():
    settings = FallbackSettings.from_env({})

    assert settings.endpoint == DEFAULT_FALLBACK_ENDPOINT
    assert settings.endpoint == "https://oai.endpoints.kepler.ai.cloud.ovh.net/v1"
    assert settings.model == DEFAULT_FALLBACK_MODEL == "Qwen3.5-397B-A17B"
    assert settings.max_retries == DEFAULT_FALLBACK_MAX_RETRIES == 8


def test_fallback_model_endpoint_and_retries_can_be_changed():
    env = {
        "FALLBACK_ENDPOINT": " https://keyless.example.com/v1 ",
        "FALLBACK_MODEL": "other-model",
        "FALLBACK_MAX_RETRIES": "3",
    }

    settings = FallbackSettings.from_env(env)

    assert settings == FallbackSettings("https://keyless.example.com/v1", "other-model", 3)


def test_blank_fallback_variables_keep_the_defaults():
    blank = {"FALLBACK_ENDPOINT": "  ", "FALLBACK_MODEL": "", "FALLBACK_MAX_RETRIES": " "}

    settings = FallbackSettings.from_env(blank)

    assert settings == FallbackSettings()


@pytest.mark.parametrize(
    ("raw", "message"), [("many", "must be an integer"), ("-1", "must be at least 0")]
)
def test_invalid_fallback_retries_are_rejected(raw, message):
    with pytest.raises(ValueError, match=f"FALLBACK_MAX_RETRIES {message}"):
        FallbackSettings.from_env({"FALLBACK_MAX_RETRIES": raw})


def test_fallback_settings_hold_no_secret():
    """The fallback is always called without a key, so there is no key to ask for."""
    assert set(FallbackSettings.__dataclass_fields__) == {"endpoint", "model", "max_retries"}
