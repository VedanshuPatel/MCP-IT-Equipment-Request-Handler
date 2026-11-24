"""Unit tests for ``flag_for_human_review``, called directly (SCOPE Part 3).

Covers acceptance criteria AC-11 to AC-13 in docs/REQUIREMENTS.md. Every test writes to a
temporary ``escalations.jsonl`` (the ``escalation_repository`` fixture), never to data/.
"""

import json
import re
from datetime import datetime, timedelta

import pytest

from it_equipment.errors import InvalidEmployeeIdError, InvalidInputError
from it_equipment.tools import EquipmentTools

REQUEST = "E004 here. I spilled coffee on my laptop and now it won't boot."
REASON = "EXCEPTION_REQUESTED: laptop damaged by a spill, refresh not due until 2029-03-16"


def _lines(tmp_path):
    path = tmp_path / "escalations.jsonl"
    return path.read_text().splitlines() if path.exists() else []


def test_creates_an_open_ticket_and_appends_one_line(tools, tmp_path):
    """AC-11."""
    result = tools.flag_for_human_review("E004", REQUEST, REASON)

    assert re.fullmatch(r"ESC-\d{6}", result.ticket_id)
    assert (result.status, result.duplicate) == ("open", False)
    assert [json.loads(line) for line in _lines(tmp_path)] == [
        {
            "ticket_id": result.ticket_id,
            "employee_id": "E004",
            "request": REQUEST,
            "reason": REASON,
            "status": "open",
            "created_at": "2026-11-24T09:30:00Z",
        }
    ]


def test_same_employee_and_request_returns_the_existing_ticket(tools, tmp_path):
    """AC-12."""
    first = tools.flag_for_human_review("E004", REQUEST, REASON)
    second = tools.flag_for_human_review("e004", REQUEST, "EXCEPTION_REQUESTED: asked again")

    assert second.ticket_id == first.ticket_id
    assert second.duplicate is True
    assert len(_lines(tmp_path)) == 1


@pytest.mark.parametrize(
    ("request_text", "reason"),
    [
        ("", REASON),
        ("   ", REASON),
        ("x" * 2001, REASON),
        (REQUEST, ""),
        (REQUEST, "   "),
        (REQUEST, "x" * 501),
    ],
    ids=[
        "empty request",
        "blank request",
        "long request",
        "empty reason",
        "blank reason",
        "long reason",
    ],
)
def test_invalid_request_or_reason_writes_nothing(tools, tmp_path, request_text, reason):
    """AC-13."""
    with pytest.raises(InvalidInputError, match=r"^INVALID_INPUT: "):
        tools.flag_for_human_review("E004", request_text, reason)

    assert _lines(tmp_path) == []


def test_limits_are_inclusive(tools):
    result = tools.flag_for_human_review("E004", "x" * 2000, "y" * 500)

    assert result.duplicate is False


def test_ticket_ids_are_sequential(tools):
    ids = [tools.flag_for_human_review("E001", f"request {n}", REASON).ticket_id for n in (1, 2)]

    assert ids == ["ESC-000001", "ESC-000002"]


def test_different_request_from_same_employee_gets_a_new_ticket(tools):
    first = tools.flag_for_human_review("E004", REQUEST, REASON)
    second = tools.flag_for_human_review("E004", REQUEST + " Please hurry.", REASON)

    assert second.ticket_id != first.ticket_id


@pytest.mark.parametrize(("raw", "stored"), [("UNKNOWN", "UNKNOWN"), (" unknown ", "UNKNOWN")])
def test_unknown_employee_placeholder_is_accepted(tools, tmp_path, raw, stored):
    tools.flag_for_human_review(raw, "Can I get a new keyboard?", "MISSING_EMPLOYEE_ID: no ID")

    assert json.loads(_lines(tmp_path)[0])["employee_id"] == stored


def test_well_formed_but_unknown_employee_can_be_escalated(tools):
    """E999 does not exist, which is exactly why it is escalated."""
    result = tools.flag_for_human_review("E999", "I need a headset.", "EMPLOYEE_NOT_FOUND: E999")

    assert result.duplicate is False


def test_malformed_employee_id_is_invalid(tools, tmp_path):
    with pytest.raises(InvalidEmployeeIdError):
        tools.flag_for_human_review("12", REQUEST, REASON)

    assert _lines(tmp_path) == []


def test_reason_is_trimmed_but_request_is_stored_unchanged(tools, tmp_path):
    tools.flag_for_human_review("E004", "  " + REQUEST + "  ", "  " + REASON + "  ")

    record = json.loads(_lines(tmp_path)[0])
    assert record["request"] == "  " + REQUEST + "  "
    assert record["reason"] == REASON


def test_default_clock_stamps_tickets_in_utc(
    employee_repository, policy_repository, escalation_repository, tmp_path
):
    tools = EquipmentTools(employee_repository, policy_repository, escalation_repository)

    tools.flag_for_human_review("E004", REQUEST, REASON)

    created_at = datetime.fromisoformat(json.loads(_lines(tmp_path)[0])["created_at"])
    assert created_at.utcoffset() == timedelta(0)
