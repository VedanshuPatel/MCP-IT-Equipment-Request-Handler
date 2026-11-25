# IT Equipment Request Handler

[![CI](https://github.com/VedanshuPatel/MCP-IT-Equipment-Request-Handler/actions/workflows/ci.yml/badge.svg)](https://github.com/VedanshuPatel/MCP-IT-Equipment-Request-Handler/actions/workflows/ci.yml)

An internal IT equipment request handler, built in two parts:

- **MCP server.** Exposes a mock equipment system (employees, role policies, eligibility checks and escalation to human review) over **Streamable HTTP**.
- **ReAct agent.** Reads a natural-language request, investigates it with the server's tools, reflects on its draft, and then **approves**, **denies** or **escalates** it to a human.

> **Status:** Phase 6, the MCP server is complete: `get_employee_info`, `get_policy_limits`, `check_request_eligibility` and `flag_for_human_review`. The rules the system implements are in [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md); [CHANGELOG.md](CHANGELOG.md) lists what has been built so far.

## Tech stack

| Area | Choice |
|---|---|
| Language | Python ≥ 3.12 |
| MCP | `mcp` 2.x over Streamable HTTP |
| LLM | Microsoft Foundry (OpenAI-compatible Responses API), with a small local model as fallback |
| Observability | OpenTelemetry |
| Quality | pytest with coverage; ruff for lint, formatting and docstrings |
| CI | GitHub Actions |

## Getting started

### Prerequisites

- Python 3.12 or newer (developed on 3.15)
- Git

### Setup

```bash
git clone https://github.com/VedanshuPatel/MCP-IT-Equipment-Request-Handler.git
cd MCP-IT-Equipment-Request-Handler
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
cp .env.example .env               # fill in values when a later phase needs them
```

### Quality checks (the same ones CI runs)

```bash
ruff check .            # lint + docstring rules
ruff format --check .   # formatting
pytest                  # tests + coverage gate (85%)
```

### Run the MCP server

```bash
python -m it_equipment.server      # terminal 1: serves http://127.0.0.1:8000/mcp
python scripts/smoke_client.py     # terminal 2: calls get_employee_info for E002 and E999
```

Expected client output (shortened):

```
Connected to http://127.0.0.1:8000/mcp
Tools: get_employee_info, ping

get_employee_info('E002') ->
{
  "employee_id": "E002",
  "name": "Priya Shah",
  "role": "manager",
  ...
}

get_employee_info('E999') ->
  error: Error executing tool get_employee_info: EMPLOYEE_NOT_FOUND: no employee with ID E999
```

Pass your own IDs with `python scripts/smoke_client.py E004 E006`. `scripts/hello_client.py` still checks plain connectivity with `ping`.

Settings (see `.env.example`):
- `MCP_HOST` and `MCP_PORT`: where the server listens. Loopback addresses only.
- `DATA_DIR`: where the server reads the mock data (`employees.json`, `policies.json`) and writes escalation tickets (`escalations.jsonl`). Default: `data`.
- `MCP_SERVER_URL`: where the clients connect.

## Project layout

```
.
├── .github/workflows/ci.yml   CI pipeline
├── data/                      employees.json, policies.json (mock data); escalations.jsonl (runtime, git-ignored)
├── docs/                      REQUIREMENTS.md, ARCHITECTURE.md
├── scripts/                   smoke_client.py, hello_client.py (manual MCP clients)
├── src/it_equipment/          application package (see docs/ARCHITECTURE.md)
├── tests/unit/                unit tests, no network
├── tests/integration/         MCP protocol tests: in-process and over real HTTP
├── .env.example               configuration template
├── CHANGELOG.md               notable changes
├── pyproject.toml             metadata, dependencies, tool configuration
└── SCOPE.md                   lab brief
```

## Development workflow

Each phase is built on its own branch, test-first:

1. Create `<type>/<name>` from an up-to-date `main`. The type is `chore`, `docs` or `feature`.
2. **Red → Green → Refactor:** write a failing test, make it pass, then clean up.
3. Run the quality checks, and update `CHANGELOG.md` and the affected docs.
4. Push, wait for CI to pass, merge into `main` with `--no-ff`, then delete the branch.

**Definition of Done:**

- Tests were written first and pass, with branch coverage of at least 85%.
- `ruff check .` and `ruff format --check .` pass.
- Every public module, class and function has a docstring.
- `CHANGELOG.md` and any affected docs are updated in the same branch.
- CI passes on the branch before it is merged.

## Documentation

- [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md): policy rules, tool contracts, decision rules, guardrails and acceptance criteria
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): what is built so far, and key decisions
- [CHANGELOG.md](CHANGELOG.md): notable changes
- [SCOPE.md](SCOPE.md): lab brief
