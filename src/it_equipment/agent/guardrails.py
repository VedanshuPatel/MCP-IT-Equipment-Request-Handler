"""Guardrails (REQUIREMENTS 9): deterministic checks around the model.

- Input (G1 to G3) run before any model call. A failure escalates at once.
- Step (G5, G7) run on every tool call. A failure becomes an error observation, so the model
  can choose again.
- Output (G8 to G10) check the drafted decision against what the tools returned in this run.
  A failure escalates.

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

#: An employee ID anywhere in the request (G2): ``E`` and 3 digits, any case.
EMPLOYEE_ID = re.compile(r"\bE\d{3}\b", re.IGNORECASE)

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


def check_output(decision: SubmittedDecision, steps: Sequence[Step]) -> Violation | None:
    """Run G8 to G10: the draft decision must rest on what the tools returned in this run.

    Args:
        decision: The model's draft decision.
        steps: The steps of this run.

    Returns:
        The failed check, or None if the decision is backed by the recorded results.
    """
    employee_id = decision.employee_id.strip().upper()
    item = decision.item.strip().lower()
    statuses = {
        (step.observation.data or {}).get("status")
        for step in steps
        if step.call.tool == CHECK_REQUEST_ELIGIBILITY
        and step.observation.ok
        and (step.observation.data or {}).get("employee_id") == employee_id
        and (step.observation.data or {}).get("item") == item
    }
    subject = f"{employee_id} and {item!r}"
    if decision.decision == "approve" and "eligible" not in statuses:
        message = f"approve without an eligible result for {subject} in this run"
        return Violation("G8", "GUARDRAIL_TRIGGERED", message)
    if decision.decision == "deny" and "not_eligible" not in statuses:
        message = f"deny without a not_eligible result for {subject} in this run"
        return Violation("G9", "GUARDRAIL_TRIGGERED", message)
    ticket = filed_ticket(steps)
    if decision.decision == "escalate" and (ticket is None or decision.ticket_id != ticket):
        message = f"escalate with ticket {decision.ticket_id!r}, but this run filed {ticket!r}"
        return Violation("G10", "GUARDRAIL_TRIGGERED", message)
    return None
