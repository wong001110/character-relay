# Portal routing and UI environments — execution plan

Status: **active branch-local execution record**

| Field | Value |
| --- | --- |
| Active branch | `codex/portal-routing-environments` |
| Base | `main` at `4c7f976` |
| Current phase | Complete — Phase 7 validation and release handoff |
| Delivery mode | coherent phase batches; one implementation commit per completed phase |

## Approved outcome

The Portal becomes a route-based application with refresh-safe deep links. Production serves
the Portal index for approved client routes, while API routes remain API routes. The Portal
also supports explicit live and mock data modes for UI/UX review without allowing a mock build
to call a production API or exposing server credentials to the browser.

## Evidence map

- Portal entry/state: `web/src/main.tsx`, `web/src/App.tsx`, `web/src/PortalShell.tsx`.
- Existing component catalogue: `web/src/ComponentLibraryPage.tsx`,
  `web/src/AdministrationSettingsPanel.tsx`, `docs/ui-component-library.md`.
- Production static serving: `src/echo_masque/api/app.py`, `Dockerfile`,
  `docs/railway-deployment.md`.
- Environment/security boundary: `src/echo_masque/config.py`, `.env.example`,
  `docs/security.md`, `docs/phase-15-security.md`.
- UI product direction: `docs/ui-ux-contract.md`, `docs/ui-component-library.md`,
  `docs/ui-page-migration-plan.md`.

## Invariants

1. Server `CHARACTER_RELAY_ENVIRONMENT` remains the authority for production security and
   must not be weakened by a browser build mode.
2. No `VITE_*` variable contains credentials, tokens, production URLs with embedded secrets,
   or an authorization bypass.
3. Mock mode is browser-local, visibly labelled, deterministic, and must never write to or
   fetch from a live `/api` endpoint.
4. Existing API authorization and Public Demo read-only enforcement remain server-side.
5. Deep links may fall back to the Portal index only for approved UI paths; `/api`, `/health`,
   static assets, and unknown operational endpoints preserve their existing semantics.
6. Overlay layers retain the ordering in `docs/ui-ux-contract.md`; route changes must close or
   restore overlays predictably.

## Phases

### Phase 0 — contract, route inventory, and data-mode seam

- Add a typed Portal route inventory and route-state ownership map.
- Define `live` and `mock` UI data modes, their build commands, visual labelling, and the
  no-live-network invariant.
- Add the production-side route fallback design and focused tests before moving screens.

Gate: route/data-mode unit tests, production static-route tests, Portal typecheck, and docs
review. No screen migration in this phase.

Status: **complete.** The typed route and
data-mode seam, `mock` build command, no-live-network Component Library boundary, and focused
unit tests are present.

### Phase 1 — routing foundation and Component Library

- Add the client router, root auth/bootstrap boundary, route guards, and a production-safe
  fallback for `/dev/ui`.
- Migrate Component Library first; retain its Super Admin-only product policy.
- Add a visible mock-mode banner and mock data adapter for this isolated route.

Gate: direct-load and browser-back checks for `/dev/ui`, guard tests, Portal build/typecheck,
and Python API route tests.

Status: **complete; commit recorded in this branch's Git history.** `BrowserRouter`,
pathname-derived catalogue routing, Component Library mock access, and the explicit FastAPI
`/dev/ui` index route are implemented. Portal typecheck, 40 Vitest tests, production build,
mock build, `git diff --check`, Python deep-link tests (`2 passed`), focused Ruff, and focused
Mypy passed. The Python environment was repaired by installing Python 3.12.10 globally and
recreating the workspace `.venv`.

### Phase 2 — top-level workspace routes

- Migrate Dashboard, Character Archive, Deployment Workspace, Toolbox, and Settings from the
  root `section` state into guarded top-level routes.
- Keep data ownership/API behavior unchanged.

Gate: navigation/deep-link regression tests, Public Demo and admin visibility checks, Portal
build/typecheck.

