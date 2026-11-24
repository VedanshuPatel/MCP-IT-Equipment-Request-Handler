"""Unit tests for the eligibility rule chain itself."""

from datetime import date

import pytest

from it_equipment.rules import DEFAULT_RULES, EligibilityContext, add_years, evaluate


@pytest.mark.parametrize(
    ("start", "years", "expected"),
    [
        (date(2023, 1, 10), 4, date(2027, 1, 10)),
        (date(2024, 2, 29), 2, date(2026, 2, 28)),  # non-leap target year
        (date(2024, 2, 29), 4, date(2028, 2, 29)),  # leap target year
    ],
)
def test_add_years(start, years, expected):
    assert add_years(start, years) == expected


def _context(employee_id="E999", item="desk") -> EligibilityContext:
    return EligibilityContext(
        employee_id=employee_id,
        item=item,
        employee=None,
        limits=None,
        catalog=("laptop",),
        today=date(2026, 11, 24),
    )


def test_rules_are_applied_in_order():
    """Unknown employee *and* unknown item: E1 runs first, so the employee wins."""
    assert evaluate(_context()).reason_code == "EMPLOYEE_NOT_FOUND"


def test_default_rules_follow_the_requirements_order():
    names = [type(rule).__name__ for rule in DEFAULT_RULES]

    assert names == [
        "EmployeeMustExist",
        "ItemMustBeInCatalog",
        "RoleMustBeEligible",
        "BelowLimit",
        "RefreshDue",
        "LimitReached",
    ]


def test_no_deciding_rule_is_an_error():
    with pytest.raises(LookupError, match="no eligibility rule decided"):
        evaluate(_context(), rules=[])
