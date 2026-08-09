# Character Relay

Character Relay is a character behavior testing and deployment workspace for conversational AI. It combines Character Cards, deterministic and provider-backed test targets, adversarial behavior evaluation, Discord deployment, scoped knowledge retrieval, Smart Participation, Tool Calling, and operational observability.

## Runtime highlights

- Character Cards keep identity, persona, tone, and behavior constraints portable across testing and deployment.
- Discord Server Workspaces scope deployments, interactions, knowledge, expressions, and runtime settings to one Server.
- Each Discord Server can store a default IANA timezone. Character replies interpret unqualified dates/times in that timezone, Current Time uses it when no override is supplied, and Reminder timestamps without an explicit offset are interpreted in it before UTC persistence.
- Tool Calling is deployment-scoped and side-effect bounded. Reminder, Discord, browser, weather, random, file, and utility capabilities are assigned explicitly.
- Provider Trace is private Super Admin observability with account/category filtering, Tool Calling classification, lazy detail loading, and failed Tool results surfaced as errors.

## Development

The backend requires Python 3.12+ and the Portal is a Vite/React application.

```bash
python -m pip install -e ".[dev]"
cd web && npm install
```

Run backend tests and checks:

```bash
python -m ruff check .
python -m mypy src
python -m pytest
```

Run Portal checks:

```bash
cd web
npm run typecheck
npm test
npm run build
```

See the `docs/` directory for architecture, deployment, security, Discord runtime, RAG, Smart Output, Smart Participation, Tool Calling, and Provider Trace documentation.
