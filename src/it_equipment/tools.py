"""Business logic behind the MCP tools, as plain Python (Facade pattern).

``EquipmentTools`` holds the dependencies (repositories and a clock) and exposes one
method per MCP tool. It knows nothing about MCP, so every tool is unit-tested by calling
the method directly; ``server.py`` only wraps these methods.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import date
from pathlib import Path

from it_equipment.errors import EmployeeNotFoundError, InvalidEmployeeIdError
from it_equipment.models import EmployeeInfo
from it_equipment.repositories import EmployeeRepository, JsonEmployeeRepository

#: Returns "today". Injected so tests can fix the date (REQUIREMENTS conventions).
Clock = Callable[[], date]

_EMPLOYEE_ID = re.compile(r"E\d{3}")


def normalize_employee_id(raw: str) -> str:
    """Trim and upper-case an employee ID, then check its format.

    Args:
        raw: The ID as received, for example ``" e002 "``.

    Returns:
        The normalized ID, for example ``"E002"``.

    Raises:
        InvalidEmployeeIdError: If the result is not ``E`` followed by exactly 3 digits.
    """
    candidate = raw.strip().upper()
    if not _EMPLOYEE_ID.fullmatch(candidate):
        raise InvalidEmployeeIdError(f"expected 'E' followed by 3 digits, got {raw!r}")
    return candidate


def completed_years(start: date, today: date) -> int:
    """Return the number of whole years from ``start`` to ``today`` (never negative)."""
    years = today.year - start.year
    if (today.month, today.day) < (start.month, start.day):
        years -= 1
    return max(years, 0)


class EquipmentTools:
    """The tool implementations, with their dependencies injected.

    Args:
        employees: Where employee records come from.
        clock: Returns today's date. Defaults to the real date.
    """

    def __init__(self, employees: EmployeeRepository, clock: Clock = date.today) -> None:
        """Store the dependencies."""
        self._employees = employees
        self._clock = clock

    @classmethod
    def from_data_dir(cls, data_dir: Path, clock: Clock = date.today) -> EquipmentTools:
        """Build the tools from the JSON files in ``data_dir``.

        Args:
            data_dir: Folder that holds ``employees.json``.
            clock: Returns today's date. Defaults to the real date.

        Returns:
            Tools backed by the JSON repositories.
        """
        return cls(JsonEmployeeRepository(data_dir / "employees.json"), clock)

    def get_employee_info(self, employee_id: str) -> EmployeeInfo:
        """Return the employee's role, tenure and current equipment (REQUIREMENTS 4.1).

        Args:
            employee_id: The ID to look up; case and surrounding spaces are ignored.

        Returns:
            The employee's profile, with tenure computed for today.

        Raises:
            InvalidEmployeeIdError: If the ID is malformed.
            EmployeeNotFoundError: If no employee has this ID.
        """
        normalized = normalize_employee_id(employee_id)
        employee = self._employees.get(normalized)
        if employee is None:
            raise EmployeeNotFoundError(f"no employee with ID {normalized}")
        return EmployeeInfo(
            employee_id=employee.employee_id,
            name=employee.name,
            role=employee.role,
            hire_date=employee.hire_date,
            tenure_years=completed_years(employee.hire_date, self._clock()),
            equipment=list(employee.equipment),
        )
