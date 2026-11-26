# Architecture

This document describes what is **built so far** and records the key decisions. It is updated as each phase is merged.

_Last updated: Phase 12, model fallback._

## Current state

The MCP server is complete: four tools (`get_employee_info`, `get_policy_limits`, `check_request_eligibility`, `flag_for_human_review`) plus `ping`. The agent connects to it over MCP and runs the ReAct loop with native function calling, inside guardrails, with a separate reviewer for every draft decision:

```
scripts/run_agent.py
  └─ react.run_agent(llm, mcp, request)
       G1-G3 input checks ── blocked ──────────────────────────────────────────► agent escalation
       tools = McpToolClient.list_tools() + submit_decision      (each with a required "thought")
       repeat, at most AGENT_MAX_STEPS (8) times:
         FoundryLLM.next_call(instructions, request, tools, history) ──► ToolCall(tool, thought, arguments)
           invalid reply: retry once (G4); twice, or model unreachable ──────► agent escalation
         ├─ submit_decision ──► SubmittedDecision ──► G8-G10 output checks
         │                        ├─ fail ────────────────────────────────────► agent escalation
         │                        └─ pass ──► reviewer (separate model call, submit_review)
         │                                     ├─ confirmed ──► AgentResult(decided by the model)  end
         │                                     └─ revise ──► Observation of the submit step;
         │                                                   a second revise ─────────► agent escalation
         ├─ blocked by G5 or G7 ──► error Observation ──► Step
         └─ MCP tool ──► McpToolClient.call_tool ──► Observation ──► Step, added to history
       no decision after the last step (G6) ───────────────────────────────────► agent escalation

agent escalation: flag_for_human_review filed by code ──► Decision(escalate, MISSING_EMPLOYEE_ID |
                  GUARDRAIL_TRIGGERED | AGENT_ERROR, ticket) ──► AgentResult(decided by the agent)
```

