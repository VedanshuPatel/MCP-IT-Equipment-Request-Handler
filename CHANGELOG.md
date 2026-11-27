# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- `scripts/run_agent.py` ends with a note when the fallback model took over during the run, so the model named in the header is never mistaken for the one that answered. Its docstring lists every setting it reads.

- Response rule R7: every date in a response is written as `YYYY-MM-DD`, as the tools return it. The agent and the reviewer share the rule, so the reviewer sends back a draft that spells a date out ("November 3, 2028").
- Scripted agent tests for demo requests 2, 4 and 5, and for request 8 (E001 asks for a second monitor); a test that the two mock-data files agree on roles and items.
- A live test for request 9: a replacement that is due ("my monitor is getting old, can I get a new one?") is still approved.
- Model fallback (REQUIREMENTS N5): when Foundry is unreachable, times out, is rate-limited or returns a server error, `FallbackLLM` switches to `ChatCompletionsLLM`, a keyless client for a hosted model: by default `Qwen3.5-397B-A17B` on OVHcloud AI Endpoints in anonymous mode. No API key, no download and no new dependency; requests carry no `Authorization` header, and rate limits are waited out. The optional `FALLBACK_ENDPOINT`, `FALLBACK_MODEL` and `FALLBACK_MAX_RETRIES` (default 8) choose another keyless model and how long rate limits are waited out; no secret is ever asked for. Configuration errors, such as a wrong Foundry key, are still reported. The `llm.generate` span records which model answered and an `llm.fallback` event marks the switch.
- `LLMCallError.outage` tells outages from configuration errors.
- Optional `FOUNDRY_MAX_RETRIES` (default 2, so an outage switches to the fallback within seconds); `AGENT_MAX_STEPS`, `FOUNDRY_MAX_RETRIES` and `FALLBACK_MAX_RETRIES` share one parser, and a blank value keeps the default.
- OpenTelemetry (`telemetry.py`, REQUIREMENTS N4): with `OTEL_ENABLED=true`, the server and the agent print their spans to the console. The agent records `agent.run`, `agent.step`, `llm.generate`, `agent.reflection` and `agent.escalation`; the `mcp` library's client and server spans join the same trace, so one request is one trace across both processes. Spans carry only IDs, actions, decisions and codes; tests check that no request text, thought or response reaches a span.
- Dependency: `opentelemetry-sdk`.
- Reflection (`agent/reflection.py`, REQUIREMENTS 8): every draft that passes the output guardrails is reviewed by a separate model call through the strict `submit_review` tool (`confirmed`, or `revise` with issues). The verdict is the observation of the `submit_decision` step, so it shows in the trace; after one `revise` the agent gets one more attempt, and a second rejected draft escalates with `AGENT_ERROR`.
- The agent and the reviewer share the same decision and response rules (`DECISION_RULES`, `RESPONSE_RULES` in `agent/prompts.py`).

