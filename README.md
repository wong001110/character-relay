# Echo Masque

**See what remains when the role is challenged.**

Echo Masque is a Python-first behavior validation system for conversational characters and agents. It runs repeatable adversarial sessions against a target, identifies the first behavioral breakpoint, and records evidence for identity drift, fabricated memory, prompt injection, capability violations, and long-conversation instability.

## Product loop

```text
Define target
  -> choose a test suite
  -> run an adversarial session
  -> judge each response
  -> locate the first breakpoint
  -> inspect evidence and replay
  -> change the prompt, model, memory, or policy
  -> rerun and compare
```

## Initial target types

1. **Prompt + model** — Echo Masque owns the conversation and calls an OpenAI-compatible model.
2. **Custom HTTP target** — Echo Masque tests a complete external chatbot or agent through a small adapter contract.
3. **Transcript import** — Echo Masque inspects an existing conversation without actively sending new messages.

A Python adapter SDK is planned after the MVP.

## Core test suites

- Identity integrity
- False-memory injection
- Prompt-injection resistance
- Capability boundaries
- Long-conversation drift
- Knowledge-boundary leakage
- Tool-behavior reliability

The first MVP implements the first four suites, with deterministic fixtures so the repository remains usable without an API key.

## Delivery phases

### Phase 0 — Product contract and roadmap

Define the product boundary, architecture direction, repository standards, phase acceptance criteria, and the initial backlog.

**Exit condition:** the repository explains what Echo Masque is, what the MVP includes, and how each later phase will be verified.

### Phase 1 — Python foundation

Create the Python package, configuration layer, domain models, health API, local development commands, quality checks, automated tests, and CI.

**Exit condition:** a contributor can install the project, run the API, and pass lint, type-check, and tests without any model credentials.

### Phase 2 — Deterministic trial engine

Implement the target protocol, session state, scenario model, turn runner, deterministic demo targets, rule-based judge, evidence records, and four initial test suites.

**Exit condition:** Stable and Fragile demo characters produce different reproducible verdicts with identifiable breakpoints.

### Phase 3 — Prompt-model target

Add an OpenAI-compatible provider abstraction, credential-safe configuration, structured retries, token and latency accounting, session reset, and model-backed target execution.

**Exit condition:** a user can test one prompt against a configured model while the deterministic suite remains available offline.

### Phase 4 — Persistence and HTTP API

Persist targets, suites, sessions, turns, verdicts, and traces in SQLite. Expose CRUD and run endpoints through FastAPI, including asynchronous run status and session replay.

**Exit condition:** a complete trial can be created, executed, stopped, retrieved, and replayed through documented API calls.

### Phase 5 — Observation interface

Build the web interface for Target Profiles, test-suite selection, live sessions, observation signals, breakpoints, evidence, and replay.

**Exit condition:** a user can understand the product and run the included demo without reading API documentation.

### Phase 6 — External target adapters

Add Custom HTTP Target and transcript import, request/response mapping, reset contracts, authentication handling, timeouts, redaction, and adapter contract tests.

**Exit condition:** Echo Masque can test a complete external chatbot without requiring its prompt or internal implementation.

### Phase 7 — Comparison and hardening

Add prompt/model/version comparisons, regression gates, score calibration, exportable reports, security review, deployment configuration, and an MVP release workflow.

**Exit condition:** users can compare two runs, identify regressions, and reproduce the same evaluation configuration.

## MVP exclusions

The initial MVP intentionally excludes browser automation of third-party chat websites, public leaderboards, automatic prompt rewriting, fine-tuning, a full red-team security platform, production traffic monitoring, and a general-purpose multi-agent simulation framework.

## Technical direction

- Python 3.12+
- FastAPI and Pydantic
- SQLAlchemy with SQLite first
- `httpx` for asynchronous target calls
- `pytest`, Ruff, and mypy
- React and TypeScript for the observation interface in Phase 5
- GitHub Actions for continuous integration

## Repository policy

- Development proceeds in numbered phases.
- Each completed phase is committed and pushed separately.
- Every phase must include tests and an explicit acceptance check.
- The default branch is `main`.
- Model credentials are never committed.

## Status

- [x] Phase 0 — Product contract and roadmap
- [ ] Phase 1 — Python foundation
- [ ] Phase 2 — Deterministic trial engine
- [ ] Phase 3 — Prompt-model target
- [ ] Phase 4 — Persistence and HTTP API
- [ ] Phase 5 — Observation interface
- [ ] Phase 6 — External target adapters
- [ ] Phase 7 — Comparison and hardening
