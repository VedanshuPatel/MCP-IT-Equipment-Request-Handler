"""Data models shared by the repositories, the tools and the MCP server.

Pydantic validates the mock data when it is loaded and defines the JSON that the tools
return, so the MCP output schema comes straight from these classes.
"""

from datetime import date, datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

#: Employee IDs are ``E`` followed by exactly 3 digits (REQUIREMENTS 2.2).
EMPLOYEE_ID_PATTERN = r"^E\d{3}$"


class EquipmentUnit(BaseModel):
    """One unit of equipment on file for an employee."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    item: str = Field(min_length=1, description="Catalog item, for example 'laptop'.")
    issued_on: date = Field(description="Date the unit was issued.")


class Employee(BaseModel):
    """An employee record as stored in the mock HR data."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    employee_id: str = Field(pattern=EMPLOYEE_ID_PATTERN)
    name: str = Field(min_length=1)
    role: str = Field(min_length=1)
    hire_date: date
    equipment: tuple[EquipmentUnit, ...] = ()


class EmployeeInfo(BaseModel):
    """Result of ``get_employee_info`` (REQUIREMENTS 4.1)."""

    employee_id: str = Field(description="Normalized employee ID, for example 'E002'.")
    name: str
    role: str = Field(description="One of the roles in the policy table.")
    hire_date: date
    tenure_years: int = Field(ge=0, description="Completed years since the hire date.")
    equipment: list[EquipmentUnit] = Field(description="Every unit currently on file.")


class ItemPolicy(BaseModel):
    """The policy for one item and one role: how many units and how often."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_quantity: int = Field(ge=0, description="Most units allowed; 0 means not eligible.")
    replacement_years: int | None = Field(
        default=None, ge=1, description="Whole years before a unit may be replaced."
    )

    @model_validator(mode="after")
    def _interval_required_when_eligible(self) -> Self:
        if self.max_quantity > 0 and self.replacement_years is None:
            raise ValueError("replacement_years is required when max_quantity is above 0")
        return self


class PolicyTable(BaseModel):
    """The whole policy file: the catalog and, for each role, a policy per catalog item."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    catalog: tuple[str, ...] = Field(min_length=1)
    roles: dict[str, dict[str, ItemPolicy]] = Field(min_length=1)

    @model_validator(mode="after")
    def _every_role_covers_the_catalog(self) -> Self:
        expected = set(self.catalog)
        for role, items in self.roles.items():
            if set(items) != expected:
                missing = sorted(expected - set(items))
                extra = sorted(set(items) - expected)
                raise ValueError(
                    f"role {role!r} must cover the catalog: missing {missing}, extra {extra}"
                )
        return self


class ItemLimit(BaseModel):
    """One row of ``get_policy_limits``: a catalog item and the role's limit for it."""

    item: str
    max_quantity: int = Field(description="Most units allowed; 0 means not eligible.")
    replacement_years: int | None = Field(description="Years before replacement; null if none.")
    eligible: bool = Field(description="True when max_quantity is above 0.")


class PolicyLimits(BaseModel):
    """Result of ``get_policy_limits`` (REQUIREMENTS 4.2)."""

    role: str = Field(description="Normalized role, for example 'manager'.")
    items: list[ItemLimit] = Field(description="One entry per catalog item, in catalog order.")


#: Outcome of an eligibility check (REQUIREMENTS 4.3).
EligibilityStatus = Literal["eligible", "not_eligible", "needs_review"]

#: The rule that decided an eligibility check (REQUIREMENTS section 5).
ReasonCode = Literal[
    "EMPLOYEE_NOT_FOUND",
    "UNKNOWN_ITEM",
    "ROLE_NOT_ELIGIBLE",
    "NEW_ALLOCATION",
    "REFRESH_DUE",
    "LIMIT_REACHED",
]


class EligibilityResult(BaseModel):
    """Result of ``check_request_eligibility`` (REQUIREMENTS 4.3)."""

    status: EligibilityStatus
    reason_code: ReasonCode = Field(description="The rule that decided (REQUIREMENTS 5).")
    employee_id: str = Field(description="Normalized employee ID.")
    item: str = Field(description="Normalized item name.")
    held: int | None = Field(default=None, description="Units on file; null when unknown.")
    max_quantity: int | None = Field(
        default=None, description="The role's limit for the item; null when unknown."
    )
    next_eligible_date: date | None = Field(
        default=None, description="LIMIT_REACHED only: when a replacement becomes possible."
    )
    message: str = Field(description="One plain-English sentence explaining the result.")


#: Escalation requests are stored in full but capped (REQUIREMENTS 4.4).
MAX_REQUEST_LENGTH = 2000
MAX_REASON_LENGTH = 500


class EscalationTicket(BaseModel):
    """One escalation, as stored in ``escalations.jsonl`` (REQUIREMENTS 4.4)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ticket_id: str = Field(pattern=r"^ESC-\d{6}$")
    employee_id: str = Field(description="Normalized employee ID, or 'UNKNOWN'.")
    request: str = Field(min_length=1, max_length=MAX_REQUEST_LENGTH)
    reason: str = Field(min_length=1, max_length=MAX_REASON_LENGTH)
    status: Literal["open"] = "open"
    created_at: datetime = Field(description="When the ticket was created, in UTC.")


class EscalationResult(BaseModel):
    """Result of ``flag_for_human_review`` (REQUIREMENTS 4.4)."""

    ticket_id: str = Field(description="Ticket ID, for example 'ESC-000001'.")
    status: Literal["open"] = Field(description="Tickets start open for a human reviewer.")
    duplicate: bool = Field(
        description="True when an open ticket already existed for this employee and request."
    )
