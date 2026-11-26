"""Guardrails (REQUIREMENTS 9): deterministic checks around the model.

- Input (G1 to G3) run before any model call. A failure escalates at once.
- Step (G5, G7) run on every tool call. A failure becomes an error observation, so the model
  can choose again.
- Output (G8 to G11) check the drafted decision against the decision table, the tools' results
  in this run and the request. A failure escalates.

G4 (one retry after an invalid reply) and G6 (the step limit) are enforced by the ReAct loop.
Every check is plain code over the request and the recorded steps; none asks the model.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Sequence
from dataclasses import dataclass

from it_equipment.agent.decision import AgentReasonCode, SubmittedDecision
from it_equipment.agent.llm import ToolCall
from it_equipment.agent.trace import Step

#: The longest request the agent accepts (G1), the same limit as the escalation store's.
MAX_REQUEST_LENGTH = 2000

#: An employee ID anywhere in the request (G2): ``E`` and 3 ASCII digits, any case.
EMPLOYEE_ID = re.compile(r"\bE[0-9]{3}\b", re.IGNORECASE)

#: Phrases that mark a prompt-injection attempt (G3), matched ignoring case.
INJECTION_PHRASES = (
    "ignore previous instructions",
    "ignore all previous",
    "disregard the rules",
    "system prompt",
    "you are now",
    "auto-approve",
)

#: The tool whose second call G7 blocks.
FLAG_FOR_HUMAN_REVIEW = "flag_for_human_review"

#: The tool whose results G8 and G9 rely on.
CHECK_REQUEST_ELIGIBILITY = "check_request_eligibility"

#: The codes the model may escalate with (REQUIREMENTS 6.3); the others approve or deny.
ESCALATION_CODES = {
    "EXCEPTION_REQUESTED",
    "UNKNOWN_ITEM",
    "EMPLOYEE_NOT_FOUND",
    "AMBIGUOUS_REQUEST",
}


@dataclass(frozen=True, slots=True)
class Violation:
    """A guardrail that blocked a request or a draft decision.

    Attributes:
        guardrail: Which rule, for example ``"G8"``.
        code: The escalation code to file (REQUIREMENTS 6.3).
        message: What was wrong, for the ticket and the trace.
    """

    guardrail: str
    code: AgentReasonCode
    message: str

    def __str__(self) -> str:
        """The violation as one line, for example ``"G2: the request has no employee ID"``."""
        return f"{self.guardrail}: {self.message}"


def check_input(request: str) -> Violation | None:
    """Run G1 to G3 on a request before the model sees it.

    Args:
        request: The employee's request, unchanged.

    Returns:
        The first failed check, or None if the request may go to the model.
    """
    if not request.strip():
        return Violation("G1", "GUARDRAIL_TRIGGERED", "the request is empty")
    if len(request) > MAX_REQUEST_LENGTH:
        return Violation(
            "G1",
            "GUARDRAIL_TRIGGERED",
            f"the request is longer than {MAX_REQUEST_LENGTH} characters",
        )
    if not EMPLOYEE_ID.search(request):
        return Violation("G2", "MISSING_EMPLOYEE_ID", "the request has no employee ID")
    lowered = request.lower()
    for phrase in INJECTION_PHRASES:
        if phrase in lowered:
            return Violation("G3", "GUARDRAIL_TRIGGERED", f"the request contains {phrase!r}")
    return None


def employee_id_in(request: str) -> str:
    """Return the first employee ID in the request, upper-cased, or ``UNKNOWN``."""
    match = EMPLOYEE_ID.search(request)
    return match.group().upper() if match else "UNKNOWN"


def filed_ticket(steps: Sequence[Step]) -> str | None:
    """Return the ticket ``flag_for_human_review`` filed in this run, if any."""
    for step in steps:
        if step.call.tool == FLAG_FOR_HUMAN_REVIEW and step.observation.ok:
            return (step.observation.data or {}).get("ticket_id")
    return None


def check_step(call: ToolCall, allowed: Collection[str], steps: Sequence[Step]) -> str | None:
    """Run G5 and G7 on a tool call before it reaches the server.

    Args:
        call: The model's call.
        allowed: The names of the tools the model was offered.
        steps: The steps so far in this run.

    Returns:
        An error message for the model, or None if the call may run.
    """
    if call.tool not in allowed:
        return f"G5: {call.tool!r} is not an available tool. Use one of: {', '.join(allowed)}."
    ticket = filed_ticket(steps)
    if call.tool == FLAG_FOR_HUMAN_REVIEW and ticket:
        return f"G7: this request is already escalated as {ticket}. Submit that ticket_id."
    return None


def _eligibility_results(steps: Sequence[Step], employee_id: str, item: str) -> set[tuple]:
    """The (status, reason code) pairs check_request_eligibility returned in this run."""
    results = set()
    for step in steps:
        result = step.observation.data or {}
        if (
            step.call.tool == CHECK_REQUEST_ELIGIBILITY
            and result.get("employee_id") == employee_id
            and result.get("item") == item
        ):
            results.add((result.get("status"), result.get("reason_code")))
    return results


def check_output(
    decision: SubmittedDecision, request: str, steps: Sequence[Step]
) -> Violation | None:
    """Run G8 to G11: the draft must follow the decision table and rest on this run's results.

    Args:
        decision: The model's draft decision.
        request: The employee's request, which names who is asking.
        steps: The steps of this run.

    Returns:
        The failed check, or None if the decision is backed by the recorded results.
    """
    employee_id = decision.employee_id.strip().upper()
    requester = employee_id_in(request)
    if employee_id != requester:
        message = f"the decision is for {employee_id}, but the request is from {requester}"
        return Violation("G11", "GUARDRAIL_TRIGGERED", message)

    item = decision.item.strip().lower()
    code = decision.reason_code
    results = _eligibility_results(steps, employee_id, item)
    subject = f"{employee_id} and {item!r}"
    if decision.decision == "approve" and ("eligible", code) not in results:
        message = (
            f"approve with {code} without a matching eligible result for {subject} in this run"
        )
        return Violation("G8", "GUARDRAIL_TRIGGERED", message)
    if decision.decision == "deny" and ("not_eligible", code) not in results:
        message = (
            f"deny with {code} without a matching not_eligible result for {subject} in this run"
        )
        return Violation("G9", "GUARDRAIL_TRIGGERED", message)

    ticket = filed_ticket(steps)
    if decision.decision != "escalate":
        if ticket is None and not decision.ticket_id:  # a blank ticket_id means none
            return None
        message = (
            f"{decision.decision} with ticket {decision.ticket_id!r}, but this run filed "
            f"{ticket!r}; only escalate has a ticket"
        )
        return Violation("G10", "GUARDRAIL_TRIGGERED", message)
    if ticket is None or decision.ticket_id != ticket:
        message = f"escalate with ticket {decision.ticket_id!r}, but this run filed {ticket!r}"
        return Violation("G10", "GUARDRAIL_TRIGGERED", message)
    if code not in ESCALATION_CODES:
        message = f"escalate with {code}, which is not an escalation code"
        return Violation("G10", "GUARDRAIL_TRIGGERED", message)
    return None
