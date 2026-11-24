"""Data access for the mock IT system (Repository pattern).

The tools depend only on the ``EmployeeRepository`` protocol. Today the data comes from
JSON files; moving to a database or an HR API means adding one class here, without
changing the tools.
"""

from pathlib import Path
from typing import Protocol

from pydantic import TypeAdapter

from it_equipment.models import Employee

_EMPLOYEE_LIST = TypeAdapter(list[Employee])


class EmployeeRepository(Protocol):
    """Read access to employee records."""

    def get(self, employee_id: str) -> Employee | None:
        """Return the employee with this normalized ID, or ``None`` if there is none."""
        ...


class JsonEmployeeRepository:
    """Employee records loaded from a JSON file that holds a list of employees.

    The whole file is validated once, at construction, so bad data fails at startup
    instead of in the middle of a request.

    Args:
        path: Path to the JSON file, for example ``data/employees.json``.

    Raises:
        FileNotFoundError: If the file does not exist.
        pydantic.ValidationError: If a record does not match the ``Employee`` model.
        ValueError: If two records share an employee ID.
    """

    def __init__(self, path: Path) -> None:
        """Load and validate every record in ``path``."""
        self._employees = self._load(path)

    @staticmethod
    def _load(path: Path) -> dict[str, Employee]:
        employees: dict[str, Employee] = {}
        for employee in _EMPLOYEE_LIST.validate_json(path.read_bytes()):
            if employee.employee_id in employees:
                raise ValueError(f"Duplicate employee ID {employee.employee_id} in {path}")
            employees[employee.employee_id] = employee
        return employees

    def get(self, employee_id: str) -> Employee | None:
        """Return the employee with this normalized ID, or ``None`` if there is none."""
        return self._employees.get(employee_id)
