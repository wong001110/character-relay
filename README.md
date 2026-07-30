# Echo Masque

**See what remains when the role is challenged.**

Echo Masque is a Python-first character behavior validation system. Users create Character Cards, define reusable test scenarios, compose Test Packs, run Benchmark or Adaptive pressure, and retain grounded evidence for identity drift, fabricated memory, prompt injection, capability claims, and long-conversation instability.

## Product loop

```text
Create or select a user-owned Character Card
  -> create language-specific Scenarios
  -> compose a versioned Test Pack
  -> choose Benchmark or Admin-managed Adaptive Tester
  -> choose Rules, Semantic, or Hybrid Judge
  -> run the pack and preserve an immutable configuration snapshot
  -> inspect Experiment History, reports, baselines, and reruns
  -> edit the card or pack without changing old experiment meaning
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

Echo Masque does not add built-in Character Cards to the user library. Stable and Fragile deterministic targets remain internal for CI, container, and Railway smoke tests.

User-owned cards can be:

- created as Prompt + Model or Existing Target cards;
- edited in place without replacing prior Trial history;
- updated with a new Provider, Base URL, Model, System Prompt, or Temperature;
- searched by name, persona, trait, or tag;
- filtered by subject type and tag;
- sorted and paginated without compressing card width.

Editing a Prompt + Model card preserves its current process-memory or environment credential association. Replace the Subject key separately from the Test Room only when needed.

Raw Subject API keys are kept only in backend process memory unless the target uses an environment-variable fallback. They are never written to SQLite, Character Cards, Trial events, reports, snapshots, or workspace exports.

The current user boundary still uses `X-Echo-User` and defaults to `local-user`. Production multi-user access requires real authentication and authorization.

## Experiment Workspace

Open **Workspace** from the Character Library. The workspace contains four areas.

### Custom Scenarios

A Scenario stores:

- category and description;
- English or Simplified Chinese Test Language;
- one or more initial Tester messages;
- expected behavior;
- required and forbidden signals;
- severity;
- maximum Adaptive turns;
- recommended Tester and Judge modes.

Scenarios support create, edit, duplicate, and delete. Scenario ownership follows `X-Echo-User`.

### Test Packs

A Test Pack is an ordered, versioned collection of Scenarios. Each item may be enabled or disabled without deleting the Scenario. Editing a pack increments its version.

The Workspace includes a Test Pack launcher for selecting:

- Character Card;
- Test Pack;
- Test Language;
- Benchmark or Adaptive Tester;
- Rules, Semantic, or Hybrid Judge;
- Fast or Watch pacing.

The existing four Test Rooms remain available as a fast fixed-suite path.

### Immutable Run snapshots

Every Phase 13 Run freezes:

- Character Card profile;
- Target Provider, Model, System Prompt, Temperature, and endpoint configuration;
- Test Pack name and version;
- ordered Scenario definitions;
- language, Tester Mode, and Judge Mode.

Editing or deleting current cards, packs, or scenarios does not rewrite an old Run snapshot. Reports and reruns therefore retain the configuration that was actually tested.

API keys and Admin tokens are never included in snapshots.

### Experiment History

Experiment History provides:

- pagination;
- Character, Test Pack, language, Tester, and Judge filters;
- score, PASS, FAIL, REVIEW, and run status;
- report access;
- rerun from the frozen snapshot;
- compatible baseline marking;
- experiment deletion.

Phase 13 history begins with Runs that contain immutable snapshots. Earlier Run reports remain accessible by their Run IDs but are not presented as reproducible Phase 13 experiments.

## Persistence and workspace backup

The **Storage & Backup** tab is Admin-protected. It shows:

- effective database backend and path;
- writeability;
- whether production SQLite is under `/data`;
- Character, Scenario, Pack, and Run counts;
- last workspace write time;
- a prominent warning when production SQLite is not persistent.

### Persistence probe

Create a probe, copy its ID, redeploy Railway, and check the same ID afterward. Delete the probe after the verification. This proves that the active deployment is reading the same persistent database rather than only checking that a Volume exists.

### Workspace export and import

Admin may export a JSON archive containing:

- user-owned targets and Character Cards;
- Custom Scenarios and Test Packs;
- snapshotted Trial Runs;
- turns, events, evidence, and reports;
- non-secret Admin Runtime configuration.

The archive excludes Subject, Adaptive, and Judge API keys and the Admin token. Import supports merge or replace mode.

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

Keys entered through Admin Settings are process-memory overrides and disappear on server restart. Raw runtime keys never enter SQLite, Trial events, Lab Notes, JSON reports, snapshots, workspace exports, or logs.

## Tester modes

### Benchmark

Uses fixed or user-authored English or Simplified Chinese scripts. Benchmark remains reproducible and is the correct mode for regression comparisons and CI.

### Adaptive

Uses the Admin-managed Adaptive Tester. The first Scenario message seeds the pressure sequence, then the independent Tester model generates one follow-up at a time from the visible transcript. The effective turn limit is the lower of the Admin maximum and the selected Scenario limits.

## Judge modes

### Rules

The deterministic Judge checks required and forbidden phrase signals. It remains fast, credential-free, and CI-compatible.

### Semantic

An independent Admin-managed model evaluates the Character Card snapshot, Scenario contract, and completed transcript using a strict structured rubric. Every failure must cite an existing Subject turn and an exact contiguous excerpt from that Subject response. Ungrounded evidence is rejected.

Semantic dimensions use a 0–5 scale:

- identity continuity;
- memory integrity;
- instruction resistance;
- capability honesty;
- persona continuity;
- language consistency.

Python calculates the canonical 0–100 Semantic score from those dimensions. Model-authored score and pass/fail fields do not control the result.

A provider formatting error receives at most one bounded correction attempt. The corrected output must still pass the same strict JSON, consistency, and exact-evidence grounding checks; fuzzy or paraphrased evidence is never accepted.

### Hybrid

Runs Rules and Semantic judging together. Both verdicts and scores are stored separately.

```text
Rules PASS + Semantic PASS -> PASS
Rules FAIL + Semantic FAIL -> FAIL
Rules and Semantic disagree -> REVIEW
```

A REVIEW result cannot become a regression baseline until a person resolves the disagreement. Comparisons require the same Test Language and Judge Mode.

## Languages

The interface language and Test Language remain independent:

- English (`en`) — default;
- Simplified Chinese (`zh-CN`).

Test Language controls Benchmark messages, Adaptive follow-ups, Scenario contracts, Judge rules, Semantic Judge response language, and report headings. User-authored names, prompts, and model responses are never automatically translated.

## Target types

1. **Prompt + model** — an OpenAI-compatible Provider configured by a Character Card.
2. **Custom HTTP target** — a separately hosted chatbot through the adapter contract.
3. **Transcript import** — inspect an existing conversation without sending new messages.
4. **Internal deterministic targets** — Stable and Fragile fixtures used by automated tests and deployment smoke checks, not user-facing Character Cards.

## Delivery phases

### Completed

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
- [x] Phase 13 — Custom Test Packs, Experiment History, and persistence guardrails
- [x] Production release gate — Railway Volume-backed SQLite, persistent Live Demo data, real Adaptive + Hybrid validation, and bounded Semantic evidence repair
- [x] Phase 14 — Batch Experiment Matrix and Comparative Analytics

### Planned

- [ ] Phase 15 — Authentication, User Isolation, and Secure Credential Vault
- [ ] Phase 16 — AI-generated Scenario Authoring, Calibration Datasets, and Evaluation Analytics

See `CHECKLIST.md` for automated acceptance and `docs/manual-validation.md` for human checks.

## Forward roadmap

The roadmap is directional. Each phase receives a dedicated issue and acceptance checklist before implementation, and scope may be adjusted when production evidence exposes a higher-priority reliability or security problem.

### Phase 14 — Batch Experiment Matrix and Comparative Analytics

Phase 14 turns one-at-a-time experiments into controlled batches across:

- Character Card or Prompt version;
- Provider and Model;
- Temperature;
- Test Pack and Test Language;
- Benchmark or Adaptive Tester;
- Rules, Semantic, or Hybrid Judge;
- repeat count.

Implemented deliverables:

- Matrix CRUD and a run-count preview before execution;
- a SQLite-backed queue with concurrency limits, pause, resume, cancellation, retries, and provider backoff;
- repeated-run statistics including mean, minimum, maximum, pass rate, review rate, failure rate, and variance;
- comparison views for Prompt, Model, Temperature, Language, Tester, and Judge combinations;
- Prompt version history with diff, restore, and production-version marking;
- baseline regression summaries;
- token, latency, provider-error, and retry aggregation;
- CSV, JSON, and Markdown export.

Phase 14 is available through the bilingual **Matrix Lab**. The server requires an exact run-count confirmation before launch, enforces a 200-task cap, persists queue state in SQLite, and pauses interrupted work after restart. Phase 14 does not introduce public accounts, billing, a distributed worker fleet, or a Scenario marketplace.

See `docs/phase-14-experiment-matrix.md` for the execution, analytics, regression, and export contracts.

### Phase 15 — Authentication, User Isolation, and Secure Credential Vault

Phase 15 makes the public deployment suitable for multiple real users.

Planned deliverables:

- production authentication and session management;
- server-enforced workspace ownership instead of trusting `X-Echo-User`;
- role-based Admin authorization;
- secure encrypted credential storage and rotation;
- per-user rate limits, quotas, and abuse controls;
- audit events for sensitive configuration changes;
- managed production persistence and migration tooling;
- safe invitation, account deletion, and workspace export flows.

Phase 15 is the security boundary required before the public deployment is promoted as a general multi-user service.

### Phase 16 — AI-generated Scenario Authoring, Calibration Datasets, and Evaluation Analytics

Phase 16 adds assisted evaluation design without allowing generated content to silently become ground truth.

Planned deliverables:

- AI-assisted Scenario and Test Pack drafting from Character Cards and known risks;
- human approval and versioning before generated tests can run;
- calibration datasets with expected verdicts and grounded evidence;
- Judge agreement, disagreement, false-positive, and false-negative analysis;
- rubric-version comparison and calibration reports;
- coverage analysis across identity, memory, instruction resistance, capability honesty, persona, and language;
- reusable evaluation templates and shareable, secret-free test assets.

Generated Scenarios and Judge recommendations remain reviewable artifacts. Deterministic validation and human-approved calibration data remain the authority.

## Railway

The root `Dockerfile` and `railway.toml` deploy one FastAPI service that also serves the built React client. Attach one Railway Volume at `/data`, keep one replica, and use `/health` for deployment health checks.

The required SQLite setting is:

```text
ECHO_MASQUE_DATABASE_URL=sqlite:////data/echo_masque.db
```

The public deployment is automatically smoke-tested at:

```text
https://echo-masque-production.up.railway.app
```

Rules Mode and internal deterministic targets require no external credential. Admin-managed Adaptive and Semantic/Hybrid modes require the production variables documented above.

The Railway deployment has been validated with Volume-backed SQLite across application deployments. Continue using Storage Diagnostics, the stable storage instance ID, and persistence probes when changing the Railway service, environment, database path, or Volume attachment.

See `docs/railway-deployment.md` for setup and security details.

## Container

```bash
docker compose up --build
```

SQLite is stored in the named `echo-masque-data` volume. Process-memory Subject, Adaptive, and Judge keys are intentionally absent from that volume.

## Security boundary

The public deployment still lacks production user authentication. Admin configuration and workspace portability are token-protected, but Character ownership continues to rely on the temporary `X-Echo-User` boundary. Do not invite external users or store sensitive prompts until authentication, authorization, rate limits, managed persistence, and a secure credential vault are added.

## Status

Phase 14 and the production release gate are complete. Echo Masque now supports user-authored Scenarios, versioned Test Packs, immutable Run snapshots, Experiment History, Prompt version history, controlled batch Matrices, a persistent queue, repeated-run statistics, regression comparisons, and secret-free Matrix exports.

The retained Live Demo verifies the intended Stable/OOC contrast under real Adaptive + Hybrid execution. A separate retained Live Matrix validates the Phase 14 production API, Temperature variants, persisted tasks, and aggregate analytics. The next implementation phase is Phase 15 — Authentication, User Isolation, and Secure Credential Vault.