Status: **complete; commit recorded in this branch's Git history.** Top-level workspace
navigation is now pathname-derived for Dashboard, Characters, Deployments, Toolbox, and
Settings. The FastAPI static boundary serves the Portal index only for these declared paths and
the Component Library. Portal typecheck, 41 Vitest tests, production/mock builds, Python
deep-link tests (`6 passed`), focused Ruff, focused Mypy, and `git diff --check` passed.
Mock mode remains intentionally restricted to the fully local Component Library until each
business page receives an explicit fixture adapter; it does not fall through to live API calls.

### Phase 3 — character files and overlay-aware routes

- Migrate Character File, Creator, Test Room, and Prompt Inspector using nested or modal
  routes where the page must retain its parent context.
- Specify which state is URL-restorable and which remains unsaved local draft state.

Gate: refresh/back/escape/focus checks, form-draft regression tests, Portal tests/build.

Status: **complete; commit recorded in this branch's Git history.** Character identity and
the active Character work surface are now pathname-derived: Archive, Create, Character File,
Persona, Prompt, Memory, Runtime, Deployments, Edit, Test Room, and Prompt Inspector each have
an explicit supported path. The Character File PageFlags update the path; Prompt Inspector is a
route-driven modal with Escape handling, focus trap, and opener-focus restoration. Creator
fields/AI Draft/credential input and Test Room run state intentionally remain unsaved local
state, so navigation and refresh never save them implicitly. The FastAPI static boundary has
specific deep-link routes only; an unknown Character subroute remains a 404. Portal typecheck,
42 Vitest tests (including route parsing), production and mock builds, 17 Python static-route
tests, focused Ruff, focused Mypy, and `git diff --check` passed. An authenticated browser
interaction check remains a release/readiness task because this local verification did not use a
live session. Mock mode remains Component-Library-only until a typed
business-page fixture adapter is delivered; Character routes do not make live API requests in
mock mode because they remain unavailable there.

### Phase 4 — Server Notebook and Conversation Board

- Give each Server Notebook page a stable route.
- Redesign Conversation Episodes as a bounded sticky-note board with a collapsed unresolved
  fragments area and an evidence drawer; do not render raw fetched content as a note title.

Gate: real-data mapping review, overflow/responsive tests, server-scope verification, Portal
tests/build.

Status: **complete; commit recorded in this branch's Git history.** The selected Discord Server,
Server Notebook page, and Intelligence subpage are pathname-derived. The exact FastAPI fallback
list covers only those declared pages; an unknown deployment subroute remains a 404. Conversation
and Knowledge evidence is explicitly presented as a Server-scoped projection, while Social remains
deployment-scoped. Episodes now render as a bounded sticky-note Board with URL-stripped,
line-clamped display titles; `unresolved_segment` projections are collapsed separately. A
focus-managed evidence drawer exposes only the stored summary and returned provenance IDs/counts,
not fabricated raw-message content. Portal typecheck, 45 Vitest tests (including Board projection
tests), production and mock builds, 22 Python static-route tests, focused Ruff, focused Mypy, and
`git diff --check` passed. An authenticated responsive browser review remains release validation.

### Phase 5 — cleanup and release readiness

- Remove superseded root state branches and path probing.
- Document development, live, and mock commands; update the component catalogue and agent map.
- Run cross-project validation and production deep-link smoke after deployment.

Status: **complete; commit recorded in this branch's Git history.** The Portal now has one
route inventory for Character and Server Notebook workspaces; no query-string Server Notebook
selection remains. `npm run dev:mock` provides typed, browser-local Component Library and Server
Notebook/Conversation Board fixtures with no `/api` calls; other business paths remain explicitly
unavailable rather than falling through to live data. The operator/developer docs now describe
live versus mock commands and the mock boundary. CI builds both bundles, and the credential-free
Railway smoke verifies declared top-level Portal deep links serve HTML. Final cross-project
validation passed locally: Python Ruff/Mypy and 659 tests; Portal typecheck, 45 tests, and both
builds; Connector typecheck, 91 tests, and build. The unreachable Advanced Labs root-state
branches were removed. A deployed, authenticated browser smoke remains release execution, not a
claim this branch has been deployed.

