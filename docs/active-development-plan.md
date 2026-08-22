# Active development plan — v3 observability and documentation cutover

Status: **branch-local execution record — Phases 0–8 complete; ready for PR/live validation**

| Field | Value |
| --- | --- |
| Active branch | `codex/v3-observability-docs-cutover` |
| Starting baseline | `main` at `5f710b3fd381ba219fc1e31a5d567b96e7c15815` |
| Delivery mode | coherent phase batches; at most one implementation commit per phase |
| OpenWiki state | generation brief exists; `openwiki/quickstart.md` has not been generated |
| Current phase | Complete — automated branch gate passed; live checks remain |
| Integration owner | the main/root coding agent for the active session |

This file lets a development agent continue the active branch without relying on chat history. It records branch execution, not merged product truth. Source, tests, schemas/migrations, and the canonical contracts linked below remain authoritative.

## Approved outcome

The current branch has approval to deliver these connected changes in larger phases:

1. Replace ordinary Discord event-log message previews with structured, redacted diagnostic metadata.
2. Add Option B temporary raw debug capture: explicitly enabled, server-scoped, access-controlled, time-limited, separately retained, and failure-isolated. Keep a storage/codec boundary that can later support Option C, a separately encrypted debug archive, without committing to that archive now.
3. Complete the Intelligence Core v3 runtime cutover so the Character turn consumes v3 context/planning authority instead of retaining the old generation path or a Topic/local semantic fallback.
4. Remove verified obsolete compatibility code, flags, unreachable UI, stale tests/configuration, and unsupported product surfaces rather than preserving unused behavior.
5. Improve manual documentation for users, operators, and developers, while treating OpenWiki as a generated agent-orientation layer rather than canonical documentation.
6. Address directly related runtime safety findings that are required for reliable cutover: Discord ingress idempotency/retry behavior, SQLite foreign-key enforcement, controlled migration execution, and failure isolation where confirmed by source/tests.

## Explicitly out of scope

- Building the full Option C external/separate encrypted archive in this branch. This branch only preserves its extension seam.
- Reintroducing Topic authority, Topic fallback, shadow-mode authority, or compatibility UI.
- Treating Telegram or WhatsApp as supported production connectors without an implemented, tested runtime.
- A broad visual redesign unrelated to removing unreachable/unsupported surfaces and making documentation/navigation clearer.
- Hand-writing generated OpenWiki pages or treating branch-local OpenWiki output as the merged baseline.
- Inventing new metrics, API fields, retention values, database behavior, or authority rules without source and contract evidence.

## Source-of-truth and evidence map

Every implementing agent must re-open the exact files it changes; this map is orientation, not permission to infer missing behavior.

### Canonical/manual contracts

- `AGENTS.md`
- `docs/ai-agent-development-workflow.md`
- `docs/agent-handoff.md`
- `docs/README.md`
- `docs/intelligence-core-v3-architecture.md`
- `docs/security.md`
- `docs/provider-tracing.md`
- `docs/discord-server-workspace.md`
- `openwiki/INSTRUCTIONS.md` for generation rules only

### Initial implementation map

| Area | Sources to verify | Proof to locate/update |
| --- | --- | --- |
| Discord structured events | `connectors/discord/src/behaviorDecisionTrace.ts`, `src/echo_masque/api/connector_schemas.py`, `src/echo_masque/api/routes/connectors.py`, `src/echo_masque/persistence/deployment_repository.py`, relevant deployment models | Connector event tests and `tests/test_discord_event_logs.py` or current equivalent |
| Temporary raw capture | Discord message ingress route/schema, deployment/server ownership repositories, auth/admin boundaries, proposed in-memory capture service/store/codec, `src/echo_masque/security/redact.py` | route, authorization, TTL/capacity, scope, restart semantics, audit, and failure-isolation tests |
| Intelligence v3 turn integration | `src/echo_masque/context_resolver_v3.py`, `src/echo_masque/connector_runtime.py`, `src/echo_masque/api/app.py`, `src/echo_masque/api/routes/smart_participation_vnext.py`, `connectors/discord/src/relayClient.ts` | context resolver, planner, connector runtime, Character turn, and API/Connector contract tests |
| Runtime/storage safety | Discord relay retry/ingress code, operation claim/idempotency persistence, `src/echo_masque/persistence/database.py`, migration code, deployment catalog synchronization | duplicate-delivery, retry classification, foreign-key, migration, and per-guild failure tests |
| Obsolete content | `src/echo_masque/config.py`, compatibility schemas/routes, `pyproject.toml`, Connector semantic/planner fallbacks, `web/src/App.tsx`, `web/src/main.tsx`, Deployment Center platform UI, candidate unreferenced modules | import/reference search plus Python, Portal, and Connector tests/builds |
| Documentation | `docs/README.md`, user/operator/developer guides, subsystem contracts, `openwiki/INSTRUCTIONS.md`, `.openwikiignore` when added | link/search review and generated-output review only after OpenWiki is intentionally run |

## Invariants for every phase

