"""Data access for the mock IT system (Repository pattern).

The tools depend only on the ``EmployeeRepository`` and ``PolicyRepository`` protocols.
Today the data comes from JSON files; moving to a database or an HR API means adding one
class here, without changing the tools.
"""

from pathlib import Path
from typing import Protocol

from pydantic import TypeAdapter

from it_equipment.models import Employee, ItemPolicy, PolicyTable

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


class PolicyRepository(Protocol):
    """Read access to the policy table."""

    def catalog(self) -> tuple[str, ...]:
        """Return the catalog items, in their defined order."""
        ...

    def limits_for(self, role: str) -> dict[str, ItemPolicy] | None:
        """Return the policy per catalog item for a normalized role, or ``None`` if unknown."""
        ...


class JsonPolicyRepository:
    """The policy table loaded from a JSON file with ``catalog`` and ``roles``.

    The file is validated once, at construction: every role must define a policy for
    exactly the catalog items, and an eligible item needs a replacement interval.

    Args:
        path: Path to the JSON file, for example ``data/policies.json``.

    Raises:
        FileNotFoundError: If the file does not exist.
        pydantic.ValidationError: If the file does not match the ``PolicyTable`` model.
    """

    def __init__(self, path: Path) -> None:
        """Load and validate the policy table in ``path``."""
        self._table = PolicyTable.model_validate_json(path.read_bytes())

    def catalog(self) -> tuple[str, ...]:
        """Return the catalog items, in their defined order."""
        return self._table.catalog

    def limits_for(self, role: str) -> dict[str, ItemPolicy] | None:
        """Return the policy per catalog item for a normalized role, or ``None`` if unknown."""
        return self._table.roles.get(role)
