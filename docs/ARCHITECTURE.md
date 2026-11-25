# Architecture

This document describes what is **built so far** and records the key decisions. It is updated as each phase is merged.

_Last updated: Phase 6, `flag_for_human_review`; the MCP server is complete._

## Current state

The MCP server is complete: four tools (`get_employee_info`, `get_policy_limits`, `check_request_eligibility`, `flag_for_human_review`) plus `ping`. Each layer depends only on the one below it:

```
scripts/smoke_client.py ──HTTP──►  server.py     thin @tool wrappers; DomainError → ToolError
   (mcp.Client)                      │
                                     ▼
                                   tools.py      EquipmentTools facade: business logic, clock injected
                                     │      └──► rules.py  eligibility rule chain E1 → E6 (first match wins)
                                     ▼
                                   repositories.py  Employee, Policy and Escalation repository protocols + file implementations
                                     │
                                     ▼
                                   data/employees.json, policies.json (read, validated at startup)
                                   data/escalations.jsonl (written: one ticket per line)
```

| Component | Path | Purpose |
|---|---|---|
| Requirements | `docs/REQUIREMENTS.md` | The testable rules that every later phase implements |
| Settings | `src/it_equipment/config.py` | `ServerSettings` (validated host, port, path), `mcp_server_url()`, `data_dir()` |
| Models | `src/it_equipment/models.py` | Pydantic models: employees (`Employee`, `EmployeeInfo`), policies (`PolicyTable`, `ItemPolicy`, `PolicyLimits`), eligibility (`EligibilityResult`), escalations (`EscalationTicket`, `EscalationResult`); validate the data and define tool output |
| Errors | `src/it_equipment/errors.py` | `DomainError` subclasses with stable codes (`INVALID_EMPLOYEE_ID`, `EMPLOYEE_NOT_FOUND`, `UNKNOWN_ROLE`, `INVALID_INPUT`) |
| Repositories | `src/it_equipment/repositories.py` | `EmployeeRepository`, `PolicyRepository` and `EscalationRepository` protocols; JSON implementations for the mock data and a JSON Lines store for tickets (sequential IDs, lock for concurrent calls) |
| Rules | `src/it_equipment/rules.py` | One class per eligibility rule (E1 to E6), `DEFAULT_RULES` in order, `evaluate()` (first decision wins), `add_years()` |
| Tools | `src/it_equipment/tools.py` | `EquipmentTools`: the four tool methods, with injected repositories, date clock and UTC clock; no MCP code |
| MCP server | `src/it_equipment/server.py` | `create_server()` registers the tools as thin wrappers with tool annotations (three read-only, one idempotent write); `main()` serves Streamable HTTP |
| Mock data | `data/employees.json`, `data/policies.json` | The 6 synthetic employees (REQUIREMENTS 2.3, 2.4) and the policy table (section 3) |
| Clients | `scripts/smoke_client.py`, `scripts/hello_client.py` | Manual checks: `get_employee_info` for given IDs; `ping` |
| Unit tests | `tests/unit/` | Tools, repository, settings, server module; no network, today fixed to 2026-11-24 |
| Integration tests | `tests/integration/` | In-process MCP client tests, and end-to-end tests against the real server process |
| CI | `.github/workflows/ci.yml` | Lint, format check and tests on Python 3.12 and 3.15 |
| Config template | `.env.example` | Every setting planned across the phases |

## Quality gates

| Gate | Tool | Runs | Fails when |
|---|---|---|---|
| Lint | `ruff check` | Locally and in CI | Style errors, likely bugs, unsorted imports, outdated syntax |
| Docstrings | ruff `D` rules (Google style) | Locally and in CI | A public module, class or function has no docstring |
| Format | `ruff format --check` | Locally and in CI | Code isn't formatted |
| Tests | `pytest` | Locally and in CI | Any test fails |
| Coverage | `pytest-cov` | Locally and in CI | Branch coverage is below 85% |

## Decision log

