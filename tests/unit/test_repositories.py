"""Unit tests for loading employee records from JSON."""

import json

import pytest
from pydantic import ValidationError

from it_equipment.repositories import JsonEmployeeRepository, JsonPolicyRepository


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
    employee = JsonEmployeeRepository(_write(tmp_path, [VALID])).get("E100")

    assert employee is not None
    assert employee.equipment == ()


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


# ---- policies ----

POLICY = {
    "catalog": ["laptop", "headset"],
    "roles": {
        "standard": {
            "laptop": {"max_quantity": 1, "replacement_years": 4},
            "headset": {"max_quantity": 0, "replacement_years": None},
        }
    },
}


def _write_policy(tmp_path, table):
    path = tmp_path / "policies.json"
    path.write_text(json.dumps(table))
    return path


def test_mock_policy_has_the_catalog_and_four_roles(policy_repository):
    assert policy_repository.catalog() == ("laptop", "monitor", "headset", "keyboard")
    for role in ("standard", "engineer", "manager", "contractor"):
        assert policy_repository.limits_for(role) is not None


def test_unknown_role_returns_none(policy_repository):
    assert policy_repository.limits_for("intern") is None


def test_valid_policy_file_loads(tmp_path):
    repository = JsonPolicyRepository(_write_policy(tmp_path, POLICY))
    limits = repository.limits_for("standard")

    assert limits is not None
    assert limits["laptop"].replacement_years == 4


@pytest.mark.parametrize(
    "items",
    [
        {"laptop": {"max_quantity": 1, "replacement_years": 4}},
        {
            "laptop": {"max_quantity": 1, "replacement_years": 4},
            "headset": {"max_quantity": 1, "replacement_years": 2},
            "desk": {"max_quantity": 1, "replacement_years": 5},
        },
    ],
    ids=["missing item", "extra item"],
)
def test_role_must_cover_exactly_the_catalog(tmp_path, items):
    table = {**POLICY, "roles": {"standard": items}}

    with pytest.raises(ValidationError, match="must cover the catalog"):
        JsonPolicyRepository(_write_policy(tmp_path, table))


@pytest.mark.parametrize(
    ("policy", "message"),
    [
        ({"max_quantity": 1, "replacement_years": None}, "replacement_years is required"),
        ({"max_quantity": -1, "replacement_years": 2}, "greater than or equal to 0"),
        ({"max_quantity": 1, "replacement_years": 0}, "greater than or equal to 1"),
        ({"max_quantity": 1, "replacement_years": 2, "cost": 9}, "Extra inputs"),
    ],
)
def test_invalid_item_policy_is_rejected(tmp_path, policy, message):
    table = {**POLICY, "roles": {"standard": {"laptop": policy, "headset": policy}}}

    with pytest.raises(ValidationError, match=message):
        JsonPolicyRepository(_write_policy(tmp_path, table))


def test_missing_policy_file_is_reported(tmp_path):
    with pytest.raises(FileNotFoundError):
        JsonPolicyRepository(tmp_path / "missing.json")
