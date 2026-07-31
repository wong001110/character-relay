# Echo Masque

**See what remains when the role is challenged.**

Echo Masque is a Python-first behavior validation system for conversational characters and agents. It combines user-owned Character Cards, reusable Scenarios and Test Packs, Benchmark or Adaptive pressure, Rules/Semantic/Hybrid judging, immutable experiment evidence, comparative Matrix analytics, and a controlled authoring review boundary.

## Product loop

```text
Sign in to an isolated workspace
  -> create or select a Character Card
  -> draft, review, or create Scenarios and Test Packs
  -> approve Drafts before they enter execution paths
  -> choose Benchmark or Admin-managed Adaptive Tester
  -> choose Rules, Semantic, or Hybrid Judge
  -> run and preserve an immutable configuration snapshot
  -> inspect evidence, reports, history, baselines, and Matrix analytics
  -> revise the character or evaluation without rewriting prior results
```

## Quick start

Requires Python 3.12+ and Node.js 22+.

```bash
python run.py
```

The launcher creates `.venv`, installs Python and web dependencies when their manifests change, and starts FastAPI and Vite together.

```bash
python run.py --install
python run.py --no-install
python run.py --api-only
python run.py --no-reload
```

Open `http://127.0.0.1:5173` for the UI or `http://127.0.0.1:8000/docs` for the API.

Local development keeps an explicit compatibility path for the historical `local-user` workspace. Production derives every private resource owner from an authenticated Session.

## Core capabilities

### Character Library

Users can create, edit, search, filter, sort, and test Prompt + Model or existing-target Character Cards. Provider, endpoint, Model, System Prompt, and Temperature changes preserve prior Run meaning through immutable snapshots and Prompt version history.

### Experiment Workspace

Custom Scenarios support English and Simplified Chinese, expected behavior, required and forbidden signals, severity, bounded Adaptive turns, and recommended modes. Test Packs provide ordered and versioned Scenario collections. Experiment History retains reports, reruns, compatible baselines, filters, and lineage.

### Test Room

The Test Room supports:

- fixed Benchmark pressure;
- Admin-managed Adaptive Tester pressure;
- deterministic Rules Judge;
- grounded Semantic Judge;
- Hybrid disagreement as `REVIEW`;
- Watch and Fast observation modes;
- persisted Tester, Subject, Judge, evidence, and breakpoint events.

### Matrix Lab

Matrix Lab executes controlled combinations of Character/Prompt, Model, Temperature, Pack, Language, Tester, Judge, and repeat count. It includes persistent queue controls, bounded concurrency, retries, Provider backoff, repeated-run statistics, compatible regressions, Prompt version management, and secret-free JSON/CSV/Markdown export.

### Reviewable authoring foundation

Phase 16A adds owner-scoped Scenario Drafts and Test Pack Drafts with manual or AI provenance, review notes, revisions, rejection, and explicit approval.

Drafts are not executable resources:

- they do not appear in formal Scenario or Test Pack listings;
- existing Trial and Matrix launch paths accept only formal Phase 13 resources;
- Scenario Draft approval creates a normal Scenario;
- Test Pack Draft approval requires every referenced Scenario Draft to be approved;
- approved Drafts become immutable provenance records.

A separate secret-free Authoring Archive supports merge and replace restore. For cross-database restoration, import the normal Workspace Archive first and the Authoring Archive second so approved formal resource IDs already exist.

See [`docs/phase-16-authoring.md`](docs/phase-16-authoring.md) for the state machine, API, archive, ownership, lifecycle, and Phase 16B boundary.

## Authentication and workspace isolation

Phase 15 replaces caller-selected identity headers with server-enforced identity and authorization:

- passwords are stored as Argon2 hashes;
- browser authentication uses opaque, revocable, expiring server-side Sessions;
- the browser receives an HttpOnly SameSite cookie and does not persist the raw Session token;
- Character Cards, Targets, Scenarios, Packs, Runs, Reports, Matrices, exports, imports, and storage operations are owner-scoped;
- Admin APIs require an authenticated account with the `admin` role;
- invitation registration, Session revocation, account export, and destructive account deletion are supported;
- sensitive mutations create append-only redacted Audit Events.