- Guardrails (`agent/guardrails.py`, REQUIREMENTS 9): input checks G1 to G3 before any model call (empty or too long, no employee ID, prompt-injection phrases); step checks G5 (only offered tools) and G7 (one escalation per request); output checks G8 to G10 (an approval or denial needs a matching eligibility result, an escalation needs the ticket filed in this run).
- Escalation as the safety default: a blocked request, two invalid model replies in a row (G4), the step limit (G6), a model that cannot be reached, or a draft that fails the output checks ends in an escalation filed by the agent's own code, with a ticket and a plain-language response. Every run now ends with a decision; the trace shows whether the model or the agent decided.
- `LLMCallError`: a failed request to Foundry (connection, timeout, rate limit, authentication, server error) names the error and its cause, never the key.
- `AGENT_MAX_STEPS` setting for the step limit (default 8).
- The ticket of an escalation always holds the employee's original request text.
- ReAct agent (`agent/react.py`): each step the model sees the request, the tools and every earlier step, and makes one tool call; tool errors and invalid decisions are shown to it as observations; the run ends with `submit_decision` or at the step limit (8).
- `submit_decision`: an agent-local strict tool generated from the `Decision` model (REQUIREMENTS 6.1), with enums for the decision and the reason codes the model may give.
- ReAct trace (`agent/trace.py`): Thought, Action and Observation per step plus the final decision, as console text and as JSON.
- Agent instructions with the decision table, exceptions and response rules (REQUIREMENTS 6 and 7).
- `scripts/run_agent.py`: runs the agent on a request against Foundry and prints the trace live.
- Live tests for demo requests 1 to 5: expected decision and reason code, the date in the denial, one ticket per escalation, a thought on every step.
- `FoundryLLM` behind an `LLMClient` protocol: Microsoft Foundry through the OpenAI Responses API with native function calling. Every request requires exactly one tool call (`tool_choice="required"`, no parallel calls) and returns a `ToolCall` (tool, thought, arguments); the steps so far are sent back with every request.
- Tool catalog built from the server's `list_tools`: each tool is offered as a strict function whose schema has an extra required `thought` argument, so every call carries the model's reason (the ReAct Thought); `ping` is hidden.
- `McpToolClient`: MCP client that turns every tool result, success or error, into an `Observation`.
- Settings for the agent: `FoundrySettings` (`FOUNDRY_ENDPOINT`, `FOUNDRY_API_KEY`, `FOUNDRY_DEPLOYMENT`; the key never appears in `repr` or error messages) and `.env` loading with `python-dotenv`.
- Dependencies: `openai`, `python-dotenv`.
- Live end-to-end tests (`tests/live/`, marker `live`): the real Foundry model and the real MCP server over HTTP. Deselected by default and skipped without `FOUNDRY_*` settings; run with `pytest -m live --no-cov`.
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

- Dependencies have an upper bound below their next major version, so a major release cannot break CI without a code change.
- The README says that the server and the client scripts read their settings from the environment only; `.env` is read by `scripts/run_agent.py`.
- Simpler agent loop: inside a run, every escalation is raised as one internal exception and filed in one place, instead of a callable escalator class; the trace works out who decided from the stop reason, so `AgentResult.decided_by` is gone; the G8 and G9 check reads the eligibility results with a small helper.

- End-to-end tests run the server on a temporary copy of `data/`, so escalations never touch the repository; `data/escalations.jsonl` is git-ignored.

- REQUIREMENTS section 4: tool error text *contains* the error code, because the MCP SDK puts `Error executing tool <name>: ` in front of it.

### Fixed

- A request for an extra unit while a unit on file was due (for example a second monitor for E001) was approved. `REFRESH_DUE` now allows a replacement only: the agent and the reviewer escalate such a request with `AMBIGUOUS_REQUEST`, and the eligibility message says the unit can be replaced but none added. A `LIMIT_REACHED` denial gives its date as the date a unit can be replaced, never a date for an extra unit.
- The output guardrails checked only the eligibility status. G8 and G9 now also require the same reason code as the eligibility result; G10 requires an escalation code, and once a ticket is filed the run can only end as that escalation (approvals and denials carry no ticket); the new G11 blocks a decision for anyone other than the employee who sent the request.
- A draft blocked by an output guardrail could put the model's text into the `agent.step` span as an exception event; step spans no longer record exceptions (REQUIREMENTS N4).
- The reviewer saw earlier drafts and their verdicts; it now sees only the tool results.
- After the model filed a ticket, the reviewer could still ask for a deny, which G10 then blocked. The rules the agent and the reviewer share now say that a filed ticket cannot be withdrawn, so the decision stays an escalation.
- A model call without a `thought` was accepted; it is now an invalid reply and is retried (G4). A reviewer reply that is not a valid review is retried once too, instead of escalating at once.
- `<` and `>` in a request are escaped, so the request cannot close its `<request>` tag.
- Two identical escalations arriving at the same moment could create two tickets; the store now looks for an open ticket and appends a new one under one lock (`find_or_create`).
- Employee IDs accept ASCII digits only (`\d` also matched digits from other scripts).