Server layers, each depending only on the one below it:

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
| MCP server | `src/it_equipment/server.py` | `create_server()` registers the tools as thin wrappers with tool annotations (three read-only, one idempotent write); `main()` serves Streamable HTTP; with `OTEL_ENABLED=true`, prints the spans of each request |
| Agent: LLM | `src/it_equipment/agent/llm.py` | `LLMClient` protocol (`next_call` returns one `ToolCall`); `FoundryLLM` sends the tools as strict functions with `tool_choice="required"` and no parallel calls, replays the steps so far as function calls and results, finds the call by type and moves `thought` out of the arguments; `ChatCompletionsLLM` calls the keyless fallback model (no `Authorization` header; OVHcloud AI Endpoints by default); `FallbackLLM` switches to it on outages only; `create_llm()` puts it behind Foundry |
| Agent: MCP client | `src/it_equipment/agent/mcp_client.py` | `McpToolClient` wraps `mcp.Client`; every tool result becomes an `Observation` (`ok`, `data`, `text`) |
| Agent: catalog | `src/it_equipment/agent/catalog.py` | Adapts the server's tool definitions (`list_tools`) into `ToolSpec`s: the server's argument schema plus a required `thought` argument; hides `ping`; keeps the read-only hint |
| Agent: ReAct loop | `src/it_equipment/agent/react.py` | `run_agent()`: one tool call per step until the reviewer confirms a decision; runs every guardrail; every escalation is raised as one internal exception and filed by `_escalate()`; always returns a decision |
| Agent: guardrails | `src/it_equipment/agent/guardrails.py` | `check_input` (G1 to G3), `check_step` (G5, G7), `check_output` (G8 to G10): plain checks over the request and the recorded steps |
| Agent: decision | `src/it_equipment/agent/decision.py` | `Decision` (the final record, REQUIREMENTS 6.1) and `SubmittedDecision` (what the model may submit); the `submit_decision` tool is generated from the latter |
| Agent: trace | `src/it_equipment/agent/trace.py` | `Step` and `AgentResult`; console text (`format_step`, `format_result`) and JSON (`to_dict`) |
| Agent: reflection | `src/it_equipment/agent/reflection.py` | `review_draft()`: the reviewer's separate model call with the strict `submit_review` tool; `review_observation()` turns the verdict into the observation of the `submit_decision` step |
| Agent: prompts | `src/it_equipment/agent/prompts.py` | `AGENT_INSTRUCTIONS` and `REVIEW_INSTRUCTIONS`, built from the shared `DECISION_RULES` and `RESPONSE_RULES`; the `<request>` delimiters |
| Telemetry | `src/it_equipment/telemetry.py` | `setup_telemetry()` installs a tracer provider that prints spans to the console when `OTEL_ENABLED` is true; `create_tracer_provider()` names the service. The agent's spans come from `react.py`, `llm.py` and `reflection.py` |
| Agent settings | `src/it_equipment/config.py` | `FoundrySettings` (key hidden from `repr`; optional `FOUNDRY_MAX_RETRIES`, default 2), the optional and keyless `FallbackSettings` (`FALLBACK_ENDPOINT`, `FALLBACK_MODEL`, `FALLBACK_MAX_RETRIES`), `agent_max_steps()` (`AGENT_MAX_STEPS`, default 8) and `load_env_file()` (`.env` never overrides real variables) |
| Mock data | `data/employees.json`, `data/policies.json` | The 6 synthetic employees (REQUIREMENTS 2.3, 2.4) and the policy table (section 3) |
| Clients | `scripts/run_agent.py`, `scripts/smoke_client.py`, `scripts/hello_client.py` | The agent on one request with a live trace; manual MCP checks: `get_employee_info` for given IDs, `ping` |
| Unit tests | `tests/unit/` | Tools, repositories, rules, settings, server and agent parts; no network, today fixed to 2026-11-24 |
| Agent tests | `tests/agent/` | The agent with a scripted model (`ScriptedLLM` in `conftest.py`) and the real server in-process |
| Integration tests | `tests/integration/` | In-process MCP client tests, end-to-end tests against the real server process, and a check that the server's span is a child of the client's span across processes |
| Live tests | `tests/live/` | Opt-in (`pytest -m live --no-cov`): the real Foundry model with the real server over HTTP; skipped without `FOUNDRY_*` settings; never run in CI |
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
| AD-022 | 2026-11-24 | The agent reaches the model only through an `LLMClient` protocol: instructions, prompt and tools in, one `ToolCall` out; `FoundryLLM` is the first implementation | Tests use a scripted model, the Phase 12 local fallback plugs in without touching agent code, and the agent never handles OpenAI types |
| AD-023 | 2026-11-24 | Native function calling: each MCP tool is offered as a strict function with an added required `thought` argument, and every reply must be exactly one tool call | The API enforces the argument schema, so there is no free text to parse; the required `thought` gives every ReAct step a visible Thought, which a reasoning model would otherwise keep hidden; one call per reply keeps one Thought, Action and Observation per step. Tools with optional arguments are sent without strict mode, which requires every argument |
| AD-024 | 2026-11-24 | `FoundryLLM` finds the tool call by type, and uses a 60 s timeout, a 4,096-token reply budget and `store=False` | Reasoning models put a reasoning item first; the SDK's 10-minute default would hang the agent; reasoning tokens count toward the budget; requests are not stored by the service |
| AD-025 | 2026-11-25 | Live end-to-end tests against Foundry are opt-in: marker `live`, deselected by default, skipped without settings; settings are read from the environment, then `.env`, without changing the process environment | CI stays free of secrets and cost; the model is not deterministic, so the assertions accept any sensible step; a passing run proves Foundry accepts the strict tool schemas |
| AD-026 | 2026-11-25 | The ReAct loop makes exactly one tool call per step; MCP tool errors and invalid `submit_decision` arguments go back to the model as observations; the run ends at `submit_decision` or after 8 steps without a decision | One Thought, Action and Observation per step keeps the trace readable; the model can correct itself; the loop always terminates. Turning a run without a decision into an escalation is a guardrail (next phase) |
| AD-027 | 2026-11-25 | Every request to the model replays the steps so far as function calls (with their `thought`) and their results; hidden reasoning items are not replayed | `store=False` keeps nothing on the service; the explicit thoughts carry the reasoning from step to step; the history stays provider-neutral, so a local model can use it too |
| AD-028 | 2026-11-25 | `submit_decision` is an agent-local strict tool generated from the `Decision` Pydantic model; it offers only the reason codes the model may give | One source for the schema and the validation; the codes for missing IDs, guardrails and agent errors are filed by code, never chosen by the model |
| AD-029 | 2026-11-26 | Guardrails are plain code around the model: input checks before any model call, step checks before a tool runs, output checks on the draft decision against the recorded tool results | Deterministic and testable without a model; the model cannot talk its way past them; a blocked tool call becomes an observation so the model can choose again |
| AD-030 | 2026-11-26 | Escalation is the safety default: every failure path files a ticket from the agent's own code (`MISSING_EMPLOYEE_ID`, `GUARDRAIL_TRIGGERED`, `AGENT_ERROR`), and every run ends with a decision | Works even when the model misbehaves or cannot be reached; a human always sees the request; the store's duplicate guard reuses a ticket the model already filed |
| AD-031 | 2026-11-26 | The final record (`Decision`) is wider than what the model may submit (`SubmittedDecision`): only code uses the agent's codes and a missing item | The model cannot choose `AGENT_ERROR` or `GUARDRAIL_TRIGGERED`; one record type covers both kinds of decision |
| AD-032 | 2026-11-26 | A failed request to Foundry raises `LLMCallError` (error type and cause, never the key), and the loop turns it into an `AGENT_ERROR` escalation | A network or configuration problem is reported in the trace instead of a traceback; the planned fallback model can hook in at the same place |
| AD-033 | 2026-11-26 | The agent always sends the employee's original text as the ticket's `request` | A reviewer reads the employee's own words, never the model's paraphrase |
| AD-034 | 2026-11-26 | Reflection is a separate model call with its own instructions and a strict `submit_review` tool; it sees only the request, the recorded tool results and the draft | An independent check that judges the draft by the tool results, not by the agent's reasoning; the strict schema makes the verdict machine-readable |
| AD-035 | 2026-11-26 | The review is the observation of the `submit_decision` step: `confirmed` ends the run, `revise` sends the issues back through the normal loop, and a second `revise` escalates with `AGENT_ERROR` | No separate revision code path; every verdict appears in the trace and in the agent's history; the run still ends within the step limit |
| AD-036 | 2026-11-26 | Telemetry uses the OpenTelemetry SDK with a console exporter and a simple (synchronous) span processor, switched on per process by `OTEL_ENABLED`; the spans `mcp` already records are reused, not duplicated | Uses what the MCP library provides, so one request is one trace across agent and server; nothing to run besides the two processes; off by default so normal output stays readable; changing the backend means changing one exporter |
| AD-037 | 2026-11-26 | Agent spans record only IDs, actions, decisions and codes (`agent.run`, `agent.step`, `llm.generate`, `agent.reflection`, `agent.escalation`); tests scan every span name, attribute, event and status for the request, thoughts and response | Traces are safe to share; the privacy rule is enforced by tests, not by convention |
| AD-038 | 2026-11-26 | The fallback is a hosted model called without a key through the `openai` library already in use: by default `Qwen3.5-397B-A17B` on OVHcloud AI Endpoints in anonymous mode; the optional `FALLBACK_ENDPOINT`, `FALLBACK_MODEL` and `FALLBACK_MAX_RETRIES` choose another keyless model and its retries. Requests omit the `Authorization` header, and by default the client retries a 429 for up to about 40 seconds | Users are never asked for a secret key, nothing is downloaded, and it works with no settings, yet the model can be changed. OVHcloud documents anonymous, OpenAI-compatible access with function calling (2 requests per minute per IP and model). Trade-offs: slow under the rate limit, no availability guarantee, and request data goes to the fallback service while it answers. Strict schemas are not sent; the agent's own checks still validate every call |
| AD-039 | 2026-11-26 | `FallbackLLM` switches only on outages (connection, timeout, rate limit, server error) and then stays on the fallback for the rest of the process; configuration errors are raised | REQUIREMENTS N5: outages are worked around, misconfiguration is fixed rather than hidden; later steps do not wait for Foundry's retries again; spans record which model answered |
