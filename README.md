# IT Equipment Request Handler

[![CI](https://github.com/VedanshuPatel/MCP-IT-Equipment-Request-Handler/actions/workflows/ci.yml/badge.svg)](https://github.com/VedanshuPatel/MCP-IT-Equipment-Request-Handler/actions/workflows/ci.yml)

An internal IT equipment request handler, built in two parts:

- **MCP server.** Exposes a mock equipment system (employees, role policies, eligibility checks and escalation to human review) over **Streamable HTTP**.
- **ReAct agent.** Reads a natural-language request, investigates it with the server's tools, reflects on its draft, and then **approves**, **denies** or **escalates** it to a human.

> **Status:** The agent has been run live on the four demo requests: one approval, one denial and two escalations for different reasons, as REQUIREMENTS section 11 expects. The ReAct agent works inside guardrails that enforce the decision table in code, has a reviewer for every draft, can be traced end to end, and switches to a hosted fallback model when Foundry has an outage. The rules the system implements are in [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md); [CHANGELOG.md](CHANGELOG.md) lists what has been built so far.

## Tech stack

| Area | Choice |
|---|---|
| Language | Python ≥ 3.12 |
| MCP | `mcp` 2.x over Streamable HTTP |
| LLM | Microsoft Foundry (OpenAI-compatible Responses API), with a keyless hosted fallback model (OVHcloud AI Endpoints) |
| Observability | OpenTelemetry (SDK, console exporter); `mcp`'s built-in spans plus the agent's own |
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
python -m pip install -r requirements.txt   # exact, tested versions (the same set CI uses)
python -m pip install -e . --no-deps
cp .env.example .env               # fill in values when a later phase needs them
```

### Quality checks (the same ones CI runs)

```bash
ruff check .            # lint + docstring rules
ruff format --check .   # formatting
pytest                  # tests + coverage gate (85%); live tests are deselected
```

### Live end-to-end tests (not in CI)

These call the real Foundry model and the real MCP server over HTTP, so they are opt-in. They read `FOUNDRY_*` from the environment or `.env`, and are skipped without them:

```bash
pytest -m live --no-cov
```

The model is not deterministic, so the assertions accept any sensible step rather than one exact reply.

### Run the MCP server

```bash
python -m it_equipment.server      # terminal 1: serves http://127.0.0.1:8000/mcp
python scripts/smoke_client.py     # terminal 2: calls get_employee_info for E002 and E999
```

Expected client output (shortened):

```
Connected to http://127.0.0.1:8000/mcp
Tools: check_request_eligibility, flag_for_human_review, get_employee_info, get_policy_limits, ping

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

Settings:
- `MCP_HOST` and `MCP_PORT`: where the server listens. Loopback addresses only.
- `DATA_DIR`: where the server reads the mock data (`employees.json`, `policies.json`) and writes escalation tickets (`escalations.jsonl`). Default: `data`.
- `MCP_SERVER_URL`: where the clients connect.

The server and the two client scripts read these from the environment only, so the server never loads the Foundry key from `.env`. To change the port, set it for both: `MCP_PORT=9000 python -m it_equipment.server`, and `MCP_SERVER_URL=http://127.0.0.1:9000/mcp` for the client (in the shell, or in `.env` for `scripts/run_agent.py`, which reads it).

### Agent: ReAct run

Put your Foundry settings in `.env` (copy `.env.example`; `.env` is git-ignored):

```
FOUNDRY_ENDPOINT=https://<your-resource>.services.ai.azure.com/openai/v1
FOUNDRY_API_KEY=<your-api-key>
FOUNDRY_DEPLOYMENT=<your-deployment>
# FOUNDRY_MAX_RETRIES=2   # optional: retries before switching to the fallback
```

Then, with the server running in another terminal:

```bash
python scripts/run_agent.py                                   # demo request 1
python scripts/run_agent.py "Hi, I'm E003 and I'd like a second monitor."   # any request
```

Each step prints as it happens (Thought, Action, Observation), followed by the final decision, its reason code, who decided (the model, or the agent's own code) and the response to the employee.

Guardrails (REQUIREMENTS section 9) surround the model. A request that is empty, too long, has no employee ID or contains a prompt-injection phrase is escalated before the model is called. A tool that was not offered, or a second escalation, is refused. The draft decision is then checked in code: it must be for the employee who sent the request; an approval or denial needs an eligibility result in the same run with the same reason code; an escalation needs the ticket that run filed and an escalation code; and once a ticket is filed, the run can only end as that escalation. A model call without a thought counts as an invalid reply. Two invalid model replies in a row, the step limit (`AGENT_MAX_STEPS`, default 8) or a model that cannot be reached all end in an escalation with a ticket, never in a crash.

Reflection (REQUIREMENTS section 8): every draft decision that passes the guardrails goes to a reviewer, a separate model call with its own instructions. It compares the draft with the tool results of the run, without seeing earlier drafts or verdicts, and answers `confirmed`, or `revise` with the issues to fix, for example a promised delivery date. The verdict shows in the trace as the observation of the `submit_decision` step. After one `revise` the agent gets one more attempt; a second rejected draft is escalated.

The default test run never calls Foundry: it uses a scripted model and a mocked HTTP layer, so CI needs no key. To check against the real model, run the live tests (`pytest -m live --no-cov`, see above).

### Fallback model (built in, no key)

When Foundry is unreachable, times out, is rate-limited or returns a server error, a second model takes over: by default `Qwen3.5-397B-A17B` on [OVHcloud AI Endpoints](https://docs.ovhcloud.com/en/guides/public-cloud/ai-machine-learning/ai-endpoints-getting-started), called through the same `openai` library in anonymous mode. It needs no API key and no download, and works with no settings.

To use a different model, set any of these optional variables in `.env`. The fallback is always called without a key, so the replacement must be a keyless, OpenAI-compatible Chat Completions endpoint that supports tool calling:

```
FALLBACK_ENDPOINT=https://oai.endpoints.kepler.ai.cloud.ovh.net/v1   # default
FALLBACK_MODEL=Qwen3.5-397B-A17B                                     # default
FALLBACK_MAX_RETRIES=8                                               # default: retries for rate limits and server errors
```

- OVHcloud's anonymous mode allows 2 requests per minute, so a run on the fallback takes a minute or two; with the default 8 retries the client waits out a rate limit (HTTP 429) for up to about 40 seconds per call.
- While the fallback answers, the request and the tool results are sent to OVHcloud.
- A configuration problem with Foundry, such as a wrong key or endpoint, is not hidden by the fallback: the request is escalated and the trace names the error.
- After an outage the fallback answers for the rest of the run, and the `llm.generate` spans record which model answered.

### Observability (OpenTelemetry)

Set `OTEL_ENABLED=true` for the server and the agent, and each process prints its spans to the console as they finish:

```bash
OTEL_ENABLED=true python -m it_equipment.server     # terminal 1
OTEL_ENABLED=true python scripts/run_agent.py       # terminal 2
```

One request is one trace across both processes. The agent records `agent.run` (the outcome), one `agent.step` per step, `llm.generate` per model call, `agent.reflection` per review and `agent.escalation` when its own code escalates. The `mcp` library adds an `MCP send ...` span for every request the agent sends and a matching span in the server, linked through the trace context it passes in each request. Spans carry only IDs, actions, decisions and codes, never request text, prompts, model output or secrets; tests check this. Telemetry is off by default.

## Project layout

```
.
├── .github/workflows/ci.yml   CI pipeline
├── data/                      employees.json, policies.json (mock data); escalations.jsonl (runtime, git-ignored)
├── docs/                      REQUIREMENTS.md, ARCHITECTURE.md
├── scripts/                   run_agent.py (agent), smoke_client.py, hello_client.py (MCP clients)
├── src/it_equipment/          application package (see docs/ARCHITECTURE.md)
├── tests/unit/                unit tests, no network
├── tests/integration/         MCP protocol tests: in-process and over real HTTP
├── tests/agent/               agent tests with a scripted model and the real server in-process
├── tests/live/                opt-in end-to-end tests against the real Foundry model
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
