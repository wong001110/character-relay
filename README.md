# Echo Masque

**See what remains when the role is challenged.**

Echo Masque is a Python-first character behavior validation system. Users keep the conversational systems they need to test as Character Cards, bring one card into a live Test Room, watch an adversarial Tester and the subject converse, and retain evidence for identity drift, fabricated memory, prompt injection, and long-conversation instability.

## Product loop

```text
Create or select a Character Card
  -> bind it to a prompt, model, API, or deterministic target
  -> choose Benchmark or Adaptive Tester
  -> enter a Test Room
  -> watch Tester and subject messages arrive live
  -> read Judge notes and the first breakpoint
  -> inspect Lab Note, JSON, replay, and comparisons
  -> change the character configuration and rerun
```

## Quick start

Requires Python 3.12+ and Node.js 22+.

```bash
python run.py
```

The launcher creates `.venv`, installs Python and web dependencies when their manifests change, and starts both FastAPI and Vite. Later runs skip unchanged installation steps. Press `Ctrl+C` once to stop both processes.

Useful options:

```bash
python run.py --install       # force dependency refresh
python run.py --no-install    # skip dependency installation
python run.py --api-only      # start only FastAPI
python run.py --no-reload     # disable Uvicorn reload
```

Open `http://127.0.0.1:5173` for the UI or `http://127.0.0.1:8000/docs` for the API.

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

## Tester modes

### Benchmark Tester

Benchmark mode uses the fixed scenario scripts. It remains deterministic and is the correct mode for prompt-version comparisons, regression gates, CI, and repeatable scores.

### Adaptive Tester

Adaptive mode keeps the first benchmark message as the scenario seed, then uses a separate AI provider to generate one targeted follow-up at a time from the visible Tester/Subject transcript. Configuration includes provider, base URL, model, system prompt, temperature, maximum turns, and a one-run API key.

The Adaptive Tester is independent from the Subject and deterministic Judge. Its key is stored only while the active run is being prepared or executed. It is never written to SQLite, events, reports, or target configuration. Adaptive pressure stops when the Subject produces a clear forbidden-phrase fracture or reaches the configured turn limit.

## Test Rooms

- Mirror Room — identity integrity
- Memory Room — false-memory injection
- Script Room — prompt-injection resistance
- Echo Hall — long-conversation drift

Watch Mode separates room opening, Tester message, typing, Subject response, Judge memo, breakpoint, and room transition into readable beats. Its live snapshot request runs about once every 1.2 seconds. Fast Mode is delay-free and polls about every 450 milliseconds. Each request returns both run state and incremental events, replacing the previous two-request loop.

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
- [x] Phase 9 — Adaptive AI Tester and efficient local development
- [ ] Phase 10 — Railway deployment readiness

See `CHECKLIST.md` for automated acceptance and `docs/manual-validation.md` for human checks.

## Current capabilities

- Manage per-user Character Cards bound to deterministic, prompt-model, or external targets.
- Configure provider, base URL, model, system prompt, temperature, and an ephemeral API key from the card creator.
- Reconfigure a provider key from the Test Room after a backend restart.
- Run four behavior suites against Stable and Fragile built-in subjects.
- Choose fixed Benchmark testing or experimental Adaptive AI pressure.
- Observe persisted Tester, Subject, Judge, and Breakpoint events in a chatroom UI.
- Choose Watch Mode for paced viewing or Fast Mode for developer workflows.
- Test prompt-and-model targets through an OpenAI-compatible provider.
- Test complete external chatbots through the Custom HTTP Target contract.
- Import JSON, CSV, or Markdown transcripts for offline inspection.
- Persist sessions, events, evidence, breakpoints, Trace, and replay in SQLite.
- Compare deterministic Benchmark runs and enforce regression thresholds.
- View and export redacted Markdown and JSON reports.
- Build one production image containing both the React client and FastAPI service.

## Railway

The repository includes a root `Dockerfile` and `railway.toml`. Railway builds the React client and serves it through FastAPI from the same service. The container listens on Railway's injected `$PORT`, and `/health` is configured as the deployment healthcheck.

Attach one Railway Volume at `/data` and keep the service at one replica. SQLite is stored at `/data/echo_masque.db`.

After a public domain is generated, validate it with:

```bash
python scripts/railway_smoke.py https://your-service.up.railway.app
```

See `docs/railway-deployment.md` for the full setup, persistence checks, GitHub Actions smoke workflow, and security limitations.

**Security:** the current MVP has no production authentication. Treat a public Railway URL as a deterministic demo and do not enter valuable provider keys or private character data.

## Container

```bash
docker compose up --build
```

The SQLite database is stored in the named `echo-masque-data` volume. Provider keys entered through the UI are intentionally not stored in that volume.

## MVP exclusions

The MVP excludes browser automation of third-party chat websites, public leaderboards, automatic prompt rewriting, fine-tuning, production traffic monitoring, and a general-purpose multi-agent simulation framework.

## Status

The automated product implementation includes Character Cards, live observation, provider-backed Subject testing, experimental Adaptive Tester pressure, in-app reports, lower-frequency snapshot polling, and a single-command development launcher. Railway deployment configuration is being validated. Visual polish, real-provider, authentication, external-host, cross-platform launcher, and end-to-end release checks remain explicitly tracked rather than being hidden behind automated pass claims.
