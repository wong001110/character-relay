# Contributing

Character Relay changes should belong to one clearly scoped feature/phase or defect fix. Avoid combining unrelated runtime, data-contract, and visual changes in one PR unless the coupling is necessary and documented.

## AI-assisted development

AI coding agents and AI-assisted contributors must follow:

- `AGENTS.md`
- `docs/ai-agent-development-workflow.md`
- `openwiki/INSTRUCTIONS.md`

For approved UI renovation work, also follow `docs/ui-page-migration-plan.md` and the matching image under `docs/ui-references/`. Generated reference art controls composition only; current code/API/tests control real data and behavior.

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Run the API

```bash
make run
```

The OpenAPI document is available at `http://127.0.0.1:8000/docs`.

## Required checks

```bash
make check
```

This runs Ruff, mypy, and pytest. Model credentials must not be required by the default test suite and must never be committed.

For web changes also run the relevant commands from `web/package.json`, including typecheck/tests/build before merge.