- Raw messages, media references, completed Tool results, and external results remain provenance evidence, but private raw text must not leak into ordinary diagnostic events, process logs, docs, exports, or generated wiki.
- Debug capture is off unless explicitly enabled, remains server-scoped and access-controlled, expires automatically, and cannot make message handling fail.
- Owner, Discord Server, channel/thread, deployment, Character, credential, and relationship scope never widens by inference.
- Runtime owns identity, permission, lifecycle, safety, and side effects.
- Intelligence v3 hard cutover does not restore Topic authority, Topic fallback, Topic-scoped Memory/Wiki, or local Connector semantic authority.
- Conversation Thread, Episode, Belief, Evidence Graph, Social State, Context Resolver, and Participation Planner retain the authority boundaries in `docs/intelligence-core-v3-architecture.md`.
- `unresolved` and safe silence/downgrade remain valid outcomes; provider or observability failure is not behavioral evidence.
- Credentials and authorization headers never enter captures, traces, fixtures, docs, or OpenWiki output.
- Public Demo remains server-enforced read-only.
- OpenWiki is disposable generated orientation. Product decisions live in manual canonical contracts.

## Working and commit protocol

For every phase:

1. The main agent records the phase evidence map and assigns non-overlapping work.
2. Sub-agents may research, verify, run tests, or edit their assigned files; they do not commit shared-tree work.
3. Integrate related source, schema, test, and documentation changes into one coherent batch.
4. Use focused reproduction/checks when needed, but do not run the full suite after every small edit.
5. At the phase gate, run the listed complete validation, inspect the combined diff for unrelated changes and secret/raw-content leakage, and repair failures.
6. Create at most one implementation commit for the phase after the gate passes. Do not create checkpoint or test-fix commits.
7. Update this file with status, commands/results, commit hash, deviations, and the next concrete action.

Sub-agent model preference for this branch:

- use `gpt-5.6-terra` for scoped multi-file editing, contract alignment, and implementation work that requires stronger judgment;
- use `gpt-5.6-luna` for repository research, reference checks, test execution, static verification, and concise evidence summaries;
- keep architecture authority, combined-diff review, phase gates, and commits with the main integration agent;
- do not interrupt an already-running coherent task only to change its model.

Allowed phase states are `planned`, `in progress`, `blocked`, and `complete`. A later phase may be researched in parallel, but implementation should not cross an unresolved authority/schema decision from the current phase.

## Phase 0 — branch contract and grounded design

Status: **complete**

Scope:

- establish this active plan and persistent Agent takeover behavior;
- verify branch/base, dirty-tree ownership, canonical contracts, source owners, and existing tests;
- turn Option B, v3 cutover, cleanup, and docs goals into implementation decisions without inventing contracts;
- identify schema/migration and authorization impacts before edits.

Grounded decisions:

- Option B captures the validated Character Relay runtime-ingress payload, not the complete Discord Gateway event. The capture point is the Python `/api/connectors/discord/messages` path so no second raw-content transport is added.
- Option B raw payloads stay in a bounded single-process in-memory store. They do not enter SQLite, WAL, backups, account exports, ordinary Discord events, Provider Trace, or OpenWiki. Restart clears all sessions and records.
- A store/codec protocol separates ingress and authorization from storage. Option B uses an in-memory store and JSON codec; future Option C may supply a dedicated encrypted archive/key without changing callers. Credential Vault is not reused because its durable credential lifecycle is a different contract.
- Raw-capture start, stop, record detail view, and clear are Bootstrap Super Admin-only and audited without payload content. Capture is disabled by default and precisely scoped by connection and guild after deployment/profile validation.
- The proposed Option B product bounds are explicit TTL choices of 15, 60, or 1440 minutes, at most 100 records and 10 MiB per session, FIFO eviction with an exposed eviction count, and one active session per server. Phase 1 tests may tighten these values before they become API contract, but must not leave them implicit.
- Ordinary Discord events remove `trigger_preview` and other nested content-bearing fields. They retain identifiers, reason codes, counts, booleans, timing, and selection metadata. Message-body fingerprints are not added because short messages may be dictionary-recovered.
- Intelligence v3 cutover is split into participation contract, Character Turn context, and projection lifecycle phases. The old `ContextOrchestrator` is not deleted until every real Character Turn consumes v3 context and end-to-end proof exists.
- Explicit mention/reply currently bypasses v3 resolution; Smart Participation returns Segment/Thread/reply-target data that the Connector currently drops; Connector V4/shadow/local fallback fields conflict with the hard-cutover contract. These are Phase 2 contract issues, not Phase 1 logging work.
- Entity Grounding, Evidence Graph, Knowledge Gap Discovery, Episodic SQL RAG, and Knowledge Consolidation files are not proof of production integration. Phase 4 must either wire them with scoped idempotent lifecycle tests or remove orphan composition; it must not document them as live merely because modules exist.

Validation gate:

- documentation diff/read-through;
- path/link/reference search for every file named as current authority;
- `git diff --check` and `git status --short`;
- no full product test suite for this documentation/design phase.

