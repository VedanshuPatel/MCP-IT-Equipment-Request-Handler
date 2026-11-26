"""The ReAct trace: what the agent thought, did and saw, as console text and as JSON.

Every run produces an ``AgentResult``: one ``Step`` per tool call (Thought, Action,
Observation) and the final decision with the thought behind it (REQUIREMENTS N3). When the
agent's own code escalates (a guardrail, an invalid reply, the step limit, a model error), its
``flag_for_human_review`` call is a step too, with a thought starting with ``(agent)``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from it_equipment.agent.decision import Decision
from it_equipment.agent.llm import ToolCall
from it_equipment.agent.mcp_client import Observation

#: Why a run ended: ``decided`` when the model's decision passed every check (the model
#: decided); anything else names the problem that made the agent escalate.
StopReason = Literal[
    "decided",
    "input_guardrail",
    "output_guardrail",
    "invalid_output",
    "model_error",
    "step_limit",
]


@dataclass(frozen=True, slots=True)
class Step:
    """One ReAct step.

    Attributes:
        number: 1 for the first step.
        call: The Thought and the Action (tool and arguments).
        observation: What the tool returned, or why the action was rejected.
    """

    number: int
    call: ToolCall
    observation: Observation

    def to_dict(self) -> dict[str, Any]:
        """The step as JSON-ready data."""
        return {
            "number": self.number,
            "thought": self.call.thought,
            "action": self.call.tool,
            "arguments": self.call.arguments,
            "ok": self.observation.ok,
            "observation": self.observation.data if self.observation.ok else self.observation.text,
        }


@dataclass(frozen=True, slots=True)
class AgentResult:
    """The outcome of one run.

    Attributes:
        request: The employee's request.
        steps: Every tool step, in order.
        stop: Why the run ended.
        decision: The final decision; every run ends with one.
        decision_thought: Why: the model's thought, or the agent's reason for escalating.
    """

    request: str
    steps: tuple[Step, ...]
    stop: StopReason
    decision: Decision
    decision_thought: str = ""

    def to_dict(self) -> dict[str, Any]:
        """The whole trace as JSON-ready data, for saving runs."""
        return {
            "request": self.request,
            "steps": [step.to_dict() for step in self.steps],
            "stop": self.stop,
            "decision_thought": self.decision_thought,
            "decision": self.decision.model_dump(),
        }


def format_step(step: Step) -> str:
    """Render one step as console text: Thought, Action, Observation."""
    observation = (
        json.dumps(step.observation.data) if step.observation.ok else step.observation.text
    )
    label = "Observation" if step.observation.ok else "Observation (error)"
    return "\n".join(
        [
            f"Step {step.number}",
            f"  Thought: {step.call.thought}",
            f"  Action: {step.call.tool}({json.dumps(step.call.arguments)})",
            f"  {label}: {observation}",
        ]
    )


def format_result(result: AgentResult) -> str:
    """Render the end of a run: who decided, why, the decision and the response."""
    decision = result.decision
    decided_by = "model" if result.stop == "decided" else f"agent ({result.stop})"
    lines = [
        "Final",
        f"  Thought: {result.decision_thought}",
        f"  Decision: {decision.decision} ({decision.reason_code}), decided by the {decided_by}",
        f"  Employee: {decision.employee_id}, item: {decision.item or 'unknown'}",
    ]
    if decision.ticket_id:
        lines.append(f"  Ticket: {decision.ticket_id}")
    lines.append(f"  Response: {decision.response}")
    return "\n".join(lines)
