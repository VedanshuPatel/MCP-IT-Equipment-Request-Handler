"""Data access for the mock IT system (Repository pattern).

The tools depend only on the ``EmployeeRepository``, ``PolicyRepository`` and
``EscalationRepository`` protocols.
Today the data comes from JSON files; moving to a database or an HR API means adding one
class here, without changing the tools.
"""

import threading
from datetime import datetime
from pathlib import Path
from typing import Protocol

from pydantic import TypeAdapter

from it_equipment.models import Employee, EscalationTicket, ItemPolicy, PolicyTable

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


class EscalationRepository(Protocol):
    """Storage for escalation tickets: the only data the tools write."""

    def find_or_create(
        self, employee_id: str, request: str, reason: str, created_at: datetime
    ) -> tuple[EscalationTicket, bool]:
        """Return the open ticket for this employee and exact request, or store a new one.

        Returns:
            The ticket, and True if this call created it.
        """
        ...


class JsonlEscalationRepository:
    """Escalation tickets stored as one JSON object per line (JSON Lines).

    The file is created on the first ticket. Ticket IDs are sequential (``ESC-000001``,
    ``ESC-000002``, ...), based on the number of tickets already stored. One lock covers "look
    for an open ticket, then append a new one", so concurrent calls within one server process
    can neither share a ticket ID nor create two tickets for the same request.

    Args:
        path: Path to the file, for example ``data/escalations.jsonl``.
    """

    def __init__(self, path: Path) -> None:
        """Remember where tickets are stored."""
        self._path = path
        self._lock = threading.Lock()

    def _tickets(self) -> list[EscalationTicket]:
        if not self._path.exists():
            return []
        lines = self._path.read_text(encoding="utf-8").splitlines()
        return [EscalationTicket.model_validate_json(line) for line in lines if line.strip()]

    def find_open(self, employee_id: str, request: str) -> EscalationTicket | None:
        """Return the open ticket for this employee and exact request text, if any."""
        with self._lock:
            return _open_ticket(self._tickets(), employee_id, request)

    def find_or_create(
        self, employee_id: str, request: str, reason: str, created_at: datetime
    ) -> tuple[EscalationTicket, bool]:
        """Return the open ticket for this employee and exact request, or store a new one.

        Returns:
            The ticket, and True if this call created it.
        """
        with self._lock:
            tickets = self._tickets()
            existing = _open_ticket(tickets, employee_id, request)
            if existing is not None:
                return existing, False
            ticket = EscalationTicket(
                ticket_id=f"ESC-{len(tickets) + 1:06d}",
                employee_id=employee_id,
                request=request,
                reason=reason,
                created_at=created_at,
            )
            with self._path.open("a", encoding="utf-8") as file:
                file.write(ticket.model_dump_json() + "\n")
            return ticket, True


def _open_ticket(
    tickets: list[EscalationTicket], employee_id: str, request: str
) -> EscalationTicket | None:
    """The open ticket for this employee and exact request text among ``tickets``, if any."""
    for ticket in tickets:
        if (ticket.employee_id, ticket.request, ticket.status) == (employee_id, request, "open"):
            return ticket
    return None
