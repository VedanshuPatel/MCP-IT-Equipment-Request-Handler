"""Domain errors raised by the tools.

Each error has a stable ``code`` (REQUIREMENTS section 4). The message is
``"<CODE>: <explanation>"``, so the code survives however the error is reported. The tools
know nothing about MCP; the server turns these errors into MCP tool errors.
"""

from typing import ClassVar


class DomainError(Exception):
    """An anticipated failure with a stable error code.

    Args:
        message: Plain-English explanation, without the code.
    """

    code: ClassVar[str] = "DOMAIN_ERROR"

    def __init__(self, message: str) -> None:
        """Store the explanation and build the ``"<CODE>: <message>"`` text."""
        self.message = message
        super().__init__(f"{self.code}: {message}")


class InvalidEmployeeIdError(DomainError):
    """The employee ID is not ``E`` followed by exactly 3 digits."""

    code = "INVALID_EMPLOYEE_ID"


class EmployeeNotFoundError(DomainError):
    """No employee has the given ID."""

    code = "EMPLOYEE_NOT_FOUND"


class UnknownRoleError(DomainError):
    """The role is not in the policy table."""

    code = "UNKNOWN_ROLE"


class InvalidInputError(DomainError):
    """An argument is empty, too long or otherwise unusable."""

    code = "INVALID_INPUT"
