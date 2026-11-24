"""Data models shared by the repositories, the tools and the MCP server.

Pydantic validates the mock data when it is loaded and defines the JSON that the tools
return, so the MCP output schema comes straight from these classes.
"""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

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
