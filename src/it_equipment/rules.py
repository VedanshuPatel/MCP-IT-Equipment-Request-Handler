"""Eligibility rules for ``check_request_eligibility`` (Strategy / chain of rules).

Each rule is a small class that either decides the request or passes (returns ``None``).
``evaluate`` tries the rules in order and the first decision wins, exactly as REQUIREMENTS
section 5 describes rules E1 to E6. A new policy rule is one new class added to the list;
the existing rules do not change.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from it_equipment.models import (
    EligibilityResult,
    EligibilityStatus,
    Employee,
    ItemPolicy,
    ReasonCode,
)


def add_years(start: date, years: int) -> date:
    """Return ``start`` plus whole ``years``; 29 February becomes 28 February if needed.

    Args:
        start: The starting date, for example the date a unit was issued.
        years: Whole years to add.

    Returns:
        The same month and day ``years`` later (REQUIREMENTS section 3, due date).
    """
    try:
        return start.replace(year=start.year + years)
    except ValueError:  # 29 February in a non-leap target year
        return start.replace(year=start.year + years, day=28)


@dataclass(frozen=True, slots=True)
class EligibilityContext:
    """Everything the rules need to decide one request.

    Attributes:
        employee_id: Normalized employee ID.
        item: Normalized item name.
        employee: The employee record, or ``None`` if no employee has the ID.
        limits: The policy per catalog item for the employee's role, or ``None``.
        catalog: The catalog items.
        today: The date to decide for.
    """

    employee_id: str
    item: str
    employee: Employee | None
    limits: dict[str, ItemPolicy] | None
    catalog: tuple[str, ...]
    today: date

    @property
    def policy(self) -> ItemPolicy:
        """The role's policy for the requested item (only valid after E1 and E2 passed)."""
        assert self.limits is not None
        return self.limits[self.item]

    @property
    def role(self) -> str:
        """The employee's role (only valid after E1 passed)."""
        assert self.employee is not None
        return self.employee.role

    @property
    def held_dates(self) -> list[date]:
        """Issue dates of the units of the requested item on file, oldest first (after E1)."""
        assert self.employee is not None
        return sorted(u.issued_on for u in self.employee.equipment if u.item == self.item)

    def result(
        self,
        status: EligibilityStatus,
        reason_code: ReasonCode,
        message: str,
        *,
        held: int | None = None,
        max_quantity: int | None = None,
        next_eligible_date: date | None = None,
    ) -> EligibilityResult:
        """Build a result for this request, filling in the employee ID and item."""
        return EligibilityResult(
            status=status,
            reason_code=reason_code,
            employee_id=self.employee_id,
            item=self.item,
            held=held,
            max_quantity=max_quantity,
            next_eligible_date=next_eligible_date,
            message=message,
        )


class EligibilityRule(Protocol):
    """One rule: decide the request, or return ``None`` to let the next rule decide."""

    def evaluate(self, ctx: EligibilityContext) -> EligibilityResult | None:
        """Return a decision, or ``None`` if this rule does not apply."""
        ...


class EmployeeMustExist:
    """E1: an unknown employee needs human review."""

    def evaluate(self, ctx: EligibilityContext) -> EligibilityResult | None:
        """Decide ``needs_review`` / ``EMPLOYEE_NOT_FOUND`` when the ID is unknown."""
        if ctx.employee is not None:
            return None
        return ctx.result(
            "needs_review", "EMPLOYEE_NOT_FOUND", f"No employee has ID {ctx.employee_id}."
        )


class ItemMustBeInCatalog:
    """E2: an item outside the catalog needs human review."""

    def evaluate(self, ctx: EligibilityContext) -> EligibilityResult | None:
        """Decide ``needs_review`` / ``UNKNOWN_ITEM`` when the item is not in the catalog."""
        if ctx.item in ctx.catalog:
            return None
        catalog = ", ".join(ctx.catalog)
        return ctx.result(
            "needs_review",
            "UNKNOWN_ITEM",
            f"'{ctx.item}' is not in the equipment catalog ({catalog}).",
        )