The bilingual web client includes sign-in, invitation registration, Session/device management, workspace export, account deletion, invitation administration, role management, Audit inspection, legacy workspace claim, and credential rotation controls.

## Secure credential vault

Character provider keys and shared Adaptive/Judge keys are encrypted with Fernet before entering SQLite. API responses expose status metadata only. Raw keys, encrypted blobs, Session tokens, password hashes, and invitation codes are excluded from workspace exports, Run snapshots, events, reports, and logs.

Production key rotation:

1. Generate a new Fernet key.
2. Set `ECHO_MASQUE_CREDENTIAL_ENCRYPTION_KEYS=<new>,<old>`.
3. Redeploy.
4. Rotate credentials from **Account & security → Admin control**.
5. Run the Phase 15 live security gate.
6. Remove the old key only after acceptance passes.

## Quotas and abuse controls

SQLite-backed controls persist across restart and cover:

- authenticated request rate limits;
- login failure windows and temporary blocking;
- Characters, Scenarios, Test Packs, Runs, and Matrices per user;
- daily Matrix task volume;
- concurrent Runs and Matrix tasks;
- total workspace record limits.

Blocked requests return `429 Too Many Requests`, with `Retry-After` for time-bound blocks.

## Production deployment

The root `Dockerfile` and `railway.toml` deploy one FastAPI service that serves the built React client. Attach one Railway Volume at `/data`, use one replica for SQLite, and configure `/health` as the health check.

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

Generate an encryption key locally:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Keep encryption keys and account passwords outside Git. Losing every matching Fernet key makes existing encrypted Provider credentials unrecoverable.

## Backup-first Phase 15 migration

Before enabling the authenticated Production UI, stop writes or use a maintenance window and run:

```bash
python scripts/phase15_migrate.py \
  --database-url sqlite:////data/echo_masque.db \
  --backup-directory /data/backups
```

The migration copies the SQLite database before creating missing tables and is safe to rerun. Existing `local-user` data can be claimed from the Admin account panel or by passing `--claim-user-email`.

See [`docs/phase-15-security.md`](docs/phase-15-security.md) for migration, quota, key-rotation, account-lifecycle, and release-gate details.

## Phase 15 live security gate

Add these GitHub Actions Repository Secrets:

```text
ECHO_MASQUE_LIVE_ADMIN_EMAIL
ECHO_MASQUE_LIVE_ADMIN_PASSWORD
```

Run **Phase 15 Live Security Smoke** after deployment and after every authentication or encryption-key migration. The workflow creates two temporary invited accounts, verifies cross-user isolation, confirms encrypted Vault status, rotates credentials, checks export redaction, and deletes the temporary accounts. Its uploaded JSON artifact contains no secret material.

## Automated validation

Pull requests run:

- Ruff and strict mypy on Python 3.12 and 3.13;
- the full pytest suite;
- TypeScript checking, Vitest, and the React Production build;
- Production Docker build and persistent-volume replacement smoke;
- Railway live smoke.

The Phase 15 workflow remains the Production multi-account and credential-rotation acceptance gate after every merge to `main`.

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
- [x] Phase 14 — Batch Experiment Matrix and Comparative Analytics
- [x] Phase 15 — Authentication, User Isolation, and Secure Credential Vault

### In progress

- [x] Phase 16A — Reviewable Scenario/Test Pack Draft foundation
- [ ] Phase 16B — AI Scenario/Test Pack drafting and Authoring Lab
- [ ] Phase 16C — Calibration Datasets
- [ ] Phase 16D — Judge evaluation analytics
- [ ] Phase 16E — Rubric comparison and coverage
- [ ] Phase 16F — Templates, sharing, and Production release gate

See `CHECKLIST.md` for acceptance status, Issue #45 for the Phase 16 tracker, and `docs/manual-validation.md` for human checks.