| ID | Date | Decision | Reason |
|---|---|---|---|
| AD-001 | 2026-11-24 | `src/` layout, setuptools, a single `pyproject.toml` | Tests run against the installed package, not loose files; one config file |
| AD-002 | 2026-11-24 | The version is defined once, in `pyproject.toml`, and read at runtime with `importlib.metadata` | One source of truth |
| AD-003 | 2026-11-24 | ruff for linting, formatting and docstring checks | One fast tool instead of flake8, isort, black and pydocstyle |
| AD-004 | 2026-11-24 | CI on every push and on pull requests to `main`, testing Python 3.12 and 3.15 | Catches breakage before merge; covers the minimum supported version and the development version |
| AD-005 | 2026-11-24 | MCP over Streamable HTTP (`mcp` 2.x `MCPServer`) | The server runs as an independent service |
| AD-006 | 2026-11-24 | Microsoft Foundry as the primary LLM, with a small local model as fallback | The organization's platform; the agent keeps working during an outage |
| AD-007 | 2026-11-24 | OpenTelemetry, building on the spans `mcp` already records | One end-to-end trace per request, at little extra cost |
| AD-008 | 2026-11-24 | Eligibility is decided by deterministic server code; the LLM gathers evidence and writes the response | Policy outcomes are testable and repeatable, and the model cannot talk itself into an approval |
| AD-009 | 2026-11-24 | Fail closed: anything the rules cannot decide is escalated with a ticket | A wrong approval costs more than a human review |
| AD-010 | 2026-11-24 | `check_request_eligibility` keeps the SCOPE signature `(employee_id, item)`; an extra unit and an early replacement both return `LIMIT_REACHED` with `next_eligible_date` | Matches the brief exactly; the employee still learns when a replacement becomes possible |
| AD-011 | 2026-11-24 | A `create_server()` factory builds the server; `main()` only runs it | Tests get a fresh server and connect in-process (`mcp.Client(server)`), with no network or global state |
| AD-012 | 2026-11-24 | Settings refuse any non-loopback `MCP_HOST`; the SDK's DNS-rebinding protection stays on and is tested | The server has no authentication, so it must not be reachable from other machines or from web pages (requirement N1) |
| AD-013 | 2026-11-24 | Tool logic lives in an `EquipmentTools` facade with injected repository and clock; `server.py` only wraps it | Each tool is unit-tested as a plain method (SCOPE Part 3); a new tool is one method plus one wrapper |
| AD-014 | 2026-11-24 | Tools raise `DomainError` with a stable code; the server converts it to the SDK's `ToolError` | The client gets `is_error` with the code in the text, while unexpected crashes stay hidden from it |
| AD-015 | 2026-11-24 | Mock data is validated by Pydantic once, when the repository loads | Bad data stops the server at startup instead of failing during a request |
| AD-016 | 2026-11-24 | The policy table is data (`data/policies.json`) validated as a whole: every role must cover exactly the catalog, and an eligible item needs an interval | A new role or item is a data change only, and an incomplete table fails at startup instead of giving a wrong answer later |
| AD-017 | 2026-11-24 | Eligibility is a chain of small rule classes (Strategy), applied in order until one decides | Each rule maps one-to-one to REQUIREMENTS E1 to E6 and is easy to read and test; a new rule is one class added to the list |
| AD-018 | 2026-11-24 | An unknown employee or item returns `needs_review` instead of an error; a role missing from the policy table raises `UNKNOWN_ROLE` | The first two are normal requests a human should see; the last is broken data that must not produce a decision |
| AD-019 | 2026-11-24 | Escalations are appended to `escalations.jsonl` with sequential `ESC-NNNNNN` IDs and a duplicate guard on employee and exact request text; a lock serializes writes | Readable, append-only audit trail; flagging the same request twice cannot create two tickets; concurrent HTTP calls cannot share a ticket ID |
| AD-020 | 2026-11-24 | Tools declare MCP annotations: the lookups are read-only, `flag_for_human_review` is a non-destructive, idempotent write | Clients and the agent can tell which call changes state; the hints match the real behavior and are tested |
| AD-021 | 2026-11-24 | Every test writes tickets to a temporary folder; the end-to-end server runs on a copy of `data/` | Tests never modify the repository's data files |
