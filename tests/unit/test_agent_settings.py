"""Unit tests for the Foundry settings and ``.env`` loading."""

import os

import pytest

from it_equipment.config import FoundrySettings, load_env_file

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
