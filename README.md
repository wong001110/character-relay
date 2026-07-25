# Echo Masque

**See what remains when the role is challenged.**

Echo Masque is a Python-first character behavior validation system. Users keep the conversational systems they need to test as Character Cards, bring one card into a live Test Room, watch an adversarial Tester and the subject converse, and retain evidence for identity drift, fabricated memory, prompt injection, and long-conversation instability.

## Product loop

```text
Create or select a Character Card
  -> bind it to a prompt, model, API, or deterministic target
  -> enter a Test Room
  -> watch Tester and subject messages arrive live
  -> read Judge notes and the first breakpoint
  -> inspect replay, reports, and comparisons
  -> change the character configuration and rerun
```

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install -e ".[dev]"
python -m pytest
python -m echo_masque.cli run-demo --target fragile --suite all
python -m uvicorn echo_masque.main:app --reload
```

Open `http://127.0.0.1:8000/docs` or call `GET /health`.

## Character Cards

Character Cards keep user-facing identity information separate from technical target bindings. A card contains its persona summary, traits, expected tone, memory boundary, forbidden behaviours, preferred test rooms, and portrait palette. The target continues to own credentials and execution configuration.

The current local MVP scopes cards with the `X-Echo-User` header and defaults to `local-user`. Production deployments should replace this boundary with authenticated identity and authorization.

## Target types

1. **Deterministic demo** — credential-free Stable and Fragile characters.
2. **Prompt + model** — Echo Masque calls an OpenAI-compatible model.
3. **Custom HTTP target** — a complete external chatbot through an adapter contract.
4. **Transcript import** — inspect an existing conversation without sending new messages.

## Test Rooms

- Mirror Room — identity integrity
- Memory Room — false-memory injection
- Script Room — prompt-injection resistance
- Echo Hall — long-conversation drift

Watch Mode intentionally paces deterministic conversations so the session can be observed. Fast Mode emits the same persisted event sequence without presentation delays.

## Delivery phases

- [x] Phase 0 — Product contract and roadmap
- [x] Phase 1 — Python foundation
- [x] Phase 2 — Deterministic trial engine
- [x] Phase 3 — Prompt-model target
- [x] Phase 4 — Persistence and HTTP API
- [x] Phase 5 — Observation interface
- [x] Phase 6 — External target adapters
- [x] Phase 7 — Comparison and hardening
- [x] Phase 8 — Character Cards and Live Test Room

See `CHECKLIST.md` for automated acceptance and `docs/manual-validation.md` for human checks.

## Current capabilities

- Manage per-user Character Cards bound to existing targets.
- Run four behavior suites against Stable and Fragile built-in subjects.
- Observe persisted Tester, Subject, Judge, and Breakpoint events in a chatroom UI.
- Choose Watch Mode for paced viewing or Fast Mode for developer workflows.
- Test prompt-and-model targets through an OpenAI-compatible provider.
- Test complete external chatbots through the Custom HTTP Target contract.
- Import JSON, CSV, or Markdown transcripts for offline inspection.
- Persist sessions, events, evidence, breakpoints, Trace, and replay in SQLite.
- Compare two completed runs and enforce regression thresholds.
- Export redacted Markdown and JSON reports.

## Web interface

```bash
# terminal 1
python -m uvicorn echo_masque.main:app --reload

# terminal 2
cd web
npm install
npm run dev
```

After `npm run build`, FastAPI serves `web/dist` from the root path.

## Container

```bash
docker compose up --build
```

The SQLite database is stored in the named `echo-masque-data` volume.

## MVP exclusions

The MVP excludes browser automation of third-party chat websites, public leaderboards, automatic prompt rewriting, fine-tuning, production traffic monitoring, and a general-purpose multi-agent simulation framework.

## Status

The automated product implementation now includes Character Cards and a live observation room. Visual polish, real-provider, external-host, and end-to-end release checks remain explicitly tracked rather than being hidden behind automated pass claims.
