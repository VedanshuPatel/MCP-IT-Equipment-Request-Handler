"""Shared pytest fixtures."""

from datetime import date
from pathlib import Path

import pytest

from it_equipment.repositories import JsonEmployeeRepository, JsonPolicyRepository
from it_equipment.tools import EquipmentTools

#: The repository's mock data (REQUIREMENTS 2.3, 2.4 and 3).
DATA_DIR = Path(__file__).resolve().parents[1] / "data"

#: "Today" for every test, as REQUIREMENTS fixes it.
TODAY = date(2026, 11, 24)


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
def tools(employee_repository, policy_repository) -> EquipmentTools:
    """Tool implementations over the mock data, with today fixed to 2026-11-24."""
    return EquipmentTools(employee_repository, policy_repository, clock=lambda: TODAY)
