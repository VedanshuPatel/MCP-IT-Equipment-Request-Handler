"""Shared pytest fixtures."""

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from it_equipment.repositories import (
    JsonEmployeeRepository,
    JsonlEscalationRepository,
    JsonPolicyRepository,
)
from it_equipment.tools import EquipmentTools

#: The repository's mock data (REQUIREMENTS 2.3, 2.4 and 3).
DATA_DIR = Path(__file__).resolve().parents[1] / "data"

#: "Today" for every test, as REQUIREMENTS fixes it.
TODAY = date(2026, 11, 24)

#: The fixed "now" stamped on escalation tickets in tests.
NOW = datetime(2026, 11, 24, 9, 30, tzinfo=UTC)


@pytest.fixture
def anyio_backend() -> str:
    """Run ``@pytest.mark.anyio`` tests on asyncio only (the MCP SDK's default backend)."""
    return "asyncio"


@pytest.fixture
def mock_data_dir() -> Path:
    """The folder that holds the mock data files."""
    return DATA_DIR


@pytest.fixture
def employee_repository() -> JsonEmployeeRepository:
    """The mock employees from ``data/employees.json``."""
    return JsonEmployeeRepository(DATA_DIR / "employees.json")


@pytest.fixture
def policy_repository() -> JsonPolicyRepository:
    """The policy table from ``data/policies.json``."""
    return JsonPolicyRepository(DATA_DIR / "policies.json")


@pytest.fixture
def escalation_repository(tmp_path) -> JsonlEscalationRepository:
    """An empty escalation store in a temporary folder, so tests never write to data/."""
    return JsonlEscalationRepository(tmp_path / "escalations.jsonl")


@pytest.fixture
def tools(employee_repository, policy_repository, escalation_repository) -> EquipmentTools:
    """Tools over the mock data; today is 2026-11-24 and tickets are stamped with ``NOW``."""
    return EquipmentTools(
        employee_repository,
        policy_repository,
        escalation_repository,
        clock=lambda: TODAY,
        now=lambda: NOW,
    )