class RoleMustBeEligible:
    """E3: a role whose maximum for the item is 0 is not eligible."""

    def evaluate(self, ctx: EligibilityContext) -> EligibilityResult | None:
        """Decide ``not_eligible`` / ``ROLE_NOT_ELIGIBLE`` when the maximum is 0."""
        if ctx.policy.max_quantity > 0:
            return None
        return ctx.result(
            "not_eligible",
            "ROLE_NOT_ELIGIBLE",
            f"The {ctx.role} role is not eligible for a {ctx.item}.",
            held=len(ctx.held_dates),
            max_quantity=0,
        )


class BelowLimit:
    """E4: fewer units than the maximum means one more can be issued."""

    def evaluate(self, ctx: EligibilityContext) -> EligibilityResult | None:
        """Decide ``eligible`` / ``NEW_ALLOCATION`` when held is below the maximum."""
        held, maximum = len(ctx.held_dates), ctx.policy.max_quantity
        if held >= maximum:
            return None
        return ctx.result(
            "eligible",
            "NEW_ALLOCATION",
            f"{ctx.employee_id} holds {held} of the {maximum} {ctx.item} units allowed for "
            f"the {ctx.role} role, so one more can be issued.",
            held=held,
            max_quantity=maximum,
        )


def _earliest_due_date(ctx: EligibilityContext) -> date:
    """The earliest date on which one of the held units becomes due for replacement."""
    years = ctx.policy.replacement_years
    assert years is not None  # guaranteed by the policy model when max_quantity > 0
    return add_years(ctx.held_dates[0], years)


class RefreshDue:
    """E5: at the maximum, but a unit is due, so it can be replaced."""

    def evaluate(self, ctx: EligibilityContext) -> EligibilityResult | None:
        """Decide ``eligible`` / ``REFRESH_DUE`` when the oldest unit is due."""
        due = _earliest_due_date(ctx)
        if ctx.today < due:
            return None
        return ctx.result(
            "eligible",
            "REFRESH_DUE",
            f"{ctx.employee_id} has the maximum of {ctx.policy.max_quantity} {ctx.item} "
            f"units, and the oldest became due for replacement on {due.isoformat()}.",
            held=len(ctx.held_dates),
            max_quantity=ctx.policy.max_quantity,
        )


class LimitReached:
    """E6: at the maximum and nothing is due; always decides, so it must be last."""

    def evaluate(self, ctx: EligibilityContext) -> EligibilityResult | None:
        """Decide ``not_eligible`` / ``LIMIT_REACHED`` with the next eligible date."""
        due = _earliest_due_date(ctx)
        return ctx.result(
            "not_eligible",
            "LIMIT_REACHED",
            f"{ctx.employee_id} already has the maximum of {ctx.policy.max_quantity} "
            f"{ctx.item} units for the {ctx.role} role, and none is due for replacement "
            f"until {due.isoformat()}.",
            held=len(ctx.held_dates),
            max_quantity=ctx.policy.max_quantity,
            next_eligible_date=due,
        )


#: Rules E1 to E6, in the order REQUIREMENTS section 5 applies them.
DEFAULT_RULES: tuple[EligibilityRule, ...] = (
    EmployeeMustExist(),
    ItemMustBeInCatalog(),
    RoleMustBeEligible(),
    BelowLimit(),
    RefreshDue(),
    LimitReached(),
)


def evaluate(
    ctx: EligibilityContext, rules: Sequence[EligibilityRule] = DEFAULT_RULES
) -> EligibilityResult:
    """Apply the rules in order and return the first decision.

    Args:
        ctx: The request to decide.
        rules: The rules to apply, in order. Defaults to E1 to E6.

    Returns:
        The decision of the first rule that applies.

    Raises:
        LookupError: If no rule decides (the default rules always decide).
    """
    for rule in rules:
        decision = rule.evaluate(ctx)
        if decision is not None:
            return decision
    raise LookupError(f"no eligibility rule decided {ctx.employee_id}/{ctx.item}")
