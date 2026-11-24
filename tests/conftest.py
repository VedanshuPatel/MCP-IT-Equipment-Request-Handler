"""Shared pytest fixtures."""

from datetime import date
from pathlib import Path

import pytest

from it_equipment.repositories import JsonEmployeeRepository
from it_equipment.tools import EquipmentTools

#: The repository's mock data (REQUIREMENTS 2.3 and 2.4).
DATA_DIR = Path(__file__).resolve().parents[1] / "data"

#: "Today" for every test, as REQUIREMENTS fixes it.
TODAY = date(2026, 11, 24)


@pytest.fixture
def anyio_backend() -> str:
    """Run ``@pytest.mark.anyio`` tests on asyncio only (the MCP SDK's default backend)."""
    return "asyncio"


@pytest.fixture
def employee_repository() -> JsonEmployeeRepository:
    """The mock employees from ``data/employees.json``."""
    return JsonEmployeeRepository(DATA_DIR / "employees.json")


@pytest.fixture
def tools(employee_repository) -> EquipmentTools:
    """Tool implementations over the mock data, with today fixed to 2026-11-24."""
    return EquipmentTools(employee_repository, clock=lambda: TODAY)
