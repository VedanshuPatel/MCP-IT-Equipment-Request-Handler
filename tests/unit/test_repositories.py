"""Unit tests for loading employee records from JSON."""

import json

import pytest
from pydantic import ValidationError

from it_equipment.repositories import JsonEmployeeRepository


def _write(tmp_path, records):
    path = tmp_path / "employees.json"
    path.write_text(json.dumps(records))
    return path


VALID = {
    "employee_id": "E100",
    "name": "Test Person",
    "role": "standard",
    "hire_date": "2020-01-01",
}


def test_mock_data_has_the_six_employees_from_the_requirements(employee_repository):
    roles = {f"E00{n}": employee_repository.get(f"E00{n}").role for n in range(1, 7)}

    assert roles == {
        "E001": "standard",
        "E002": "manager",
        "E003": "standard",
        "E004": "engineer",
        "E005": "contractor",
        "E006": "engineer",
    }


def test_mock_data_lists_each_unit_separately(employee_repository):
    items = [unit.item for unit in employee_repository.get("E004").equipment]

    assert items.count("monitor") == 2


def test_unknown_id_returns_none(employee_repository):
    assert employee_repository.get("E999") is None


def test_equipment_defaults_to_empty(tmp_path):
    repository = JsonEmployeeRepository(_write(tmp_path, [VALID]))

    assert repository.get("E100").equipment == ()


def test_duplicate_ids_are_rejected(tmp_path):
    with pytest.raises(ValueError, match="Duplicate employee ID E100"):
        JsonEmployeeRepository(_write(tmp_path, [VALID, VALID]))


@pytest.mark.parametrize(
    "bad_field",
    [
        {"employee_id": "100"},
        {"hire_date": "not-a-date"},
        {"name": ""},
        {"unexpected": "field"},
    ],
)
def test_invalid_records_are_rejected(tmp_path, bad_field):
    with pytest.raises(ValidationError):
        JsonEmployeeRepository(_write(tmp_path, [{**VALID, **bad_field}]))


def test_missing_file_is_reported(tmp_path):
    with pytest.raises(FileNotFoundError):
        JsonEmployeeRepository(tmp_path / "missing.json")