Commit gate: one consolidated branch-foundation/documentation commit only after the plan and design evidence are internally consistent.

Validation result: all named evidence paths exist; the combined workflow/plan diff passed `git diff --check`; product tests were intentionally not run because Phase 0 changes only development workflow and branch-local documentation.

Next takeover action: implement the in-memory Option B batch without intermediate commits, then run the Phase 1 Python/Connector/Portal gate once for the combined change.

## Phase 1 — Discord observability Option B

Status: **complete**

Scope:

- remove raw `trigger_preview`-style content from ordinary Discord decision events;
- retain useful structured fields such as event/decision type, identifiers, reason codes, bounded counts/timings, correlation/operation IDs, and booleans; do not add a recoverable message-body fingerprint;
- add explicitly enabled server-scoped temporary capture with TTL and capacity bounds, Bootstrap Super Admin viewing/clearing authorization, payload-free audit events, and in-memory retention separate from normal event logs;
- centralize capture storage/encoding behind an interface that can later use a separate Option C encrypted archive/key without changing ingress or authorization callers;
- make capture write/prune/view failures non-blocking to Discord message processing.

Required gate:

- relevant Python lint/type checks and focused API/repository/security tests;
- Connector typecheck and complete Connector tests/build when Connector code changes;
- authorization, disabled-by-default, scope isolation, TTL/pruning, restart/stop semantics, capacity eviction, deduplication, audit, no-store response headers, and failure-isolation coverage;
- diff inspection confirming ordinary event records contain no raw message preview.

Commit gate: one Option B implementation commit after all Phase 1 checks pass.

Delivered contract:

- ordinary Discord events and process/heartbeat errors now contain structured diagnostics only; nested snake_case/camelCase content fields and raw exception messages are removed at both Connector and persistence boundaries;
- Option B is a Super Admin-only, connection+guild-scoped, explicitly started process-memory capture for actual direct and Social Turn generation ingress, with durable replay excluded;
- TTL choices are 15/60/1440 minutes; limits are 100 records/10 MiB per session, 500 records/50 MiB globally, and 500 retained session summaries; FIFO eviction, deduplication, replacement, stop, expiry, restart, audit rollback, and failure isolation are covered;
- raw detail is fetched only on explicit reveal with `Cache-Control: no-store`; start/stop/reveal/clear audits contain identifiers and counts only;
- the store/codec Protocol is the Option C extension seam; no durable/encrypted archive was implemented in this phase.

Validation result:

- Python changed-file Ruff passed; strict mypy passed for 5 touched source files; focused capture/event-log pytest passed with `11 passed` and one existing Starlette/httpx deprecation warning;
- Discord Connector typecheck and production build passed; complete Vitest passed with `26 files, 131 tests`;
- Portal typecheck and production build passed; complete Vitest passed with `12 files, 36 tests`; Vite retained the existing large-chunk advisory;
- combined and staged diff/static review found no production `trigger_preview`, raw exception-message logging, raw SQLite/WAL capture, secret-like additions, unrelated build artifacts, or whitespace errors.

## Phase 2 — Intelligence v3 participation contract hard cutover

Status: **complete**

Scope:

- align Connector types with the actual v3 `/api/smart-participation/resolve` response, including authoritative speaker plan, reply targets, Segment/Thread identity, grounding, and sufficiency;
- remove `DiscordV4Participation*`, `/semantic-score` fallback, shadow parity/conversation-planner fields, and local semantic speaker fallback;
- make Smart Participation resolver failure fail-silent with structured diagnostics instead of restoring Connector semantic authority;
- retain explicit mention/reply, security, scope, cooldown/rate-limit, and delivery hard gates because they are deterministic Runtime evidence rather than competing intelligence authority;
- delete the v4 schema bridge and dead v4/planner settings only after all callers/tests use the v3 contract.

Required gate:

- Python `/resolve` API integration and v3 schema/planner tests;
- Connector participation contract tests, typecheck, complete tests, and build;
- Python Ruff and strict mypy for the touched batch;
- hard-cutover reference/static guards covering Connector source as well as Python.

Commit gate: one participation-contract cutover commit. Do not mix Character prompt/context replacement into this phase.

Delivered result:

- Connector ordinary-message selection now accepts only a runtime-validated, authoritative Conversation Intelligence v3 plan; malformed/failed/empty responses remain silent and never call the retired semantic fallback;
- Segment/Thread, reply-target, grounding, sufficiency, plan reason, and guidance provenance are decoded and retained for the Phase 3 Character-turn handoff;
- explicit audience plus deterministic scope, profile, cooldown/rate, and delivery gates remain intact and fail closed;
- Python filters candidates against the actual Discord destination, returns authoritative empty plans for every resolver input-stage failure, and isolates reply-target persistence failure;
- the v4 schema bridge, unused Conversation Planner implementation/settings, Connector shadow/parity/local semantic/follow-up authority, and their obsolete tests/config were deleted.

## Phase 3 — ContextResolverV3 for every Character Turn

Status: **complete**

Scope:

- introduce one app-level v3 turn service (or an equivalent grounded composition) used by mention, reply, Smart Participation, and Social continuation;
- reuse a Segment already resolved for the message or observe explicit turns once in Python, then run the runtime coordinator and current-turn correction before model generation;
- supply bounded Knowledge/Wiki/Belief/Episode/Entity/Social/Pending Action evidence through one `ContextBundleV3` and inject its prompt sections into the real provider request;
- remove duplicate Knowledge/recall/social context injection only after the replacement path is proven; do not create a third parallel context layer;
- preserve empty-bundle/unresolved/fail-silent behavior without falling back to Topic or local semantic authority.

Required gate:

- explicit mention and reply v3 context tests;
- Smart resolve plus `/messages` Segment reuse and no-duplicate observation tests;
- correction shield before provider call and scoped Belief/Episode/Social/Knowledge tests;
- proof that `ContextBundleV3.prompt_sections()` reaches the provider request;
- resolver failure tests showing empty/unresolved/silent behavior with no old-authority fallback;
- Python Ruff, strict mypy, and affected v3/Character-turn tests.

Commit gate: one Character Turn context cutover commit after the old generation authority has no live consumer.

Delivered result:

- one app-level `CharacterTurnContextV3Service` now serves mention, reply, Smart Participation, sequential Character turns, and Social-turn Character execution;
- authoritative v3 reply decisions reuse their persisted Segment, while explicit turns resolve and observe the current message once; a stale persisted Thread hint cannot override current Segment membership;
- the real provider prompt now receives bounded v3 live context, Beliefs, perceived Episodes, Entities, Knowledge, Server Wiki, Social state, Pending Actions, correction shield, and server-local time;
- current-turn correction extraction is shared between `/resolve` and generation with a durable revision-event guard, and its Utility usage remains observable;
- context assembly failure terminates the graph as structured safe silence before provider execution, with no old ContextOrchestrator, CharacterRecall, Topic, or Connector semantic fallback;
- Media handling, sleeping/presence wake-up, Smart Output authorization, Tool execution, and deterministic Runtime gates remain in their existing owners.

Validation result:

- changed-file Ruff passed and strict mypy passed for 10 source/test files;
- 51 focused context, participation, Character/Social graph, media, routing, and provider-prompt tests passed;
- independent Luna review added explicit-turn observe-once, correction reuse, provider prompt handoff, server-time context, and no-provider-on-context-failure proof;
- combined Phase 3 diff review found no old prompt fallback, duplicate recall/social injection, scope widening, raw-message logging, or unrelated behavior rewrite.

## Phase 4 — Intelligence v3 projection and lifecycle completion

Status: **complete**

Scope:

- connect Conversation Runtime observation to required Entity/Evidence/Episode/Knowledge Gap projections with explicit source and scope boundaries;
- make replay of the same message, Segment, Episode, edge, or index idempotent;
- allow Entity grounding only from explicit evidence and keep Knowledge Gap discovery as candidate state until accepted evidence resolves it;
- give Knowledge Consolidation an explicit checkpoint/manual lifecycle or remove orphan app composition rather than representing it as active;
- add direct tests for Context Resolver, Entity Grounding, Evidence Graph, Knowledge Gap, Episode indexing, consolidation lifecycle, replay, and owner/server isolation.

Required gate:

- focused v3 repository/service/lifecycle tests plus replay and scope tests;
- Python Ruff, strict mypy, and the complete Python suite at the phase gate;
- diff review for duplicate derived rows, incorrect scope, raw-content snapshots, and orphan composition.

Commit gate: one v3 projection/lifecycle commit.

Delivered result:

- Conversation Runtime now projects scoped relation, membership, and Episode evidence through one
  best-effort coordinator; individual derived-edge failures do not fail message observation.
- Edge, Episode, membership, and consolidation replay is deterministic and idempotent; rejected or
  superseded evidence is not silently reactivated.
- Entity grounding requires explicit evidence, Knowledge Gaps remain scoped candidate state, and
  the owner-authenticated server-profile endpoint provides an explicit manual consolidation
  checkpoint lifecycle.

Validation result: changed-file Ruff and strict mypy passed; 14 focused projection, conversation
structure, and no-Topic-authority tests passed; replay, failure isolation, endpoint ownership, and
wrong-guild isolation were independently verified. The integrated full Python suite remains a
Phase 6/8 gate rather than an extra commit boundary.

## Phase 5 — runtime and persistence reliability

Status: **complete**

Scope:

- prevent generic retries from duplicating non-idempotent Discord message/tool/provider work by adding or reusing a grounded ingress operation contract;
- enable and test SQLite foreign-key enforcement only after auditing existing manual deletion/trigger paths;
- replace unconditional startup hard-cutover migration with a recorded, repeat-safe version ledger and test fresh, legacy, interrupted, and restarted paths;
- isolate per-guild catalog synchronization failures so one guild does not block unrelated deployments;
- include Option B/v3 lifecycle cleanup where durable metadata exists, without persisting Option B raw payloads.

