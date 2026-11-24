# Architecture

This document describes what is **built so far** and records the key decisions. It is updated as each phase is merged.

_Last updated: Phase 0, project setup._

## Current state

Only the project skeleton exists.

| Component | Path | Purpose |
|---|---|---|
| Package | `src/it_equipment/` | Application code (only the package version so far) |
| Tests | `tests/unit/` | Smoke tests for the package |
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
