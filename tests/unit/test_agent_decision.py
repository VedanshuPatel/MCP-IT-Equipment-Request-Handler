"""Unit tests for the decision records and the ``submit_decision`` tool (REQUIREMENTS 6.1)."""

import pytest
from pydantic import ValidationError

from it_equipment.agent.decision import SUBMIT_DECISION_TOOL, Decision, SubmittedDecision

APPROVAL = {
    "employee_id": "E002",
    "item": "laptop",
    "decision": "approve",
    "reason_code": "REFRESH_DUE",
    "response": "Your laptop replacement is approved.",
    "ticket_id": None,
}


def test_valid_submission_is_accepted():
    decision = SubmittedDecision.model_validate(APPROVAL)

    assert decision.decision == "approve"
    assert decision.ticket_id is None


@pytest.mark.parametrize(
    ("change", "field"),
    [
        ({"decision": "maybe"}, "decision"),
        ({"reason_code": "AGENT_ERROR"}, "reason_code"),
        ({"item": None}, "item"),
        ({"comment": "extra"}, "comment"),
    ],
    ids=["unknown decision", "code only the agent files", "no item", "extra field"],
)
def test_invalid_submission_is_rejected(change, field):
    with pytest.raises(ValidationError, match=field):
        SubmittedDecision.model_validate({**APPROVAL, **change})


def test_ticket_id_must_be_given_even_when_null():
    without_ticket = {key: value for key, value in APPROVAL.items() if key != "ticket_id"}

    with pytest.raises(ValidationError, match="ticket_id"):
        SubmittedDecision.model_validate(without_ticket)


def test_final_record_also_takes_the_agents_codes_and_an_unknown_item():
    """The agent's own escalations use codes the model may not give, often with no item."""
    escalation = Decision.model_validate(
        {
            **APPROVAL,
            "item": None,
            "decision": "escalate",
            "reason_code": "MISSING_EMPLOYEE_ID",
            "ticket_id": "ESC-000001",
        }
    )

    assert escalation.reason_code == "MISSING_EMPLOYEE_ID"
    assert escalation.item is None


def test_a_submission_is_a_final_record():
    assert isinstance(SubmittedDecision.model_validate(APPROVAL), Decision)


def test_submit_decision_tool_takes_a_thought_and_every_decision_field():
    parameters = SUBMIT_DECISION_TOOL.parameters

    assert SUBMIT_DECISION_TOOL.name == "submit_decision"
    assert parameters["required"] == ["thought", *SubmittedDecision.model_fields]
    assert set(parameters["properties"]) == set(parameters["required"])
    assert parameters["additionalProperties"] is False


def test_submit_decision_tool_offers_only_the_models_values():
    properties = SUBMIT_DECISION_TOOL.parameters["properties"]

    assert properties["decision"]["enum"] == ["approve", "deny", "escalate"]
    assert "EXCEPTION_REQUESTED" in properties["reason_code"]["enum"]
    assert "AGENT_ERROR" not in properties["reason_code"]["enum"]
    assert properties["item"]["type"] == "string"
