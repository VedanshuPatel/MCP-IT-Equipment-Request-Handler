"""Business logic behind the MCP tools, as plain Python (Facade pattern).

``EquipmentTools`` holds the dependencies (repositories and a clock) and exposes one
method per MCP tool. It knows nothing about MCP, so every tool is unit-tested by calling
the method directly; ``server.py`` only wraps these methods.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path

from it_equipment import rules
from it_equipment.errors import (
    EmployeeNotFoundError,
    InvalidEmployeeIdError,
    InvalidInputError,
    UnknownRoleError,
)
from it_equipment.models import (
    MAX_REASON_LENGTH,
    MAX_REQUEST_LENGTH,
    EligibilityResult,
    EmployeeInfo,
    EscalationResult,
    ItemLimit,
    PolicyLimits,
)
from it_equipment.repositories import (
    EmployeeRepository,
    EscalationRepository,
    JsonEmployeeRepository,
    JsonlEscalationRepository,
    JsonPolicyRepository,
    PolicyRepository,
)

#: Returns "today". Injected so tests can fix the date (REQUIREMENTS conventions).
Clock = Callable[[], date]

#: Returns the current time in UTC. Injected so tests can fix ticket timestamps.
Now = Callable[[], datetime]

#: Employee ID used for escalations when the request contains none (REQUIREMENTS 4.4).
UNKNOWN_EMPLOYEE = "UNKNOWN"


def _utc_now() -> datetime:
    return datetime.now(UTC)


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
        policies: Where the policy table comes from.
        escalations: Where escalation tickets are stored.
        clock: Returns today's date. Defaults to the real date.
        now: Returns the current UTC time, for ticket timestamps. Defaults to the real time.
    """

    def __init__(
        self,
        employees: EmployeeRepository,
        policies: PolicyRepository,
        escalations: EscalationRepository,
        clock: Clock = date.today,
        now: Now = _utc_now,
    ) -> None:
        """Store the dependencies."""
        self._employees = employees
        self._policies = policies
        self._escalations = escalations
        self._clock = clock
        self._now = now

    @classmethod
    def from_data_dir(cls, data_dir: Path, clock: Clock = date.today) -> EquipmentTools:
        """Build the tools from the JSON files in ``data_dir``.

        Args:
            data_dir: Folder that holds ``employees.json`` and ``policies.json``; escalations
                are written to ``escalations.jsonl`` in the same folder.
            clock: Returns today's date. Defaults to the real date.

        Returns:
            Tools backed by the JSON repositories.
        """
        return cls(
            JsonEmployeeRepository(data_dir / "employees.json"),
            JsonPolicyRepository(data_dir / "policies.json"),
            JsonlEscalationRepository(data_dir / "escalations.jsonl"),
            clock,
        )

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

    def get_policy_limits(self, role: str) -> PolicyLimits:
        """Return what a role is eligible for and how often (REQUIREMENTS 4.2).

        Args:
            role: The role to look up; case and surrounding spaces are ignored.

        Returns:
            One entry per catalog item, in catalog order.

        Raises:
            UnknownRoleError: If the role is not in the policy table.
        """
        normalized = role.strip().lower()
        limits = self._policies.limits_for(normalized)
        if limits is None:
            raise UnknownRoleError(f"no policy for role {role!r}")
        items = [
            ItemLimit(
                item=item,
                max_quantity=limits[item].max_quantity,
                replacement_years=limits[item].replacement_years,
                eligible=limits[item].max_quantity > 0,
            )
            for item in self._policies.catalog()
        ]
        return PolicyLimits(role=normalized, items=items)

    def check_request_eligibility(self, employee_id: str, item: str) -> EligibilityResult:
        """Decide whether the employee may receive one unit of the item today.

        Applies rules E1 to E6 (REQUIREMENTS section 5). An unknown employee or item is not
        an error: it returns ``needs_review`` so the agent escalates.

        Args:
            employee_id: The employee; case and surrounding spaces are ignored.
            item: The catalog item; case and surrounding spaces are ignored.

        Returns:
            The decision, with the rule's reason code and the facts behind it.

        Raises:
            InvalidEmployeeIdError: If the ID is malformed.
            InvalidInputError: If the item is empty.
            UnknownRoleError: If the employee's role is missing from the policy table
                (a data error).
        """
        normalized_id = normalize_employee_id(employee_id)
        normalized_item = item.strip().lower()
        if not normalized_item:
            raise InvalidInputError("item must not be empty")
        employee = self._employees.get(normalized_id)
        limits = None
        if employee is not None:
            limits = self._policies.limits_for(employee.role)
            if limits is None:
                raise UnknownRoleError(f"no policy for role {employee.role!r}")
        context = rules.EligibilityContext(
            employee_id=normalized_id,
            item=normalized_item,
            employee=employee,
            limits=limits,
            catalog=self._policies.catalog(),
            today=self._clock(),
        )
        return rules.evaluate(context)

    def flag_for_human_review(
        self, employee_id: str, request: str, reason: str
    ) -> EscalationResult:
        """Escalate a request to a human reviewer by creating a ticket (REQUIREMENTS 4.4).

        This is the only tool with a side effect. Flagging the same employee and identical
        request text again returns the existing open ticket instead of creating a second one.

        Args:
            employee_id: A well-formed ID (it may be unknown), or ``UNKNOWN`` when the
                request contains none.
            request: The original request text, 1 to 2,000 characters. Stored unchanged.
            reason: Why it needs a human, 1 to 500 characters, normally starting with an
                escalation code such as ``EXCEPTION_REQUESTED:``.

        Returns:
            The ticket ID, its status and whether it already existed.

        Raises:
            InvalidEmployeeIdError: If the ID is neither well-formed nor ``UNKNOWN``.
            InvalidInputError: If the request or reason is empty or too long.
        """
        normalized_id = employee_id.strip().upper()
        if normalized_id != UNKNOWN_EMPLOYEE:
            normalized_id = normalize_employee_id(employee_id)
        if not request.strip() or len(request) > MAX_REQUEST_LENGTH:
            raise InvalidInputError(f"request must be 1 to {MAX_REQUEST_LENGTH} characters")
        reason = reason.strip()
        if not reason or len(reason) > MAX_REASON_LENGTH:
            raise InvalidInputError(f"reason must be 1 to {MAX_REASON_LENGTH} characters")

        existing = self._escalations.find_open(normalized_id, request)
        if existing is not None:
            return EscalationResult(ticket_id=existing.ticket_id, status="open", duplicate=True)
        ticket = self._escalations.create(normalized_id, request, reason, self._now())
        return EscalationResult(ticket_id=ticket.ticket_id, status="open", duplicate=False)
