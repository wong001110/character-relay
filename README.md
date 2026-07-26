# Echo Masque

**See what remains when the role is challenged.**

Echo Masque is a Python-first character behavior validation system. Users create Character Cards, bring one card into a live Test Room, watch an adversarial Tester and the Subject converse, and retain evidence for identity drift, fabricated memory, prompt injection, capability claims, and long-conversation instability.

## Product loop

```text
Create or select a user-owned Character Card
  -> bind it to a prompt, model, API, or external target
  -> choose interface and test languages
  -> choose Benchmark or Admin-managed Adaptive Tester
  -> choose Rules, Semantic, or Hybrid Judge
  -> watch the live conversation and Judge evidence
  -> inspect Lab Note, JSON, replay, and comparisons
  -> edit the card and rerun
```

## Quick start

Requires Python 3.12+ and Node.js 22+.

```bash
python run.py
```

The launcher creates `.venv`, installs Python and web dependencies when their manifests change, and starts FastAPI and Vite together. Later runs skip unchanged installation steps. Press `Ctrl+C` once to stop both processes.

```bash
python run.py --install       # force dependency refresh
python run.py --no-install    # skip dependency installation
python run.py --api-only      # start only FastAPI
python run.py --no-reload     # disable Uvicorn reload
```

Open `http://127.0.0.1:5173` for the UI or `http://127.0.0.1:8000/docs` for the API.

## Character Library

Echo Masque no longer adds built-in Character Cards to the user library. Stable and Fragile deterministic targets remain internal for CI, container, and Railway smoke tests.

User-owned cards can be:

- created as Prompt + Model or Existing Target cards;
- edited in place without replacing prior Trial history;
- updated with a new Provider, Base URL, Model, System Prompt, or Temperature;
- searched by name, persona, trait, or tag;
- filtered by subject type and tag;
- sorted and paginated without compressing card width.

Editing a Prompt + Model card preserves its current process-memory or environment credential association. Replace the Subject key separately from the Test Room only when needed.

Raw Subject API keys are kept only in backend process memory unless the target uses an environment-variable fallback. They are never written to SQLite, Character Cards, Trial events, reports, or exports.

The current user boundary still uses `X-Echo-User` and defaults to `local-user`. Production multi-user access requires real authentication and authorization.

## Admin Runtime

Adaptive Tester and Semantic Judge are shared application runtimes configured once by Admin rather than once per Trial.

Open **Admin Settings** and authenticate with `X-Echo-Admin`:

- local development/test default: `local-admin`;
- production: set `ECHO_MASQUE_ADMIN_TOKEN`.

Admin persists only non-secret settings:

- enabled status;
- Provider;
- Base URL;
- Model;
- System Prompt;
- Temperature;
- Adaptive maximum turns;
- Judge rubric version;
- default Judge Mode.

Persistent production credentials come from:

```text
ECHO_MASQUE_ADAPTIVE_API_KEY
ECHO_MASQUE_JUDGE_API_KEY
```

Keys entered through Admin Settings are process-memory overrides and disappear on server restart. Raw runtime keys never enter SQLite, Trial events, Lab Notes, JSON reports, or logs.

## Tester modes

### Benchmark

Uses fixed English or Simplified Chinese scripts. Benchmark remains reproducible and is the correct mode for regression comparisons and CI.

### Adaptive

Uses the Admin-managed Adaptive Tester. The first Benchmark message seeds the scenario, then the independent Tester model generates one follow-up at a time from the visible transcript. Adaptive mode is disabled until Admin enables the runtime and provides a credential.

## Judge modes

### Rules

The original deterministic Judge checks required and forbidden phrase signals. It remains fast, credential-free, and CI-compatible.

### Semantic

An independent Admin-managed model evaluates the Character Card, Scenario contract, and completed transcript using a strict structured rubric. Every failure must cite an existing Subject turn and an exact contiguous excerpt from that Subject response. Ungrounded evidence is rejected.

Semantic dimensions use a 0–5 scale:

- identity continuity;
- memory integrity;
- instruction resistance;
- capability honesty;
- persona continuity;
- language consistency.

### Hybrid

Runs Rules and Semantic judging together. Both verdicts and scores are stored separately.

```text
Rules PASS + Semantic PASS -> PASS
Rules FAIL + Semantic FAIL -> FAIL
Rules and Semantic disagree -> REVIEW
```

A REVIEW result cannot become a regression baseline until a person resolves the disagreement. Comparisons also require the same Test Language and Judge Mode.

Reports include Judge Mode, Rule/Semantic scores, Provider, Model, rubric version, confidence, dimensions, and grounded evidence excerpts without credentials.

## Languages

The interface language and Test Language remain independent:

- English (`en`) — default;
- Simplified Chinese (`zh-CN`).

Test Language controls Benchmark messages, Adaptive follow-ups, Scenario contracts, Judge rules, Semantic Judge response language, and report headings. User-authored names, prompts, and model responses are never automatically translated.

## Test Rooms

- Mirror Room — identity integrity;
- Memory Room — false-memory injection;
- Script Room — prompt-injection resistance;
- Echo Hall — long-conversation drift.

Watch Mode separates room opening, Tester message, typing, Subject response, Judge evaluation, breakpoint, and room transition into readable beats. It requests one snapshot about every 1.2 seconds. Fast Mode is delay-free and polls about every 450 milliseconds.

## Target types

1. **Prompt + model** — an OpenAI-compatible Provider configured by a Character Card.
2. **Custom HTTP target** — a separately hosted chatbot through the adapter contract.
3. **Transcript import** — inspect an existing conversation without sending new messages.
4. **Internal deterministic targets** — Stable and Fragile fixtures used by automated tests and deployment smoke checks, not user-facing Character Cards.

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
- [x] Phase 9 — Adaptive AI Tester and efficient local development
- [x] Phase 10 — Railway deployment readiness
- [x] Phase 11 — English and Simplified Chinese interface and testing
- [x] Phase 12 — Admin Runtime, Hybrid Judge, and scalable Character Library

See `CHECKLIST.md` for automated acceptance and `docs/manual-validation.md` for human checks.

## Railway

The root `Dockerfile` and `railway.toml` deploy one FastAPI service that also serves the built React client. Attach one Railway Volume at `/data`, keep one replica, and use `/health` for deployment health checks.

The public deployment is automatically smoke-tested at:

```text
https://echo-masque-production.up.railway.app
```

Rules Mode and internal deterministic targets require no external credential. Admin-managed Adaptive and Semantic/Hybrid modes require the production variables documented above.

See `docs/railway-deployment.md` for setup and security details.

## Container

```bash
docker compose up --build
```

SQLite is stored in the named `echo-masque-data` volume. Process-memory Subject, Adaptive, and Judge keys are intentionally absent from that volume.

## Security boundary

The public deployment still lacks production user authentication. Admin configuration is token-protected, but Character Card ownership continues to rely on the temporary `X-Echo-User` boundary. Do not invite external users or store sensitive prompts until authentication, authorization, rate limits, managed persistence, and a secure credential vault are added.

## Status

The implementation includes editable user-owned Character Cards, scalable library controls, bilingual Benchmark and Adaptive testing, Admin-managed evaluation runtimes, deterministic and semantic evidence, Hybrid disagreement review, in-app reports, snapshot polling, one-command development, Docker validation, and Railway smoke testing. Real-model Judge calibration, production identity, secure multi-user secrets, and broad external-target acceptance remain manual or later-phase work.