### Phase 6 — Conversation Map reading refinement

Status: **complete; commit recorded in this branch's Git history.** The old all-Threads versus first-50-Segments split is now a
client-side Conversation Map: a paginated eight-thread index, selected-thread detail with
six-segment pagination, and a separately paginated collapsible unresolved-membership inbox.
Display labels/summaries are URL-stripped and bounded. This remains a Portal-only derived
projection: no API pagination contract, server/character scope, Thread authority, or reversible
membership semantics changed. The mock Server Notebook supplies ten typed Thread fixtures so the
pagination interaction is reviewable without `/api` access. During Chrome verification, the global
System Intelligence dock was found to make Admin runtime calls even in mock mode; it is now omitted
there and has a focused data-mode test. Portal typecheck, all 48 Vitest tests, production and mock
builds, and `git diff --check` passed. A fresh Chrome mock-route verification confirmed the 8/2
pagination split, automatic selection of the new page's first Thread, selected Segment detail, no
console errors, and no mock API proxy errors. The explicit 720px browser override did not retain a
locator during the tooling resize; after reset the page was healthy, while the CSS's existing 900px
single-column media rule remains covered by build/type validation rather than claimed as a
visual-browser pass.

### Phase 7 — Conversation Relations and Episode pagination

- Present Message Relations as a pageable sticky-note board rather than opaque ID cards.
- Persist bounded sender/reply-target identity snapshots for new Discord `REPLY_TO` evidence,
  without storing message content or guessing missing historic identities.
- Add SQLite-compatible columns for existing deployments; preserve relation revision provenance.
- Replace the Episode Board's implicit twelve-note truncation with explicit pagination for
  filed Episodes and unresolved fragments.

Gate: Portal and connector typechecks/tests, focused Conversation Structure persistence tests,
both Portal builds, diff review, and a mock browser verification of relation/episode pagination.

Status: **complete; commit recorded in this branch's Git history.** Relations are now a
pageable sticky-note board, showing bounded sender/reply-target display-name snapshots instead of
opaque message IDs. New Discord `REPLY_TO` evidence obtains the source name from the captured
turn and resolves its reply parent when Discord exposes it; the backend persists only bounded
identity snapshots and relation IDs, never message content. Existing rows remain valid and show
an explicit unavailable label rather than guessed authors. SQLite startup adds the four snapshot
columns to existing `message_relations_v3` tables; relation revisions preserve those snapshots.
The Episode Board now paginates all filed Episodes and its unresolved fragment list rather than
silently discarding entries beyond twelve. Mock data contains thirteen Relations and fourteen
filed Episodes for review. Portal typecheck and 51 Vitest tests, focused Python Ruff/Mypy and 8
Conversation Structure tests, both Portal builds, and connector typecheck/91 Vitest tests/build
passed; `git diff --check` passed. The local mock dev server started successfully, but this host
does not have the `agent-browser` executable or a callable browser connector, so a final visual
click-through remains a release/manual check rather than a claimed automated result.

## Mock-mode boundary

`live` is the normal Portal mode. It may call same-origin API routes and uses the normal session.
`mock` is a UI review mode: fixtures are bundled in the Portal, all data calls are intercepted by
the typed client boundary, mutation controls are inert or explicitly simulated, and the shell
shows a persistent **MOCK DATA — NO LIVE CONNECTION** indicator. It is not a staging server,
Demo account, authentication bypass, or production data preview.

## Handoff

Release handoff: deploy the branch through the normal review/merge path, then run
`python scripts/railway_smoke.py <public-url> --require-storage`. With an authenticated Admin
session, manually verify Component Library authorization and Character/Server Notebook deep links.
The production bundle retains the existing >500 kB Vite chunk warning; future performance work
should split heavy workspaces deliberately rather than suppress the warning.
