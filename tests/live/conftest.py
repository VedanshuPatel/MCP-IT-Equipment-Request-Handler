"""Fixtures for the live tests, which call the real Foundry model."""

import os
from pathlib import Path

import pytest
from dotenv import dotenv_values

from it_equipment.agent.llm import FoundryLLM
from it_equipment.config import FoundrySettings

#: The repository's ``.env`` file (git-ignored), read only if it exists.
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


@pytest.fixture(scope="session")
def live_env() -> dict[str, str]:
    """Settings from the environment first, then from ``.env``.

    The file is read into a dictionary, so the process environment of the other tests is never
    changed.
    """
    from_file = {key: value for key, value in dotenv_values(ENV_FILE).items() if value}
    return {**from_file, **os.environ}


@pytest.fixture(scope="module")
def foundry_llm(live_env) -> FoundryLLM:
    """The real Foundry model, or a skip that names the missing variables, never a value."""
    try:
        settings = FoundrySettings.from_env(live_env)
    except ValueError as error:
        pytest.skip(f"live test needs Foundry settings: {error}")
    return FoundryLLM.from_settings(settings)
