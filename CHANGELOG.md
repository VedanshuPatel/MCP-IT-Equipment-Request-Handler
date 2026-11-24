# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

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