Required gate:

- duplicate-ingress/retry, operation claim, foreign-key, startup migration, and catalog failure-isolation tests;
- fresh-database and representative existing-database upgrade tests;
- Python Ruff, strict mypy, and affected persistence/API suites;
- Connector typecheck, complete tests, and build;
- explicit storage-safety, backup, recovery, and upgrade-path review.

Commit gate: one reliability/migration commit. If the upgrade design cannot be safely bounded, split it to a dedicated branch instead of partially landing it here.

Delivered result:

- ordinary Discord Character ingress uses a Runtime-derived operation/step identity and durable
  generation replay plus delivery claim/ack/uncertain semantics; caller IDs and message text are
  excluded from identity, unknown restart outcomes do not re-run Character generation, and durable
  error persistence/HTTP responses contain classifications rather than raw upstream text;
- Connector generation retries are conservative while explicit durable claim/ack calls remain
  retryable, and normal Discord sends are claimed before the platform side effect;
- every SQLite connection enables foreign keys, audited Character deletion paths remove dependent
  Key Group rows, and the v3 hard cutover uses a repeat-safe persistent ledger with a one-replica
  startup guard and post-rebuild foreign-key checks;
- Discord catalog sync partitions visible, successful, and failed Guilds so one failure preserves
  its prior catalog, partial media failure preserves prior inventory, and catalog failure cannot
  block deployment refresh.

Validation result: changed-file Ruff and strict mypy passed for 17 source/test files; the affected
durability, API, migration, storage, account, catalog, Option B, and no-Topic suites passed; Discord
Connector typecheck, all 94 tests, and production build passed. Independent review regressions for
restart uncertainty, concurrent claim, safe errors, excluded-channel silence, and catalog partition
validation were repaired before commit.

## Phase 6 — obsolete-code and unsupported-surface removal

Status: **complete**

Scope:

- delete only code proven unused by import/reference search plus tests/builds;
- remove obsolete compatibility settings/routes/tests after Phases 2–4 migrate their consumers;
- remove unreachable hidden-lab/admin UI imports and candidate orphan modules only after verifying runtime and dynamic imports;
- remove or hide unsupported Telegram/WhatsApp creation surfaces while Discord remains the implemented production connector;
- preserve user-authored Smart Participation profile match data even if misleading `topics` naming is later migrated; it is not Conversation Topic authority;
- preserve raw evidence and supported user data; schema/data deletion requires an explicit reviewed migration.

Required gate:

- repository-wide reference search for each deletion;
- Python Ruff, strict mypy, and full Python test suite;
- Portal typecheck, complete tests, and production build;
- Connector typecheck, complete tests, and production build;
- diff review for accidental feature, authority, or data removal.

Commit gate: one consolidated cleanup commit after all three project surfaces pass.

Delivered result:

- the production-unused ContextOrchestrator/CharacterRecall/legacy routing, continuation, semantic
  signal, Utility RAG guard, and unused Smart Participation outcome chains were removed after live
  v3 trace/context types moved to `character_turn_context_types.py`;
- Connector-only legacy Turn Intelligence telemetry and health fields with no v3 producer were
  removed while current context/RAG diagnostics remain;
- Portal and backend creation paths are Discord-only; legacy WhatsApp/Telegram records retain their
  schema union and read/delete compatibility, with no data migration or deletion;
- enabling SQLite foreign keys exposed historical parent/child fixture ordering and Target deletion
  behavior. Fixtures now insert parents explicitly, and deleting owner access preserves the hidden
  Target row required by historical Trial Runs rather than deleting history or leaving an orphan.

Validation result: repository-wide deleted-reference search returned no source/test consumers;
Python Ruff passed, strict mypy passed for 338 source files, and all 624 tests passed; Portal
typecheck, 38 tests, and production build passed; Discord Connector typecheck, 91 tests, and build
passed. Warnings remain limited to existing dependency/collection notices, one fixture serializer
warning, and Vite's existing large-chunk advisory.

## Phase 7 — user-friendly docs and OpenWiki readiness

Status: **complete**

Scope:

- organize manual documentation by user, operator, developer, canonical contract, and historical/reference audience;
- make Discord setup/debugging, deployment, security/retention, Intelligence v3 ownership, development, testing, and release entry points easy to find;
- keep stable links or explicit redirects/index mapping when reorganizing existing canonical paths;
- add `.openwikiignore` and refine generation instructions; do not hand-write `openwiki/quickstart.md`;
- run OpenWiki only when explicitly authorized/configured, label branch-local output, and review it for hallucinations, scope widening, obsolete Topic claims, sensitive data, and broken source links.

Required gate:

- docs link/path/reference review and `git diff --check`;
- verify current settings/commands against source, package files, and workflows;
- relevant docs-facing UI/build checks if navigation code changes;
- OpenWiki generated-diff review only if generation is intentionally performed.

Commit gate: one consolidated documentation/readiness commit. Prefer a separate post-merge OpenWiki refresh from updated `main` for generated pages.

Delivered result:

