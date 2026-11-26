"""Unit tests for the JSON repositories: employees, policies and escalation tickets."""

import json
import threading
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from it_equipment.repositories import (
    JsonEmployeeRepository,
    JsonlEscalationRepository,
    JsonPolicyRepository,
)


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


def test_mock_data_uses_only_roles_and_items_from_the_policy_table(
    mock_data_dir, policy_repository
):
    """The files are validated one by one at startup, so this test checks them together."""
    employees = json.loads((mock_data_dir / "employees.json").read_text())

    roles = {employee["role"] for employee in employees}
    items = {unit["item"] for employee in employees for unit in employee.get("equipment", [])}
    assert [role for role in roles if policy_repository.limits_for(role) is None] == []
    assert items <= set(policy_repository.catalog())


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
        {"employee_id": "E\u0661\u0662\u0663"},
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


# ---- escalations ----

CREATED = datetime(2026, 11, 24, 9, 30, tzinfo=UTC)


def test_missing_escalation_file_means_no_tickets(tmp_path):
    repository = JsonlEscalationRepository(tmp_path / "escalations.jsonl")

    assert repository.find_open("E004", "anything") is None


def test_ticket_ids_continue_from_an_existing_file(tmp_path):
    path = tmp_path / "escalations.jsonl"
    JsonlEscalationRepository(path).find_or_create("E001", "first", "UNKNOWN_ITEM: desk", CREATED)

    reopened = JsonlEscalationRepository(path)
    ticket, created = reopened.find_or_create("E002", "second", "UNKNOWN_ITEM: chair", CREATED)

    assert (ticket.ticket_id, created) == ("ESC-000002", True)
    assert reopened.find_open("E001", "first").ticket_id == "ESC-000001"


def test_identical_open_request_returns_its_ticket_and_writes_nothing(tmp_path):
    path = tmp_path / "escalations.jsonl"
    repository = JsonlEscalationRepository(path)
    first, _ = repository.find_or_create("E001", "Can I get a desk?", "UNKNOWN_ITEM: desk", CREATED)

    again, created = repository.find_or_create("E001", "Can I get a desk?", "other", CREATED)

    assert (again, created) == (first, False)
    assert len(path.read_text().splitlines()) == 1


def test_identical_requests_at_the_same_time_share_one_ticket(tmp_path):
    """The SDK runs tools in worker threads, so two identical calls can arrive together."""
    repository = JsonlEscalationRepository(tmp_path / "escalations.jsonl")
    start = threading.Barrier(8)
    tickets = []

    def flag() -> None:
        start.wait()
        ticket, _ = repository.find_or_create("E004", "same", "EXCEPTION_REQUESTED: x", CREATED)
        tickets.append(ticket.ticket_id)

    threads = [threading.Thread(target=flag) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert tickets == ["ESC-000001"] * 8


def test_find_open_matches_employee_and_exact_request_only(tmp_path):
    repository = JsonlEscalationRepository(tmp_path / "escalations.jsonl")
    repository.find_or_create("E001", "Can I get a desk?", "UNKNOWN_ITEM: desk", CREATED)

    assert repository.find_open("E002", "Can I get a desk?") is None
    assert repository.find_open("E001", "can i get a desk?") is None


def test_corrupt_escalation_line_is_reported(tmp_path):
    path = tmp_path / "escalations.jsonl"
    path.write_text('{"ticket_id": "not-a-ticket"}\n')

    with pytest.raises(ValidationError):
        JsonlEscalationRepository(path).find_open("E001", "x")
