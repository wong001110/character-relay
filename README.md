# Echo Masque

**See what remains when the role is challenged.**

Echo Masque is a Python-first AI character evaluation workspace. It combines owner-scoped Character Cards, reusable tests, deterministic and model-backed execution, human-controlled calibration, Judge analytics, and a server-enforced review boundary for AI-generated evaluation assets.

## Product loop

```text
Sign in to an isolated workspace
  -> create or select a Character Card
  -> inspect the exact Runtime System Prompt when applicable
  -> author or generate reviewable Scenario/Test Pack Drafts
  -> approve Drafts before they enter execution paths
  -> run Benchmark or Adaptive pressure
  -> judge with Rules, Semantic, or Hybrid mode
  -> preserve immutable Run and Evaluation Snapshots
  -> calibrate PASS / FAIL / REVIEW labels with exact evidence
  -> compare Rubrics and inspect coverage gaps
  -> exchange secret-free evaluation assets without bypassing review
```

## Quick start

Requires Python 3.12+ and Node.js 22+.

```bash
python run.py
```

Open `http://127.0.0.1:5173` for the UI or `http://127.0.0.1:8000/docs` for the API.

```bash
python run.py --install
python run.py --no-install
python run.py --api-only
python run.py --no-reload
```

## Public demo account

A shared read-only account is available on the Production deployment:

```text
URL: https://echo-masque-production.up.railway.app
Email: demo@echo-masque.app
Password: EchoMasqueDemo2026!
```

The Demo workspace is synchronized from the Bootstrap Admin workspace on deployment. It receives the two Live Demo Character Cards plus the Admin's current custom Scenarios and Test Packs. Provider credentials remain encrypted and server-side.

Demo users may inspect Character Prompts, browse the Experiment Workspace, run or cancel tests, rerun experiments, compare results, view reports, and sign out. Character, credential, Scenario, Test Pack, account, Matrix, Authoring, Calibration, Analytics, Template, import, and other shared-workspace mutations are rejected by the server.

The Authoring, Calibration, Judge Analytics, Coverage, and Templates & Sharing navigation is temporarily hidden in the web UI while the public testing flow is being simplified.

## Core capabilities

### Character Library and Runtime Prompt Inspector

Prompt-model Character Cards expose the exact current Runtime System Message, Provider, Model, Temperature, active Prompt Version, and config hash. The Prompt can be copied or exported as:

- plain text;
- Markdown with metadata;
- full secret-free JSON;
- OpenAI-compatible messages JSON.

The Inspector reads the authoritative `PromptModelConfig` used by `PromptModelTarget`. API keys, Environment Secret values, and Vault ciphertext are never exported.

### Test Room and Experiment Workspace

The Test Room supports fixed Benchmark pressure, Admin-managed Adaptive pressure, Rules/Semantic/Hybrid Judge modes, Watch/Fast observation, grounded evidence, breakpoints, immutable Run Snapshots, reports, reruns, baselines, and lineage.

Custom Scenarios and ordered Test Packs support English and Simplified Chinese, expected behavior, required and forbidden signals, severity, bounded turns, and recommended Tester/Judge modes.

### Matrix Lab

Matrix Lab executes controlled combinations of Character/Prompt, Model, Temperature, Pack, Language, Tester, Judge, and repeat count. It includes persistent queue controls, retries, bounded concurrency, repeated-run statistics, compatible regression analysis, Prompt version management, and secret-free JSON/CSV/Markdown exports.

## Phase 16 evaluation-engineering workspace

### Reviewable Authoring

Scenario and Test Pack Drafts carry manual or AI provenance, review notes, risk tags, revisions, rejection, and explicit approval. Drafts do not appear in formal listings and cannot be launched by Trial or Matrix paths.

The encrypted Authoring Runtime performs strict structured generation, allows one bounded correction, rejects duplicate fingerprints, surfaces risk-coverage warnings, and saves every result as a Draft.

### Calibration Lab

Calibration Datasets preserve human-controlled ground truth:

- expected `PASS`, `FAIL`, or `REVIEW`;
- frozen Subject responses;
- exact contiguous evidence excerpts;
- failure types and six coverage dimensions;
- manual Cases or completed Run Turn import;
- immutable approved versions and explicit next versions;
- secret-free Archive export/import.

### Judge Analytics

Approved Dataset versions can be evaluated with Rules, Semantic, and Hybrid Judges. Immutable Evaluation Snapshots preserve Judge configuration metadata, per-Case predictions, evidence, errors, and metrics.

Analytics include confusion matrices, accuracy, precision, recall, Macro F1, false-positive/false-negative rates, Rules/Semantic agreement, and breakdowns by failure type, language, Scenario category, and Character.

### Rubric and Coverage Lab