- the documentation front door now routes users, operators, developers, AI agents, contract readers,
  and historical researchers to short audience-specific indexes without moving canonical files or
  breaking their stable paths;
- a first-reply Discord guide and a structured-events-first/Option-B-second debugging guide provide
  executable setup, privacy, retention, and incident steps; the Connector reference now uses the
  source-backed API secret name and documents every current Turn Collector setting;
- stale current-document references to deleted context owners were replaced with the v3 context
  service/types, and control-plane/Smart Participation material that could imply old authority is
  explicitly labelled historical;
- `.openwikiignore` excludes secrets, databases, dependencies, caches, logs, and builds while keeping
  source/tests/docs visible; `openwiki/INSTRUCTIONS.md` records the official code-mode refresh cycle.
  No generated `quickstart.md` was hand-written and OpenWiki was not run because its CLI is not
  installed in this workspace.

Validation result: all 69 root/Connector/docs Markdown files passed a local-link target scan with
zero broken paths; current settings and commands were checked against Python/Connector config and
both package manifests; repository search found no deleted owner/config names in current docs outside
the intentionally historical branch ledger; `git diff --check` passed. No UI navigation code changed,
so no extra docs-facing build was required before the integrated Phase 8 gate.

## Phase 8 — integrated release and handoff gate

Status: **complete**

Scope:

- review all phase commits and the full branch diff against the starting baseline;
- reconcile canonical docs, source/types, migrations, and tests;
- run the complete supported Python, Portal, and Discord Connector validations once for the integrated branch;
- record remaining live deployment/manual checks without fabricating results;
- prepare the PR evidence map, intentional deviations, upgrade/rollback notes, and OpenWiki refresh follow-up.

Required gate:

```text
Python: Ruff + strict mypy + complete pytest
Portal: typecheck + complete tests + production build
Discord Connector: typecheck + complete tests + production build
Repository: git diff --check + secret/raw-content review + migration/upgrade review
```

Commit gate: no routine implementation commit is expected. If the integrated gate finds a real cross-phase defect, assign it to the owning phase, fix and validate it as one coherent final repair batch, and document why the phase gate missed it before committing.

Integrated repair:

- branch review found that pre-Option-B `discord_connector_events` rows could still contain and
  expose old message previews. A new repeat-safe `discord-event-privacy-v1` operational migration
  now normalizes the event message, recursively sanitizes stored details, clears untrusted legacy
  Discord operational error strings, and records completed/failed/retried state in a dedicated
  ledger. The API applies the same sanitizer on read as defense in depth;
- Runtime/provider failures stored on Deployments now retain only a bounded error type/reason code,
  not exception text;
- the unconsumed `/semantic-score` compatibility route, Utility participation Tie-break/Turn
  Intelligence chain, shadow trace fields, and retired Behavior Notebook candidate/E5 event panel
  were removed. Semantic Character profiles and v3 participation scoring remain live;
- final docs corrections distinguish Super Admin Connection creation from regular-user Server
  claiming, point structured events to Deployment Center, and keep `.env.example` visible to
  OpenWiki while excluding actual environment files.

Integrated validation result:

```text
Python: Ruff passed; strict mypy passed for 339 source files; 622 pytest tests passed
Portal: typecheck passed; 13 files / 38 tests passed; production build passed
Discord Connector: typecheck passed; 17 files / 91 tests passed; production build passed
Repository: Markdown local-link scan passed; git diff check, secret-pattern review,
            raw-content boundary review, and migration/upgrade review passed
```

Existing non-blocking warnings are the Starlette/httpx deprecation, pytest collection notices,
one Pydantic fixture serializer warning, and Vite's large-chunk advisory.

Intentional follow-up: the persisted/API field named `semantic_thread_id` currently carries the v3
`conversation_thread_id`. It executes no Topic or shadow authority, but renaming it requires an
explicit compatibility/data-contract migration and is not hidden inside this release cleanup.
Generated OpenWiki output remains absent because the CLI is not installed; refresh it from updated
`main` in a dedicated docs branch.

Required live checks remain the real Discord Option B workflow, a representative production-copy
SQLite upgrade plus backup/restore rehearsal, and Railway single-replica/Volume persistence. There
is no application-level downgrade migration; rollback to an older release requires restoring the
pre-upgrade SQLite backup/Volume snapshot.

## Phase ledger

