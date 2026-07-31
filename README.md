# Echo Masque

**See what remains when the role is challenged.**

Echo Masque is a Python-first AI character evaluation workspace. It combines owner-scoped Character Cards, reusable Scenarios and Test Packs, deterministic and model-backed testing, human-controlled calibration, Judge analytics, and a server-enforced review boundary for AI-generated evaluation assets.

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
  -> calibrate expected PASS / FAIL / REVIEW labels with exact evidence
  -> compare Rubrics, inspect coverage gaps, and generate new Drafts
  -> share secret-free evaluation assets without bypassing review
```

## Quick start

Requires Python 3.12+ and Node.js 22+.

```bash
python run.py
```

The launcher creates `.venv`, installs changed dependencies, and starts FastAPI and Vite. Open `http://127.0.0.1:5173` for the UI or `http://127.0.0.1:8000/docs` for the API.

```bash
python run.py --install
python run.py --no-install
python run.py --api-only
python run.py --no-reload
```

Production derives ownership from an authenticated Session. The legacy `local-user` compatibility path is development-only and can be explicitly claimed by an Admin.

## Core capabilities

### Character Library and Runtime Prompt Inspector

Users can create, edit, search, filter, sort, and test Prompt + Model or existing-target Character Cards. Prompt-model cards expose the exact current Runtime System Message, Provider, Model, Temperature, active Prompt Version, and config hash.

The Runtime Prompt can be copied or exported as:

- plain text;
- Markdown with metadata;
- full secret-free JSON;
- OpenAI-compatible messages JSON.

The Inspector reads the authoritative `PromptModelConfig` used by `PromptModelTarget`; it never exports API keys, Vault ciphertext, or Environment Secret values.

### Test Room and Experiment Workspace

Custom Scenarios support English and Simplified Chinese, expected behavior, required and forbidden signals, severity, bounded Adaptive turns, and recommended modes. Test Packs provide ordered Scenario collections.

The Test Room supports:

- fixed Benchmark pressure;
- Admin-managed Adaptive Tester pressure;
- deterministic Rules Judge;
- grounded Semantic Judge;
- Hybrid disagreement as `REVIEW`;
- Watch and Fast observation modes;
- persisted Tester, Subject, Judge, evidence, and breakpoint events.

Experiment History retains immutable configuration snapshots, reports, reruns, compatible baselines, filters, and lineage.

### Matrix Lab

Matrix Lab executes controlled combinations of Character/Prompt, Model, Temperature, Pack, Language, Tester, Judge, and repeat count. It includes persistent queue controls, bounded concurrency, retries, Provider backoff, repeated-run statistics, compatible regressions, Prompt version management, and secret-free JSON/CSV/Markdown exports.

## Phase 16 evaluation-engineering workspace

### Reviewable Authoring

Scenario Drafts and Test Pack Drafts carry manual or AI provenance, review notes, risk tags, revisions, rejection, and explicit approval.

Drafts are not executable resources:

- they do not appear in formal Scenario or Test Pack listings;
- Trial and Matrix launch paths accept only formal resources;
- Scenario Draft approval creates a normal Scenario;
- Test Pack Draft approval requires approved Scenario Draft references;
- approved Drafts become immutable provenance records.

The Admin-managed Authoring Runtime stores its credential in the encrypted Vault. Structured AI generation allows one bounded correction, rejects duplicate Scenario fingerprints, reports risk-coverage warnings, and saves every result as a Draft.

### Calibration Lab

Calibration Datasets preserve human-controlled ground truth:

- expected `PASS`, `FAIL`, or `REVIEW`;
- frozen Subject responses;
- exact contiguous evidence excerpts;
- failure types and six explicit coverage dimensions;
- manual Case creation or import from a completed Run Turn;
- immutable approved versions and explicit next-version creation;
- secret-free Archive export/import.

### Judge Analytics

Approved Calibration Dataset versions can be evaluated by Rules, Semantic, and Hybrid Judges. Every Evaluation Snapshot freezes the Dataset version, Judge configuration metadata, per-Case predictions, evidence, errors, and metrics.

Analytics include:

- confusion matrices;
- accuracy, precision, recall, and Macro F1;
- false-positive and false-negative rates;
- Rules/Semantic agreement and disagreement;
- breakdowns by failure type, language, Scenario category, and Character.

Provider failures remain explicit errors and never become fabricated verdicts.

### Rubric and Coverage Lab

Semantic Rubrics can be compared only when both Evaluation Snapshots use the same frozen Dataset ID and version. Reports show accuracy, Macro F1, false-positive/false-negative deltas, six Semantic dimension deltas, and per-Case prediction changes.

Coverage is reported across:

1. identity;
2. memory;
3. instruction resistance;
4. capability honesty;
5. persona;
6. language.

Missing and weak dimensions can be sent to the Authoring Runtime as risk tags. The output remains reviewable Drafts; it is never auto-approved.

