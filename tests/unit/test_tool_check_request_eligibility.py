"""Unit tests for ``check_request_eligibility``, called directly (SCOPE Part 3).

Covers acceptance criteria AC-08 to AC-10 in docs/REQUIREMENTS.md.
"""

import json
from datetime import date

import pytest

from it_equipment.errors import InvalidEmployeeIdError, InvalidInputError, UnknownRoleError
from it_equipment.repositories import JsonEmployeeRepository, JsonlEscalationRepository
from it_equipment.tools import EquipmentTools

# REQUIREMENTS 5.1, today = 2026-11-24:
# (employee, item, held, max, status, reason_code, next_eligible_date)
MATRIX = [
    ("E002", "laptop", 1, 1, "eligible", "REFRESH_DUE", None),
    ("E001", "monitor", 1, 1, "eligible", "REFRESH_DUE", None),
    ("E001", "keyboard", 0, 1, "eligible", "NEW_ALLOCATION", None),
    ("E002", "Monitor", 1, 2, "eligible", "NEW_ALLOCATION", None),
    ("E006", "laptop", 0, 1, "eligible", "NEW_ALLOCATION", None),
    ("E003", "monitor", 1, 1, "not_eligible", "LIMIT_REACHED", "2028-11-03"),
    ("E004", "laptop", 1, 1, "not_eligible", "LIMIT_REACHED", "2029-03-16"),
    ("E004", "monitor", 2, 2, "not_eligible", "LIMIT_REACHED", "2027-01-08"),
    ("E001", "laptop", 1, 1, "not_eligible", "LIMIT_REACHED", "2027-01-10"),
    ("E005", "headset", 1, 1, "not_eligible", "LIMIT_REACHED", "2027-08-04"),
    ("E005", "laptop", 0, 0, "not_eligible", "ROLE_NOT_ELIGIBLE", None),
    ("E001", "standing desk", None, None, "needs_review", "UNKNOWN_ITEM", None),
    ("E999", "laptop", None, None, "needs_review", "EMPLOYEE_NOT_FOUND", None),
]


@pytest.mark.parametrize(
    ("employee_id", "item", "held", "maximum", "status", "code", "next_date"),
    MATRIX,
    ids=[f"{row[0]}-{row[1]}" for row in MATRIX],
)
def test_matches_the_requirements_test_matrix(
    tools, employee_id, item, held, maximum, status, code, next_date
):
    """AC-08."""
    result = tools.check_request_eligibility(employee_id, item)

    assert (result.status, result.reason_code) == (status, code)
    assert (result.held, result.max_quantity) == (held, maximum)
    assert result.next_eligible_date == (date.fromisoformat(next_date) if next_date else None)
    assert result.message


def test_refresh_due_allows_a_replacement_not_an_extra_unit(tools):
    """E5: the employee still holds the maximum, so only the due unit can be replaced."""
    result = tools.check_request_eligibility("E001", "monitor")

    assert result.message == (
        "E001 has the maximum of 1 monitor units for the standard role. The oldest became due "
        "for replacement on 2026-01-10, so it can be replaced, but no unit can be added."
    )


@pytest.mark.parametrize(
    ("today", "status", "code"),
    [
        (date(2027, 1, 10), "eligible", "REFRESH_DUE"),  # the due date itself
        (date(2027, 1, 9), "not_eligible", "LIMIT_REACHED"),  # one day before
    ],
)
def test_due_date_boundary(
    employee_repository, policy_repository, escalation_repository, today, status, code
):
    """AC-09: E001's laptop (standard, 4 years, issued 2023-01-10)."""
    tools = EquipmentTools(
        employee_repository, policy_repository, escalation_repository, clock=lambda: today
    )

    result = tools.check_request_eligibility("E001", "laptop")

    assert (result.status, result.reason_code) == (status, code)


def _tools_for(tmp_path, policy_repository, today: date, *, role: str, equipment) -> EquipmentTools:
    """Tools over a one-employee ``employees.json`` (E100) for edge cases the mock data lacks."""
    path = tmp_path / "employees.json"
    record = {
        "employee_id": "E100",
        "name": "Edge Case",
        "role": role,
        "hire_date": "2020-01-01",
        "equipment": [{"item": item, "issued_on": issued_on} for item, issued_on in equipment],
    }
    path.write_text(json.dumps([record]))
    return EquipmentTools(
        JsonEmployeeRepository(path),
        policy_repository,
        JsonlEscalationRepository(tmp_path / "escalations.jsonl"),
        clock=lambda: today,
    )


def test_unit_issued_on_29_february_is_due_on_28_february(tmp_path, policy_repository):
    """AC-09: a headset issued 2024-02-29 (2-year interval) is due 2026-02-28."""
    equipment = [("headset", "2024-02-29")]

    before = _tools_for(
        tmp_path, policy_repository, date(2026, 2, 27), role="standard", equipment=equipment
    )
    on_due_date = _tools_for(
        tmp_path, policy_repository, date(2026, 2, 28), role="standard", equipment=equipment
    )

    assert before.check_request_eligibility("E100", "headset").next_eligible_date == date(
        2026, 2, 28
    )
    assert on_due_date.check_request_eligibility("E100", "headset").reason_code == "REFRESH_DUE"


@pytest.mark.parametrize("item", ["", "   "])
def test_empty_item_is_invalid_input(tools, item):
    """AC-10."""
    with pytest.raises(InvalidInputError, match=r"^INVALID_INPUT: "):
        tools.check_request_eligibility("E002", item)


def test_malformed_employee_id_is_invalid(tools):
    with pytest.raises(InvalidEmployeeIdError):
        tools.check_request_eligibility("12", "laptop")


def test_inputs_are_normalized(tools):
    result = tools.check_request_eligibility(" e002 ", "  LAPTOP ")

    assert (result.employee_id, result.item) == ("E002", "laptop")


def test_oldest_unit_decides_when_several_are_held(tmp_path, policy_repository):
    """Engineer with two monitors: the older one (2023) is due, so a refresh is allowed."""
    tools = _tools_for(
        tmp_path,
        policy_repository,
        date(2026, 11, 24),
        role="engineer",
        equipment=[("monitor", "2026-01-01"), ("monitor", "2023-06-01")],
    )

    assert tools.check_request_eligibility("E100", "monitor").reason_code == "REFRESH_DUE"


def test_role_missing_from_policy_table_is_a_data_error(tmp_path, policy_repository):
    tools = _tools_for(tmp_path, policy_repository, date(2026, 11, 24), role="intern", equipment=[])

    with pytest.raises(UnknownRoleError):
        tools.check_request_eligibility("E100", "laptop")
