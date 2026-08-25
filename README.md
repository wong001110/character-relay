# Character Relay

Character Relay is a creator-oriented studio for building, testing, deploying, and observing persistent AI characters in group chat. Echo Masque is the evaluation module inside the wider product.

The current production connector is Discord. Telegram and WhatsApp are directions, not equivalent implemented connectors.

## What is implemented

- Character Cards, prompt/model configuration, portraits, credentials, and versioned evaluation inputs.
- Discord server workspaces, deployments, per-character webhook identities, Smart Participation, social turns, tools, media handling, and durable delivery boundaries.
- Intelligence Core v3: conversation structure, episodes, evidence-backed beliefs, entity/evidence graph, context resolution, social state, and participation planning.
- LangGraph Character Turn and Social Turn orchestration with runtime and provider traces.
- Echo Masque evaluation: scenarios, test packs, matrices, calibration datasets, authoring drafts, reports, and prompt inspection.
- Session authentication, owner isolation, encrypted credentials, audit controls, quotas, and a server-enforced read-only Public Demo.

## Runtime shape

```text
Discord
  -> connectors/discord
  -> audience and participation routing
  -> Social Turn
  -> Character Turn
       -> context / belief / episode / knowledge / media resolution
       -> provider model
       -> optional tool loop
       -> Smart Output
       -> runtime authority
  -> Discord rendering and delivery
```

The runtime owns identity, scope, permissions, lifecycle, and side effects. Model output may propose semantic choices, but it cannot create IDs, widen visibility, or authorize operations.

Topic authority was removed by the Intelligence Core v3 hard cutover. Do not reintroduce Topic fallback, `topic_id` continuation authority, Topic-scoped durable memory, or Topic-driven Wiki/Discovery behavior. See [`docs/intelligence-core-v3-architecture.md`](docs/intelligence-core-v3-architecture.md).

## Repository map

| Area | Implementation | Primary tests/docs |
| --- | --- | --- |
| Python API/runtime | `src/echo_masque/` | `tests/`, `docs/architecture.md` |
| API composition/routes | `src/echo_masque/api/` | API/phase tests under `tests/` |
| Web Portal | `web/src/` | `web/src/*.test.ts`, UI contracts under `docs/` |
| Discord Connector | `connectors/discord/src/` | `connectors/discord/src/**/*.test.ts`, connector README |
| Persistence | `src/echo_masque/persistence/` | repository and lifecycle tests under `tests/` |
| Deployment | root `Dockerfile`, `railway.toml`, `compose.yaml` | CI workflows, `docs/railway-deployment.md` |
| Agent orientation | `AGENTS.md`, `docs/README.md`, `docs/agent-handoff.md` | `openwiki/INSTRUCTIONS.md` |

For a source-to-test map by subsystem, start at [`docs/agent-handoff.md`](docs/agent-handoff.md). The documentation authority index is [`docs/README.md`](docs/README.md).

Future local-device execution, gaming presence, live viewing, plugins/adapters, and optional local/coding-agent integration are planned in [`docs/local-execution-roadmap.md`](docs/local-execution-roadmap.md). The device-side companion repository is [`wong001110/character-relay-local`](https://github.com/wong001110/character-relay-local). This direction is **planned/deferred and not part of the currently implemented runtime**.

## Local setup

Requirements:

- Python 3.12+
- Node.js 22+ for the Portal
- Node.js 24.17+ for the Discord Connector

Start the API and Portal:

```bash
python run.py
```

The launcher prepares `.venv` and installs dependencies unless told otherwise.

```bash
python run.py --install
python run.py --no-install
python run.py --api-only
python run.py --no-reload
```

Default local endpoints:

- Portal: `http://127.0.0.1:5173`
- API documentation: `http://127.0.0.1:8000/docs`
- Health: `http://127.0.0.1:8000/health`

## Validation

Python:

```bash
python -m ruff check .
python -m mypy src
python -m pytest
```

Portal:

```bash
cd web
npm ci
npm run typecheck
npm test
npm run build
```

Discord Connector:

```bash
cd connectors/discord
npm ci
npm run typecheck
npm test
npm run build
```

CI is the complete merge gate; select targeted tests while iterating, then run the relevant full checks before handoff.

## Production deployment

The supported Railway shape is one application replica using the root `Dockerfile`, with a persistent Volume mounted at `/data`. SQLite requires the single-replica boundary.

Application settings use only the `CHARACTER_RELAY_*` prefix. A minimal production configuration includes:

```text
CHARACTER_RELAY_ENVIRONMENT=production
CHARACTER_RELAY_DATABASE_URL=sqlite:////data/echo_masque.db
CHARACTER_RELAY_LEGACY_LOCAL_USER_ENABLED=false
CHARACTER_RELAY_PUBLIC_REGISTRATION_ENABLED=false
CHARACTER_RELAY_BOOTSTRAP_ADMIN_EMAIL=<admin email>
CHARACTER_RELAY_BOOTSTRAP_ADMIN_PASSWORD=<long unique password>
CHARACTER_RELAY_CREDENTIAL_ENCRYPTION_KEYS=<Fernet key>
CHARACTER_RELAY_CONNECTOR_SHARED_SECRET=<long random secret>
RAILWAY_RUN_UID=0
```

Railway needs `RAILWAY_RUN_UID=0` because its Volume is mounted as root; the image entrypoint repairs `/data` ownership and drops to UID `10001` before Uvicorn starts. Keep credentials and encryption material outside Git. The shared Public Demo is intentionally read-only; server-side mutation checks remain authoritative even when a client is incorrect.

See [`docs/railway-deployment.md`](docs/railway-deployment.md) and [`docs/security.md`](docs/security.md) before production changes.

## AI coding agents

Read in this order:

1. [`AGENTS.md`](AGENTS.md)
2. [`docs/ai-agent-development-workflow.md`](docs/ai-agent-development-workflow.md)
3. `openwiki/quickstart.md` only when it was generated by OpenWiki and exists
4. [`docs/agent-handoff.md`](docs/agent-handoff.md) and [`docs/README.md`](docs/README.md)
5. task-relevant canonical docs, source/types, and tests

Generated OpenWiki pages are navigation, not product contracts. Important claims must be traced to current source, tests, schemas, or an accepted canonical document.

## Documentation

- [`docs/user/README.md`](docs/user/README.md) — Discord setup and everyday use
- [`docs/operator/README.md`](docs/operator/README.md) — deployment, storage, security, and incident entry points
- [`docs/developer/README.md`](docs/developer/README.md) — local setup, validation, and evidence-first development
- [`docs/contracts/README.md`](docs/contracts/README.md) — current product and architecture authority
- [`docs/history/README.md`](docs/history/README.md) — superseded designs and delivery records
- [`docs/local-execution-roadmap.md`](docs/local-execution-roadmap.md) — planned/deferred local device execution and embodiment direction
- [`docs/README.md`](docs/README.md) — complete audience and authority index
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — contribution workflow