| Phase | Status | Validation evidence | Commit | Next action |
| --- | --- | --- | --- | --- |
| 0. Contract/design | complete | branch/base, contracts, source paths, Option B boundary, v3 call graph, and combined doc diff verified; no product tests by design | `3a26bea` | Phase 1 started |
| 1. Discord Option B | complete | Python Ruff/mypy + 11 focused tests; Connector typecheck + 131 tests + build; Portal typecheck + 36 tests + build; privacy/static review | `f18ba86` | Phase 2 ready |
| 2. v3 participation contract | complete | changed-file Ruff passed; strict mypy passed for 6 files; 28 focused Python tests passed; Connector typecheck + 90 tests + build passed; Luna authority/scope review and static hard-cutover guards passed | `113ed69` | Phase 3 ready |
| 3. v3 Character Turn context | complete | Ruff + strict mypy passed for 10 files; 51 focused tests passed; Luna provider/failure/reuse review passed | `2e9889f` | Phase 4 started |
| 4. v3 projection lifecycle | complete | Ruff/mypy; 14 focused lifecycle/structure/no-Topic tests; Luna replay, scope, endpoint and failure-isolation review | `0cadcc0` | Phase 5 completed |
| 5. Reliability/storage | complete | Ruff/mypy; affected Python durability/storage/API suites; Connector typecheck + 94 tests + build; independent restart/concurrency/privacy review | `86f6970` | Phase 6 started |
| 6. Cleanup | complete | deleted-reference audit; Ruff/mypy + 624 Python tests; Portal 38 tests/build; Connector 91 tests/build | `7315910` | Phase 7 started |
| 7. Docs/OpenWiki readiness | complete | 69 Markdown files / 0 broken local links; settings/commands/source audit; deleted-owner search; diff check | `5b8c74c` | Phase 8 started |
| 8. Integrated gate | complete | Ruff/mypy + 622 Python tests; Portal 38 tests/build; Connector 91 tests/build; link/secret/raw/migration/diff review | final repair/handoff commit; resolve from Git history | open PR, perform live checks, then post-merge OpenWiki refresh |

## Handoff update template

Before yielding this branch, replace the relevant ledger row and append a concise entry here:

```text
Date/time zone:
Agent/session:
Phase and status:
Evidence/contracts read:
Files/change surface:
Validation commands and exact result:
Commit hash (only after gate):
Intentional deviations:
Unresolved risks/conflicts:
Next concrete action:
```

Do not include credentials, raw Discord content, private traces, or secret-derived values in the handoff.

### 2026-08-23 workflow handoff update

```text
Date/time zone: 2026-08-23, Asia/Kuala_Lumpur
Agent/session: /root/workflow_handoff sub-agent
Phase and status: Phase 0 in progress
Evidence/contracts read: AGENTS.md; docs/ai-agent-development-workflow.md; docs/agent-handoff.md; docs/README.md; openwiki/INSTRUCTIONS.md; docs/intelligence-core-v3-architecture.md; docs/provider-tracing.md; docs/security.md; docs/discord-server-workspace.md
Files/change surface: AGENTS.md; docs/ai-agent-development-workflow.md; docs/agent-handoff.md; docs/README.md; docs/active-development-plan.md
Validation commands and exact result: current branch/base confirmed; every named initial implementation path exists; git diff --check passed for tracked changes; active-plan trailing-whitespace scan pending final integration; no product tests run by design
Commit hash (only after gate): none; sub-agent did not commit
Intentional deviations: OpenWiki quickstart was not read because it does not exist; no generated OpenWiki page was hand-written
Unresolved risks/conflicts: product code is unchanged; Phase 1 API/UI wording must clearly say runtime-ingress capture rather than complete Discord Gateway capture
Next concrete action: main agent reviews and integrates this documentation batch, reruns the Phase 0 documentation gate, creates the single Phase 0 commit, then starts Phase 1
```

### 2026-08-23 Phase 1 handoff update

```text
Date/time zone: 2026-08-23, Asia/Kuala_Lumpur
Agent/session: /root with backend, Connector, Portal, Luna audit, and Terra safe-error sub-agents
Phase and status: Phase 1 complete; Phase 2 ready to start
Evidence/contracts read: AGENTS.md; docs/ai-agent-development-workflow.md; docs/agent-handoff.md; docs/README.md; docs/security.md; docs/provider-tracing.md; docs/discord-server-workspace.md; docs/intelligence-core-v3-architecture.md; openwiki/INSTRUCTIONS.md; current API schemas/routes/repositories, Connector routing/reporter/types, Portal Behavior Notebook, and related tests
Files/change surface: Discord Connector structured events/process diagnostics; Python in-memory capture store/admin API/ingress hooks/persistence sanitizer; Behavior Notebook capture UI/API; security/operator/manual docs and this execution record
Validation commands and exact result: changed-file Ruff passed; strict mypy 5 source files passed; focused pytest 11 passed with one existing dependency warning; Connector typecheck/build passed and complete Vitest 26 files/131 tests passed; Portal typecheck/build passed and complete Vitest 12 files/36 tests passed; staged diff/privacy/secret/whitespace scans passed
Commit hash (only after gate): phase commit; resolve from Git history
Intentional deviations: Option C archive remains an interface seam only; OpenWiki generation was not run; complete Python suite is deferred to the v3 lifecycle/cleanup/integrated gates defined above
Unresolved risks/conflicts: Character-count fields represent their named ingress/decision text and may differ for burst composition; no raw-content risk results. Production multi-replica capture remains out of scope for memory-only Option B
Next concrete action: begin Phase 2 by reconciling the actual `/api/smart-participation/resolve` response with Connector consumers, then remove v4/shadow/local semantic authority as one tested batch
```

