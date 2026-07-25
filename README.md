# Echo Masque

**See what remains when the role is challenged.**

Echo Masque is a Python-first character behavior validation system. Users keep the conversational systems they need to test as Character Cards, bring one card into a live Test Room, watch an adversarial Tester and the subject converse, and retain evidence for identity drift, fabricated memory, prompt injection, and long-conversation instability.

## Product loop

```text
Create or select a Character Card
  -> bind it to a prompt, model, API, or deterministic target
  -> choose an interface language and an independent test language
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

Benchmark mode uses fixed scenario scripts. It remains deterministic and is the correct mode for prompt-version comparisons, regression gates, CI, and repeatable scores.

### Adaptive Tester

Adaptive mode keeps the first benchmark message as the scenario seed, then uses a separate AI provider to generate one targeted follow-up at a time from the visible Tester/Subject transcript. Configuration includes provider, base URL, model, system prompt, temperature, maximum turns, and a one-run API key.

The Adaptive Tester is independent from the Subject and deterministic Judge. Its key is stored only while the active run is being prepared or executed. It is never written to SQLite, events, reports, or target configuration. Adaptive pressure stops when the Subject produces a clear forbidden-phrase fracture or reaches the configured turn limit.

## Languages

Echo Masque separates the language of the product interface from the language of the actual AI evaluation.

### Interface language

- English (`en`) — default
- Simplified Chinese (`zh-CN`)

The selection is stored in the browser and restored on refresh. It translates navigation, forms, room controls, status labels, observation notes, and modal copy.

Character names, card content, System Prompts, imported transcripts, model responses, and provider errors remain in their original form and are not automatically translated.

### Test language

The Test Room has a separate Test Language selector. English and Simplified Chinese each have their own:

- fixed Benchmark Tester messages;
- scenario names and expected-behaviour contracts;
- forbidden and required phrase rules;
- Stable and Fragile deterministic demo responses;
- Adaptive Tester context and output-language instructions;
- Judge summaries and evidence messages;
- trial report headings and scenario content.

Every run records `test_language`. Existing persisted runs are treated as English. Regression comparison only accepts runs that use the same test language.

See `docs/multilingual-testing.md` for the language boundary, coverage, and extension process.

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
- [x] Phase 10 — Railway deployment readiness
- [ ] Phase 11 — English and Simplified Chinese interface and testing

See `CHECKLIST.md` for automated acceptance and `docs/manual-validation.md` for human checks.

## Current capabilities

- Manage per-user Character Cards bound to deterministic, prompt-model, or external targets.
- Configure provider, base URL, model, system prompt, temperature, and an ephemeral API key from the card creator.
- Reconfigure a provider key from the Test Room after a backend restart.
- Switch the interface between English and Simplified Chinese.
- Run independent English or Simplified Chinese behavior suites.
- Run four behavior suites against Stable and Fragile built-in subjects.
- Choose fixed Benchmark testing or experimental Adaptive AI pressure.
- Keep Adaptive Tester follow-ups in the selected test language.
- Observe persisted Tester, Subject, Judge, and Breakpoint events in a chatroom UI.
- Choose Watch Mode for paced viewing or Fast Mode for developer workflows.
- Test prompt-and-model targets through an OpenAI-compatible provider.
- Test complete external chatbots through the Custom HTTP Target contract.
- Import JSON, CSV, or Markdown transcripts for offline inspection.
- Persist sessions, language, events, evidence, breakpoints, Trace, and replay in SQLite.
- Compare deterministic Benchmark runs within the same test language.
- View and export redacted Markdown and JSON reports.
- Build one production image containing both the React client and FastAPI service.

## Railway

The repository includes a root `Dockerfile` and `railway.toml`. Railway builds the React client and serves it through FastAPI from the same service. The container listens on Railway's injected `$PORT`, and `/health` is configured as the deployment healthcheck.

Attach one Railway Volume at `/data` and keep the service at one replica. SQLite is stored at `/data/echo_masque.db`.

The live deployment is automatically smoke-tested at:

```text
https://echo-masque-production.up.railway.app
```

The Railway Smoke workflow checks health, static UI delivery, demo target availability, and a real Stable Benchmark Trial after each update to `main`.

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

The implementation includes Character Cards, live observation, provider-backed Subject testing, experimental Adaptive Tester pressure, bilingual interface scaffolding, bilingual deterministic evaluation, in-app reports, lower-frequency snapshot polling, a single-command development launcher, and an automatically smoke-tested Railway deployment. Visual polish, real-provider multilingual quality, authentication, external-host, cross-platform launcher, and final browser acceptance remain explicitly tracked rather than being hidden behind automated pass claims.