### Templates and Sharing

Echo Masque includes bilingual reusable templates for identity/memory, instruction/capability, and persona/language testing. Template instantiation creates Scenario and Test Pack Drafts only.

Evaluation Share Bundles are versioned and secret-free. They may include formal Scenario contracts and Test Pack structure, but exclude account data, owner IDs, credentials, Calibration labels, and private Run transcripts. Imports always become Drafts.

See:

- `docs/phase-16-authoring.md`
- `docs/phase-16-ai-authoring.md`
- `docs/phase-16-calibration.md`
- `docs/phase-16-rubric-coverage.md`
- `docs/phase-16-release.md`

## Authentication and credential security

Phase 15 provides:

- Argon2 password hashing;
- opaque, revocable, expiring server-side Sessions;
- HttpOnly SameSite browser cookies;
- invitation-controlled Production registration;
- user and Admin roles;
- owner-scoped workspaces and reports;
- encrypted Character, Adaptive, Judge, and Authoring credentials;
- MultiFernet key rotation;
- append-only redacted Audit Events;
- secret-free account export and destructive account deletion.

Raw keys, encrypted blobs, Session tokens, password hashes, and invitation codes are excluded from exports, snapshots, events, reports, and logs.

## Quotas and abuse controls

SQLite-backed controls persist across restart and cover:

- authenticated request rate limits;
- login failure windows and temporary blocking;
- per-user Characters, Scenarios, Packs, Runs, and Matrices;
- daily Matrix task volume;
- concurrent Runs and Matrix tasks;
- total workspace records;
- daily AI Authoring generations;
- daily Judge Evaluation Case predictions;
- daily template and Share Bundle imports;
- Share Bundle asset caps.

Blocked requests return `429 Too Many Requests`, with `Retry-After` when applicable.

## Production deployment

The root `Dockerfile` and `railway.toml` deploy one FastAPI service that serves the built React client. Attach one Railway Volume at `/data`, use one replica while SQLite remains the Production database, and configure `/health` as the health check.

Required Railway variables:

```text
ECHO_MASQUE_ENVIRONMENT=production
ECHO_MASQUE_DATABASE_URL=sqlite:////data/echo_masque.db
ECHO_MASQUE_LEGACY_LOCAL_USER_ENABLED=false
ECHO_MASQUE_PUBLIC_REGISTRATION_ENABLED=false
ECHO_MASQUE_BOOTSTRAP_ADMIN_EMAIL=<admin email>
ECHO_MASQUE_BOOTSTRAP_ADMIN_PASSWORD=<long unique password>
ECHO_MASQUE_CREDENTIAL_ENCRYPTION_KEYS=<Fernet key>
```

Optional Phase 16 quota overrides:

```text
ECHO_MASQUE_MAX_AUTHORING_GENERATIONS_PER_DAY=50
ECHO_MASQUE_MAX_EVALUATION_CASES_PER_DAY=1000
ECHO_MASQUE_MAX_TEMPLATE_INSTANTIATIONS_PER_DAY=100
ECHO_MASQUE_MAX_SHARED_ASSETS_PER_BUNDLE=200
```

Keep encryption keys and account passwords outside Git. Losing every matching Fernet key makes existing encrypted Provider credentials unrecoverable.

## Automated validation

Pull requests run:

- Ruff and strict mypy on Python 3.12 and 3.13;
- the full pytest suite;
- TypeScript checking, Vitest, and the React Production build;
- Production Docker build and persistent-volume replacement smoke;
- Railway live smoke.

Retained Production workflows:

- **Phase 15 Live Security Smoke** validates multi-account isolation, credential Vault rotation, and export redaction.
- **Phase 16 Live Acceptance** validates template Draft boundaries, secret-free sharing, Runtime Prompt exports, Calibration, Rules Evaluation, coverage analytics, and temporary-account cleanup.

GitHub Repository Secrets used by both workflows:

```text
ECHO_MASQUE_LIVE_ADMIN_EMAIL
ECHO_MASQUE_LIVE_ADMIN_PASSWORD
```

## Delivery phases

### Completed

- [x] Phases 0–15 — Foundation through authenticated secure multi-user deployment
- [x] Phase 16A — Reviewable Scenario/Test Pack Draft foundation
- [x] Phase 16B — AI Scenario/Test Pack drafting and Authoring Lab
- [x] Phase 16C — Human-controlled Calibration Datasets
- [x] Phase 16D — Judge Evaluation Snapshots and analytics
- [x] Phase 16E — Rubric comparison and coverage analytics

### Final release gate

- [x] Phase 16F implementation — templates, sharing, quotas, UI, migration guide, and retained live workflow
- [ ] Phase 16F Production live acceptance after merge

See `CHECKLIST.md` for acceptance status and Issue #45 for the Phase 16 tracker.