### 2026-08-23 Phase 2 handoff update

```text
Date/time zone: 2026-08-23, Asia/Kuala_Lumpur
Agent/session: /root with Terra Python/Connector implementation agents and Luna deletion/authority reviews
Phase and status: Phase 2 complete; Phase 3 ready to start
Evidence/contracts read: AGENTS.md; docs/ai-agent-development-workflow.md; docs/agent-handoff.md; docs/README.md; docs/intelligence-core-v3-architecture.md; openwiki/INSTRUCTIONS.md; v3 request/response schemas; Discord routing/runtime gates; deployment scope repository; focused tests
Files/change surface: Discord v3 resolve client/runtime validation and authoritative routing; Python resolve failure/scope boundary; dead v4/Conversation Planner/shadow/local semantic code and obsolete tests/config; canonical ownership maps and this execution record
Validation commands and exact result: changed-file Ruff passed; strict mypy 6 files passed; focused pytest 28 passed with one existing dependency warning; Connector typecheck passed and complete Vitest 17 files/90 tests passed; production build passed; hard-cutover/static/diff review passed
Commit hash (only after gate): phase commit; resolve from Git history
Intentional deviations: independent Portal/API semantic-profile inspection remains because it is not a Connector fallback; full Segment/Thread/reply-target injection into Character provider payload is assigned to Phase 3
Unresolved risks/conflicts: docs/smart-participation-v3.md remains a clearly marked historical implementation note pending Phase 7 documentation reorganization
Next concrete action: trace mention/reply/Smart/Social paths into the Character provider request, then implement one app-level v3 turn context composition with Segment reuse and no duplicate observation
```

### 2026-08-23 Phase 3 handoff update

```text
Date/time zone: 2026-08-23, Asia/Kuala_Lumpur
Agent/session: /root with Terra implementation tracing and Luna test/review support
Phase and status: Phase 3 complete; Phase 4 in progress
Evidence/contracts read: AGENTS.md; docs/ai-agent-development-workflow.md; docs/agent-handoff.md; docs/README.md; docs/intelligence-core-v3-architecture.md; openwiki/INSTRUCTIONS.md; Connector ingress; Character/Social graphs; v3 context/structure/runtime repositories; Knowledge/Wiki/Belief/Social sources and focused tests
Files/change surface: app-level v3 Character-turn context service; ContextResolver perceived-Episode/social/time inputs; runtime/provider prompt handoff; graph fail-silent branch; shared correction path; removal of duplicate CharacterRecall/social prompt injection; focused tests and this execution record
Validation commands and exact result: changed-file Ruff passed; strict mypy passed for 10 files; 51 focused pytest cases passed with existing dependency/fixture warnings only; diff and authority review passed
Commit hash (only after gate): phase commit; resolve from Git history
Intentional deviations: compatibility trace/Smart Output data classes remain temporarily in context_layer.py, but ContextOrchestrator itself has no production composition or prompt authority; cleanup is assigned to Phase 6
Unresolved risks/conflicts: Phase 4 must make derived projections replay-safe and either give Knowledge Consolidation an explicit lifecycle or remove its orphan app composition
Next concrete action: integrate Terra's evidence/Episode replay changes, add projection coordinator/lifecycle tests, then settle the consolidation trigger before the Phase 4 full Python gate
```

### 2026-08-23 Phase 8 handoff update

```text
Date/time zone: 2026-08-23, Asia/Kuala_Lumpur
Agent/session: /root with Terra branch/privacy audit and Luna Portal/Connector gates
Phase and status: Phases 0–8 complete; automated branch gate passed; ready for PR and live validation
Evidence/contracts read: AGENTS.md; AI workflow/handoff/docs indexes; active plan; v3 architecture; security/debug/storage/Railway contracts; current source/types/tests; official OpenWiki repository/CLI/quickstart documentation
Files/change surface: Phase commits listed in the ledger plus final legacy Discord privacy migration/read guard, safe Runtime error classification, retired semantic-score/Tie-break/Turn Intelligence and Behavior Notebook selection removal, final docs corrections
Validation commands and exact result: Python Ruff passed; strict mypy 339 source files passed; complete pytest 622 passed with 7 existing warnings; Portal typecheck + 13 files/38 tests + build passed with existing Vite chunk advisory; Connector typecheck + 17 files/91 tests + build passed; 69 Markdown files/0 broken local links; final diff/secret/raw-content/migration review passed
Commit hash (only after gate): final repair/handoff commit; resolve from Git history
Intentional deviations: OpenWiki generation not run because CLI is not installed; semantic_thread_id rename deferred to explicit compatibility/data-contract migration because the current field stores v3 conversation_thread_id without Topic/shadow authority
Unresolved risks/conflicts: live Discord/Railway behavior and representative production-copy upgrade/restore are not fabricated by local tests; older-version rollback requires restoring a pre-upgrade SQLite backup or Volume snapshot
Next concrete action: review/open the PR, back up a representative database, perform the listed live checks, merge, then refresh generated OpenWiki from updated main in a dedicated docs branch
```
