# Developer guide

## Start locally

Requirements are Python 3.12+, Node.js 22+ for the Portal, and Node.js 24.17+ for the Discord Connector.

```bash
python run.py
```

The launcher prepares the Python environment and starts the API and Portal. Useful variants are `--install`, `--no-install`, `--api-only`, and `--no-reload`.

For isolated integration testing with PostgreSQL + pgvector and a separate Fabric worker:

```bash
docker compose up --build -d
docker compose logs --tail=100 echo-masque fabric-worker
docker compose stop
```

This is a **local development** stack, bound to `127.0.0.1:8000`, with a private database service,
development-only password and separate API/worker CPU, RAM and PID budgets. The resource values
are starting limits, not measured production sizing. The existing named `/data` volume is retained;
the review database has a separate named volume. No real provider or Discord credential is
injected. PostgreSQL behavior, process restart and browser resource testing require Docker; SQLite
unit tests do not replace those checks. Do not reuse this configuration for public hosting.

Never run recovery while another API/worker sharing its database is alive. Recovery is explicit:

```bash
docker compose stop echo-masque fabric-worker
docker compose run --rm --no-deps echo-masque echo-masque recover-interrupted --workers-stopped
docker compose up -d echo-masque fabric-worker
```

The acknowledgement is an operator assertion, not automatic proof that every remote replica has
stopped. Stop remote replicas too if they share the database. This command conservatively marks
uncertain external effects and requeues interrupted ingestion; review those effects before retry.
Do not delete volumes to recover a stalled job.

Before any later production rollout, validate the disposable PostgreSQL stack, configure the
operator endpoint origins and owner-scoped credentials, and stop all replicas before invoking
offline recovery. Retain a database backup and reconcile uncertain external effects. This review
adds no schema migration, but reverting to the baseline also restores its startup-recovery and
authorization defects; it is not an automatically safe rollback target. Keep the PR unreleased
until the deployment and security limitations in `docs/security-red-team-2026-09-07.md` have an
explicit disposition.

For the Discord worker:

```bash
cd connectors/discord
npm install
npm run dev
```

## Validate a batch

```bash
python -m ruff check .
python -m mypy src
python -m pytest
```

For a faster local full regression, `python -m pytest -n 2 --tb=short` runs the same configured
suite across two workers using the development dependency `pytest-xdist`. Build `web/dist` first
with `npm ci --prefix web` and `npm run build --prefix web`; Python Portal route tests serve that
artifact. The Python CI job performs this build itself.

```bash
cd web
npm run typecheck
npm test
npm run build
```

```bash
cd connectors/discord
npm run typecheck
npm test
npm run build
```

Use focused tests while editing and run the relevant complete surface gate before handoff. CI remains the merge gate.

Default pytest runs use injected deterministic encoders or the unavailable-embedding fallback;
they do not initialize real embedding models. This prevents accidental model downloads and
third-party runtime telemetry during regressions. An approved live-model environment may opt in
with `pytest --live-embeddings`; record that separately from deterministic results. Runtime model
initialization disables ONNX telemetry explicitly. Passing offline tests does not prove embedding
quality or live provider behavior.

## Mutation testing

Use the bounded mutation scope for changed authorization, ownership, lifecycle, safety, and
deterministic decision logic when it is configured for that module. Python mutation runs require
Ubuntu CI or an installed WSL distribution. From a Windows checkout, invoke
`scripts/run_mutmut_wsl.sh` through WSL; it runs a temporary WSL-native copy so mutmut does not
stall writing its cache under `/mnt/<drive>`. Portal and Connector runs use the package-local
`test:mutation` scripts. Native Windows Stryker output is diagnostic only while its worker-cleanup
permission issue remains; use the scheduled/manual Ubuntu workflow as gate evidence.
The scheduled/manual workflow carries the initial smoke scopes, while a phase records the exact
scope and any reviewed survivor. See [Mutation testing](../mutation-testing.md) before adding an
exclusion or treating a score as proof of untested code.

## Before changing behavior

1. Read repository `AGENTS.md` and the [AI agent workflow](../ai-agent-development-workflow.md).
2. Use the maintained [agent map](../agent-map.md), [five-minute handoff](../agent-handoff.md), and [canonical contract index](../contracts/README.md).
3. Read current source, types, migrations, tests, and the task-relevant contract.
4. Record the evidence map and invariants before implementation.

The active branch ledger is [active-development-plan.md](../active-development-plan.md) only when its header matches the checked-out branch. The agent map is navigation, not product authority.

## Conversation runtime implementation record

The phased record for focused Roleplay prompts, conditional Utility Turn Direction,
Segment-first context, and qualitative social posture is in [Turn Director and Focused Roleplay
Prompt](../turn-director-prompt-implementation.md). It must be read alongside the current
[Intelligence Core v3 contract](../intelligence-core-v3-architecture.md). Check the recorded
branch/commit and current source before relying on it as merged behavior.

## Evaluation and calibration

Use [Experiment Matrix](../phase-14-experiment-matrix.md) to run and compare retained
experiments. For datasets and rubrics, follow [evaluation authoring](../phase-16-authoring.md),
[AI-assisted authoring](../phase-16-ai-authoring.md),
[calibration](../phase-16-calibration.md), [rubric coverage](../phase-16-rubric-coverage.md),
then [release acceptance](../phase-16-release.md). AI may draft authoring material, but human
approval and immutable dataset/version boundaries remain authoritative.
