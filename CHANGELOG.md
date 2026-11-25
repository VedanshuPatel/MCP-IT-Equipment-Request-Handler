# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- `flag_for_human_review` MCP tool: creates an open escalation ticket (`ESC-000001`, ...) in `DATA_DIR/escalations.jsonl`; returns the existing ticket for a repeated employee and request (`duplicate: true`); accepts `UNKNOWN` when a request has no employee ID; `INVALID_INPUT` for an empty or too-long request or reason. The MCP server now has all four tools.
- `EscalationRepository` protocol with a JSON Lines implementation, and a UTC clock injected into `EquipmentTools` for ticket timestamps.
- MCP tool annotations: the three lookup tools are read-only; `flag_for_human_review` is a non-destructive, idempotent write.

- `check_request_eligibility` MCP tool: decides `eligible`, `not_eligible` or `needs_review` with a reason code (`NEW_ALLOCATION`, `REFRESH_DUE`, `LIMIT_REACHED`, `ROLE_NOT_ELIGIBLE`, `UNKNOWN_ITEM`, `EMPLOYEE_NOT_FOUND`), the units held, the role's limit, the next eligible date and a plain-English message; `INVALID_INPUT` error for an empty item.
- Eligibility rule chain (`rules.py`): one class per rule E1 to E6, applied in order; due dates handle 29 February.

- `get_policy_limits` MCP tool: for a role, the maximum quantity, replacement interval and eligibility of every catalog item; roles are case- and space-insensitive; `UNKNOWN_ROLE` error.
- Policy table (`data/policies.json`) with a `PolicyRepository` protocol and JSON implementation; the table is validated at startup (every role covers exactly the catalog).

- `get_employee_info` MCP tool: role, tenure and current equipment for an employee; IDs are case- and space-insensitive; `INVALID_EMPLOYEE_ID` and `EMPLOYEE_NOT_FOUND` errors.
- Mock employee data (`data/employees.json`), validated by Pydantic models at startup; `DATA_DIR` setting.
- `EquipmentTools` facade, `EmployeeRepository` protocol with a JSON implementation, and `DomainError` codes.
- `scripts/smoke_client.py`: calls `get_employee_info` on the running server (SCOPE step 3).

- MCP server (`python -m it_equipment.server`) built on `mcp` 2.x `MCPServer`, serving a `ping` tool over Streamable HTTP at `http://127.0.0.1:8000/mcp`.
- Settings (`it_equipment.config`): `MCP_HOST`, `MCP_PORT` and `MCP_SERVER_URL`, validated; the server refuses non-loopback hosts.
- `scripts/hello_client.py`: connects to the server, lists its tools and calls `ping`.
- Integration tests: in-process MCP protocol tests, and end-to-end tests that start the real server and check `ping`, the hello client and DNS-rebinding protection.

- Project scaffolding: `pyproject.toml` with a `src/` layout and `dev` extras.
- ruff for linting and formatting, with Google-style docstring rules.
- pytest with a branch-coverage gate at 85%.
- GitHub Actions CI: lint, format check and tests on Python 3.12 and 3.15.
- `it_equipment` package skeleton that reads its version from the installed package metadata, with smoke tests.
- Documentation: README, `docs/ARCHITECTURE.md`, this changelog, and the `.env.example` configuration template.
- `docs/REQUIREMENTS.md`: request data, mock data set, policy rules, contracts for the four MCP tools, eligibility rules with a test matrix, agent decision rules, what counts as ambiguous, response rules, reflection, guardrails, acceptance criteria (AC-01 to AC-22) and the demo requests.

### Changed

- End-to-end tests run the server on a temporary copy of `data/`, so escalations never touch the repository; `data/escalations.jsonl` is git-ignored.

- REQUIREMENTS section 4: tool error text *contains* the error code, because the MCP SDK puts `Error executing tool <name>: ` in front of it.
