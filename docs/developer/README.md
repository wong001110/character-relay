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
2. Read `openwiki/quickstart.md` if OpenWiki generated it, then trace claims back to source/tests.
3. Use the [five-minute handoff map](../agent-handoff.md) and [canonical contract index](../contracts/README.md).
4. Read current source, types, migrations, tests, and the task-relevant contract.
5. Record the evidence map and invariants before implementation.

The active branch ledger is [active-development-plan.md](../active-development-plan.md) only when its header matches the checked-out branch. Generated OpenWiki pages are orientation, not product authority.
