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
  -> inspect Lab Note, JSON, replay, and comparisons
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

Character Cards keep user-facing identity information separate from technical target bindings. A card contains its persona summary, traits, expected tone, memory boundary, forbidden behaviours, preferred test rooms, and portrait palette.

The card creator supports two binding paths:

1. **Prompt + Model** — choose DeepSeek, OpenAI, OpenRouter, or a custom OpenAI-compatible endpoint; provide the base URL, model ID, system prompt, temperature, and API key.
2. **Existing Target** — bind the card to a deterministic demo or a target already configured through the API.

Raw provider API keys are kept only in backend process memory. They are never written to SQLite, Character Cards, trial events, Lab Notes, JSON reports, or target exports. Restarting the backend clears the key and the Test Room asks the user to configure it again. An environment variable may still supply the configured target's fallback key for local development.

The current local MVP scopes cards with the `X-Echo-User` header and defaults to `local-user`. Production deployments should replace this boundary with authenticated identity and authorization.

## Target types

1. **Deterministic demo** — credential-free Stable and Fragile characters.
2. **Prompt + model** — Echo Masque calls an OpenAI-compatible provider using the model configuration attached to the card.
3. **Custom HTTP target** — a complete external chatbot through an adapter contract.
4. **Transcript import** — inspect an existing conversation without sending new messages.

## Test Rooms

- Mirror Room — identity integrity
- Memory Room — false-memory injection
- Script Room — prompt-injection resistance
- Echo Hall — long-conversation drift

Watch Mode separates room opening, Tester message, typing, Subject response, Judge memo, breakpoint, and room transition into readable beats. Fast Mode emits the same persisted event sequence without presentation delays.

Completed sessions expose Lab Note and JSON buttons in the Observation sidebar. Both reports open inside the application as modals and retain copy and download actions.

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

- Manage per-user Character Cards bound to deterministic, prompt-model, or external targets.
- Configure provider, base URL, model, system prompt, temperature, and an ephemeral API key from the card creator.
- Reconfigure a provider key from the Test Room after a backend restart.
- Run four behavior suites against Stable and Fragile built-in subjects.
- Observe persisted Tester, Subject, Judge, and Breakpoint events in a chatroom UI.
- Choose Watch Mode for paced viewing or Fast Mode for developer workflows.
- Test prompt-and-model targets through an OpenAI-compatible provider.
- Test complete external chatbots through the Custom HTTP Target contract.
- Import JSON, CSV, or Markdown transcripts for offline inspection.
- Persist sessions, events, evidence, breakpoints, Trace, and replay in SQLite.
- Compare two completed runs and enforce regression thresholds.
- View and export redacted Markdown and JSON reports.

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

The SQLite database is stored in the named `echo-masque-data` volume. Provider keys entered through the UI are intentionally not stored in that volume.

## MVP exclusions

The MVP excludes browser automation of third-party chat websites, public leaderboards, automatic prompt rewriting, fine-tuning, production traffic monitoring, and a general-purpose multi-agent simulation framework.

## Status

The automated product implementation includes Character Cards, live observation, provider-backed prompt testing, and in-app report viewing. Visual polish, real-provider, external-host, and end-to-end release checks remain explicitly tracked rather than being hidden behind automated pass claims.
