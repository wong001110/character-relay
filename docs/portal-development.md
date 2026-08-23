# Portal development and UI review

The Portal is a React/Vite client in `web/`. The normal build is **live mode**: it uses the
same-origin authenticated API and must be run with the application service when you need real
data or mutations.

## Commands

```bash
cd web
npm ci
npm run dev          # live mode, normally with the FastAPI API running locally
npm run build        # production Portal bundle
npm run typecheck
npm test
```

For no-network UI review:

```bash
cd web
npm run dev:mock
npm run build:mock
```

Mock mode sets `VITE_PORTAL_DATA_MODE=mock`. It is a browser-local UI fixture mode, not a staging
environment, Demo account, or authentication bypass. It never calls the live `/api` surface and
shows a persistent **MOCK DATA — NO LIVE CONNECTION** indicator where a fixture is available.

Current mock coverage is deliberately narrow:

- `/dev/ui` — local Component Library review with a mock reviewer;
- `/deployments` and its Server Notebook paths — typed local Server/Conversation Board fixtures;
- other business paths show the explicit mock-mode landing page instead of falling through to
  live data.

Fixture adapters are page-local and typed against existing Portal interfaces. Do not replace
global `fetch`, copy production payloads into fixtures, or add credentials to `VITE_*` values.

## Deep links

The production service returns the Portal entry document only for explicitly approved client
paths. Current groups are Dashboard; Character Archive/File/Create/Edit/Test/Prompt; top-level
Toolbox/Settings; Component Library; and Server Notebook pages under a selected deployment Server.
Unknown API and unknown client-like paths remain 404s.

After deployment, validate the public HTML deep links with the credential-free Railway smoke. Then
perform an authenticated browser check for the Super Admin-only Component Library and a real
Server Notebook; the smoke cannot prove session-based authorization.
