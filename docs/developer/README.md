# Developer guide

Policy: [AGENTS.md](../../AGENTS.md). Current work: [PROJECT_STATE.md](../../PROJECT_STATE.md).
Ownership: [architecture.md](../architecture.md). This page contains setup/check commands, not a
second phase plan. The accepted group-chat design is pending implementation; do not alter runtime
code in the planning-only PR.

## Local setup

Use the current manifests for exact supported Python/Node versions. The existing launcher prepares
the Python environment and starts API/Portal:

```bash
python run.py
# Existing variants: --install, --no-install, --api-only, --no-reload
```

For an isolated PostgreSQL + pgvector stack and the separate Fabric worker:

```bash
docker compose up --build -d
docker compose logs --tail=100 echo-masque fabric-worker
docker compose stop
```

This is a local development stack bound to loopback, with a private database, development-only
password and separate resource budgets. Do not use it as public production configuration or insert
live credentials into fixtures. SQLite unit tests do not replace PostgreSQL/restart validation.

Offline recovery requires **all** processes/replicas sharing the database to stop first:

```bash
docker compose stop echo-masque fabric-worker
docker compose run --rm --no-deps echo-masque echo-masque recover-interrupted --workers-stopped
docker compose up -d echo-masque fabric-worker
```

The acknowledgement is an operator assertion, not proof remote replicas stopped. Back up data and
reconcile uncertain external effects before retrying. Do not delete volumes to recover a job. Read
[storage safety](../storage-safety.md), [deployment](../railway-deployment.md) and
[security](../security.md) before production work; a docs PR or old green CI is not rollout approval.

For the Discord worker:

```bash
cd connectors/discord
npm ci
npm run dev
```

## Validation by changed surface

Use focused tests after coherent edits. Relevant complete checks belong at the phase/PR boundary,
not after every file. Validate commands against the checkout if manifests have changed.

```bash
# Repository root: Python
python -m ruff check .
python -m mypy src
# Python Portal route tests require the built artifact first.
npm ci --prefix web
npm run build --prefix web
python -m pytest
# Optional existing two-worker variant: python -m pytest -n 2 --tb=short
```

```bash
# Portal
cd web
npm ci
npm run typecheck
npm test
npm run build
```

```bash
# Discord Connector
cd connectors/discord
npm ci
npm run typecheck
npm test
npm run build
```

Ordinary pytest uses deterministic/unavailable encoders rather than real embedding downloads.
An approved live-model environment may use the existing `pytest --live-embeddings` option; record
that separately. Offline tests do not prove live model, embedding or Discord quality.

Use applicable bounded mutation scopes for changed protected decisions; see
[mutation testing](../mutation-testing.md). Python scopes use supported Ubuntu/WSL facilities;
`scripts/run_mutmut_wsl.sh` and package-local `test:mutation` scripts are existing entry points.
Record equivalent survivors, tool failures, timeouts and missing environments honestly. Do not
weaken coverage/exclusions to make a badge pass. Browser checks apply to changed Portal journeys;
Docker/PostgreSQL/fault tests apply to changed deployment/worker/storage boundaries.

## Documentation-only validation

Check Markdown links/statuses, accepted-requirement coverage, retired development pointers and
changed-path scope. Compare runtime/dependency/workflow subtrees with the reviewed baseline. No
source moves, placeholder packages, tests or workflow execution changes belong in a planning PR.
Record self-review and unrun runtime/live checks. CI conclusions must name the actual checked head.

## UI and evaluation

For UI work use [UI/UX](../ui-ux-contract.md), [components](../ui-component-library.md) and
[approved reference rules](../ui-page-migration-plan.md). Real APIs/types determine data; reference
art supplies composition only. Keep accessibility, responsive behavior and overlay rules.

For offline evaluation follow [Matrix](../phase-14-experiment-matrix.md),
[authoring](../phase-16-authoring.md), [AI-assisted drafts](../phase-16-ai-authoring.md),
[calibration](../phase-16-calibration.md), [coverage](../phase-16-rubric-coverage.md) and
[release evidence](../phase-16-release.md). AI may draft; approvals and immutable evaluation
snapshots remain authoritative. These capabilities need not run on every group-chat message.
