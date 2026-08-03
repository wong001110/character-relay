# Character Relay

**Create, test, and deploy persistent AI characters across chat platforms.**

Character Relay is the expanded product direction of Echo Masque. It combines a secure Character Card workspace, the existing Echo Masque evaluation system, version-aware deployment management, and a connector-oriented architecture for bringing characters into Discord, WhatsApp, Telegram, and future chat platforms.

Echo Masque remains part of the product as the character consistency and pressure-testing module. It is no longer the name of the entire platform.

## Product loop

```text
Create a Character Card
  -> inspect the exact runtime prompt and model binding
  -> test identity, memory, persona, and instruction resistance in Echo Masque
  -> review evidence and publish a stable character version
  -> connect a Discord, WhatsApp, or Telegram account
  -> deploy the character to one or more channels, threads, or groups
  -> manage every deployment independently
  -> revise, retest, upgrade, pause, or roll back
```

## Current release scope

The current application includes:

- **Character Studio** — user-owned Character Cards and prompt/model bindings;
- **Echo Masque Lab** — deterministic and model-backed character evaluation;
- **Experiment Workspace** — reusable scenarios, test packs, runs, reports, and matrices;
- **Deployment Center** — persistent platform connections and one-record-per-destination deployments;
- **Security workspace** — account isolation, encrypted provider credentials, audit controls, quotas, and read-only public Demo boundaries.

The new Deployment Center is the foundation for connectors. It currently stores and manages connection/deployment configuration, status, channel/thread identity, participation mode, memory scope, version labels, and sticker counts. Discord OAuth, Telegram Bot setup, and the local WhatsApp QR connector are planned connector phases and are not falsely presented as active integrations in this release.

## Deployment model

One Character Card may be deployed to many destinations:

```text
Ann / Current
├── Discord / Juen Test Server / #ann-room
├── Discord / Juen Test Server / #general
├── Discord / Roleplay Server / Thread: Chapter 1
├── Telegram / Test Group
└── WhatsApp / Local Test Group
```

Every channel, thread, or group is stored as an independent Deployment so it can have its own:

- status: active, paused, offline, error, or disconnected;
- participation mode: mention, reply, mention + reply, or smart participation;
- memory scope: channel-isolated, server-shared, or custom;
- character version label;
- sticker mapping count;
- destination and connection identity;
- error and activity state.

## Connector direction

```text
Chat platform
  -> Platform Connector
  -> normalized message contract
  -> Social Participation Runtime
  -> Character Runtime
  -> platform-specific reply renderer
```

Recommended deployment topology:

```text
Railway
├── Character Relay Web/API
├── Discord Connector
├── Telegram Connector
└── persistent database / queue

User computer
└── WhatsApp Experimental Connector
    └── linked-device session remains local
```

The Discord and Telegram connectors can use official Bot APIs and run as managed workers. The private-number WhatsApp experiment requires a separate local connector because it relies on a linked-device session rather than the official business messaging flow.

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

The existing production URL remains unchanged during the product rename:

```text
URL: https://echo-masque-production.up.railway.app
Email: demo@echo-masque.app
Password: EchoMasqueDemo2026!
```

The shared Demo workspace is read-only. It can inspect prompts, browse the experiment workspace, run supported tests, view reports, and inspect deployment structure. Character, credential, connection, deployment, account, matrix, authoring, calibration, analytics, template, and import mutations remain server-blocked.

## Echo Masque evaluation module

Echo Masque continues to provide:

- exact Runtime System Prompt inspection;
- Benchmark and Adaptive pressure testing;
- Rules, Semantic, and Hybrid Judge modes;
- identity, memory, instruction-resistance, capability-honesty, persona, and language coverage;
- immutable Run and Evaluation Snapshots;
- human-controlled calibration labels and exact evidence;
- Matrix experiments and regression comparison;
- reviewable AI-assisted Scenario and Test Pack authoring;
- secret-free templates, archives, and sharing bundles.

OOC and consistency checks belong primarily to creation, simulation, debugging, and release validation. A deployed character is not required to pay the latency and token cost of an OOC judge on every message.

## Deployment API

Authenticated users can manage the deployment foundation through:

```text
GET    /api/connections
POST   /api/connections
PATCH  /api/connections/{connection_id}
DELETE /api/connections/{connection_id}

GET    /api/deployments
POST   /api/deployments
PUT    /api/deployments/{deployment_id}
PATCH  /api/deployments/{deployment_id}/status
DELETE /api/deployments/{deployment_id}
```

Deleting a platform connection also removes its deployment records. Creating the same character deployment twice for the same connection/channel/thread returns a conflict instead of creating duplicate runtime assignments.

## Authentication and credential security

Production uses Argon2 password hashes, opaque server-side Sessions, HttpOnly cookies, invitation-controlled registration, user/Admin roles, owner-scoped resources, encrypted Character and shared Runtime credentials, MultiFernet rotation, redacted Audit Events, and secret-free account export.

Raw keys, encrypted blobs, Session tokens, password hashes, invitation codes, and local connector sessions must not enter exports, snapshots, reports, or logs.

## Production deployment

Deploy the root `Dockerfile` with `railway.toml`, one replica, and a Railway Volume mounted at `/data`.

The existing `ECHO_MASQUE_*` environment prefix and SQLite filename remain intentionally supported as backward-compatible infrastructure identifiers during the Character Relay product rename.

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

Keep encryption keys, connector credentials, Bot tokens, WhatsApp linked-device sessions, and administrator passwords outside Git.

## Validation

Pull requests run Ruff, strict mypy, pytest on Python 3.12/3.13, TypeScript, Vitest, the production web build, Docker persistent-volume smoke, and Railway smoke.

The retained Phase 15/16 security and evaluation acceptance suites remain part of the product. The deployment foundation adds owner-scoped connection and deployment API coverage without weakening the public Demo mutation boundary.

## Documentation

- `CHECKLIST.md`
- `docs/phase-15-security.md`
- `docs/phase-16-authoring.md`
- `docs/phase-16-ai-authoring.md`
- `docs/phase-16-calibration.md`
- `docs/phase-16-rubric-coverage.md`
- `docs/phase-16-release.md`
- `docs/railway-deployment.md`
