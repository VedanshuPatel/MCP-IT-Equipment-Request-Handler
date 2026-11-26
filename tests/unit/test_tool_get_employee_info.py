"""Unit tests for ``get_employee_info``, called directly (SCOPE Part 3).

Covers acceptance criteria AC-01 to AC-04 in docs/REQUIREMENTS.md.
"""

import shutil
from datetime import date

import pytest

from it_equipment.errors import EmployeeNotFoundError, InvalidEmployeeIdError
from it_equipment.tools import EquipmentTools, completed_years, normalize_employee_id

# AC-01: the example in REQUIREMENTS 4.1, as JSON.
E002_EXPECTED = {
    "employee_id": "E002",
    "name": "Priya Shah",
    "role": "manager",
    "hire_date": "2019-07-01",
    "tenure_years": 7,
    "equipment": [
        {"item": "laptop", "issued_on": "2024-05-20"},
        {"item": "monitor", "issued_on": "2024-05-20"},
    ],
}


def test_returns_role_tenure_and_equipment(tools):
    """AC-01."""
    assert tools.get_employee_info("E002").model_dump(mode="json") == E002_EXPECTED


@pytest.mark.parametrize("raw", [" e002 ", "e002", "E002\n"])
def test_id_case_and_surrounding_spaces_are_ignored(tools, raw):
    """AC-02."""
    assert tools.get_employee_info(raw).model_dump(mode="json") == E002_EXPECTED


def test_unknown_employee_raises_not_found(tools):
    """AC-03."""
    with pytest.raises(EmployeeNotFoundError, match=r"^EMPLOYEE_NOT_FOUND: .*E999"):
        tools.get_employee_info("E999")


@pytest.mark.parametrize(
    "raw", ["12", "", "   ", "E12", "E0001", "X002", "E00A", "E\u0661\u0662\u0663"]
)
def test_malformed_id_raises_invalid(tools, raw):
    """AC-04."""
    with pytest.raises(InvalidEmployeeIdError, match=r"^INVALID_EMPLOYEE_ID: "):
        tools.get_employee_info(raw)


def test_employee_without_equipment_has_empty_list(tools):
    info = tools.get_employee_info("E006")

    assert info.equipment == []
    assert info.tenure_years == 0


def test_multiple_units_of_one_item_are_all_listed(tools):
    items = [unit.item for unit in tools.get_employee_info("E004").equipment]

    assert items == ["laptop", "monitor", "monitor", "keyboard"]


@pytest.mark.parametrize(
    ("today", "expected"),
    [
        (date(2027, 6, 30), 7),  # day before the anniversary
        (date(2027, 7, 1), 8),  # on the anniversary
    ],
)
def test_tenure_counts_completed_years_only(
    employee_repository, policy_repository, escalation_repository, today, expected
):
    tools = EquipmentTools(
        employee_repository, policy_repository, escalation_repository, clock=lambda: today
    )

    assert tools.get_employee_info("E002").tenure_years == expected


def test_completed_years_is_never_negative():
    assert completed_years(date(2030, 1, 1), date(2026, 11, 24)) == 0


def test_normalize_employee_id_returns_canonical_form():
    assert normalize_employee_id("  e123 ") == "E123"


def test_from_data_dir_reads_employees_json(tmp_path, mock_data_dir):
    shutil.copy(mock_data_dir / "policies.json", tmp_path / "policies.json")
    (tmp_path / "employees.json").write_text(
        '[{"employee_id": "E100", "name": "A B", "role": "standard", "hire_date": "2020-01-01"}]'
    )
    tools = EquipmentTools.from_data_dir(tmp_path, clock=lambda: date(2026, 1, 1))

    assert tools.get_employee_info("E100").tenure_years == 6