Semantic Rubrics can be compared only when both Evaluation Snapshots use the same frozen Dataset ID and version. Reports show metric deltas, six Semantic dimension deltas, and per-Case changes.

Coverage is reported across identity, memory, instruction resistance, capability honesty, persona, and language. Missing or weak dimensions can create new AI Draft requests, but nothing is approved automatically.

### Templates and Sharing

Echo Masque includes bilingual templates for identity/memory, instruction/capability, and persona/language testing. Template instantiation creates reviewable Scenario and Test Pack Drafts only.

Versioned Evaluation Share Bundles may include formal Scenario contracts and Test Pack structure. They exclude account data, owner IDs, credentials, Calibration labels, and private Run transcripts. Imports always become Drafts.

## Authentication and credential security

Production uses Argon2 password hashes, opaque server-side Sessions, HttpOnly cookies, invitation-controlled registration, user/Admin roles, owner-scoped resources, encrypted Character and shared Runtime credentials, MultiFernet rotation, redacted Audit Events, and secret-free account export.

Raw keys, encrypted blobs, Session tokens, password hashes, and invitation codes are excluded from exports, snapshots, events, reports, and logs.

## Quotas and abuse controls

Persistent SQLite-backed limits cover requests, login failures, workspace records, Runs, Matrices, daily Matrix tasks, concurrent work, AI Authoring generations, Judge Evaluation Case predictions, template/import operations, and Share Bundle assets.

Blocked requests return `429 Too Many Requests`, with `Retry-After` when applicable.

## Production deployment

Deploy the root `Dockerfile` with `railway.toml`, one replica, and a Railway Volume mounted at `/data`.

Required variables:

```text
ECHO_MASQUE_ENVIRONMENT=production
ECHO_MASQUE_DATABASE_URL=sqlite:////data/echo_masque.db
ECHO_MASQUE_LEGACY_LOCAL_USER_ENABLED=false
ECHO_MASQUE_PUBLIC_REGISTRATION_ENABLED=false
ECHO_MASQUE_BOOTSTRAP_ADMIN_EMAIL=<admin email>
ECHO_MASQUE_BOOTSTRAP_ADMIN_PASSWORD=<long unique password>
ECHO_MASQUE_CREDENTIAL_ENCRYPTION_KEYS=<Fernet key>
```

The Production Docker image sets `ECHO_MASQUE_PUBLIC_DEMO_ENABLED=true`. Set it to `false` in the deployment environment to disable Demo-account provisioning and synchronization.

Optional Phase 16 quota overrides:

```text
ECHO_MASQUE_MAX_AUTHORING_GENERATIONS_PER_DAY=50
ECHO_MASQUE_MAX_EVALUATION_CASES_PER_DAY=1000
ECHO_MASQUE_MAX_TEMPLATE_INSTANTIATIONS_PER_DAY=100
ECHO_MASQUE_MAX_SHARED_ASSETS_PER_BUNDLE=200
```

Keep encryption keys and administrator passwords outside Git. The documented Demo password is intentionally public and belongs only to the server-restricted low-privilege account. Losing every matching Fernet key makes existing encrypted Provider credentials unrecoverable.

## Validation

Pull requests run Ruff, strict mypy, pytest on Python 3.12/3.13, TypeScript, Vitest, the Production web build, Docker persistent-volume smoke, and Railway smoke.

Retained Production workflows:

- **Phase 15 Live Security Smoke** — multi-account isolation, Vault rotation, and export redaction.
- **Phase 16 Live Acceptance** — template Draft boundaries, secret-free Share Bundles, exact Runtime Prompt inspection and four exports, Calibration, Rules Evaluation, Coverage, and temporary-account cleanup.

Phase 16 Production acceptance passed on merge commit `b341f45d77ec6bb25ad883de86f147ade4267ffd`.

## Delivery status

- [x] Phases 0–15 — secure authenticated evaluation platform
- [x] Phase 16A — reviewable Draft foundation
- [x] Phase 16B — AI-assisted Authoring Runtime and Lab
- [x] Phase 16C — human-controlled Calibration Datasets
- [x] Phase 16D — immutable Judge Evaluation Analytics
- [x] Phase 16E — Rubric comparison and coverage analytics
- [x] Phase 16F — templates, sharing, quotas, migration, and Production release gate

**Phase 16 is complete.** See `CHECKLIST.md` and Issue #45 for the retained acceptance record.

## Documentation

- `docs/phase-15-security.md`
- `docs/phase-16-authoring.md`
- `docs/phase-16-ai-authoring.md`
- `docs/phase-16-calibration.md`
- `docs/phase-16-rubric-coverage.md`
- `docs/phase-16-release.md`
- `docs/railway-deployment.md`
