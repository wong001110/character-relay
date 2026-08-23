# Developer guide

## Start locally

Requirements are Python 3.12+, Node.js 22+ for the Portal, and Node.js 24.17+ for the Discord Connector.

```bash
python run.py
```

The launcher prepares the Python environment and starts the API and Portal. Useful variants are `--install`, `--no-install`, `--api-only`, and `--no-reload`.

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
