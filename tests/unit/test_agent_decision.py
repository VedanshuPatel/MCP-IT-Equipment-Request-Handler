"""Unit tests for the decision record and the ``submit_decision`` tool (REQUIREMENTS 6.1)."""

import pytest
from pydantic import ValidationError

from it_equipment.agent.decision import SUBMIT_DECISION_TOOL, Decision

APPROVAL = {
    "employee_id": "E002",
    "item": "laptop",
    "decision": "approve",
    "reason_code": "REFRESH_DUE",
    "response": "Your laptop replacement is approved.",
    "ticket_id": None,
}


def test_valid_decision_is_accepted():
    decision = Decision.model_validate(APPROVAL)

    assert decision.decision == "approve"
    assert decision.ticket_id is None


@pytest.mark.parametrize(
    ("change", "field"),
    [
        ({"decision": "maybe"}, "decision"),
        ({"reason_code": "AGENT_ERROR"}, "reason_code"),
        ({"comment": "extra"}, "comment"),
    ],
    ids=["unknown decision", "code the model may not give", "extra field"],
)
def test_invalid_decision_is_rejected(change, field):
    with pytest.raises(ValidationError, match=field):
        Decision.model_validate({**APPROVAL, **change})


def test_ticket_id_must_be_given_even_when_null():
    without_ticket = {key: value for key, value in APPROVAL.items() if key != "ticket_id"}

    with pytest.raises(ValidationError, match="ticket_id"):
        Decision.model_validate(without_ticket)


def test_submit_decision_tool_takes_a_thought_and_every_decision_field():
    parameters = SUBMIT_DECISION_TOOL.parameters

    assert SUBMIT_DECISION_TOOL.name == "submit_decision"
    assert parameters["required"] == ["thought", *Decision.model_fields]
    assert set(parameters["properties"]) == set(parameters["required"])
    assert parameters["additionalProperties"] is False


def test_submit_decision_tool_offers_only_the_allowed_values():
    properties = SUBMIT_DECISION_TOOL.parameters["properties"]

    assert properties["decision"]["enum"] == ["approve", "deny", "escalate"]
    assert "EXCEPTION_REQUESTED" in properties["reason_code"]["enum"]
    assert "AGENT_ERROR" not in properties["reason_code"]["enum"]
