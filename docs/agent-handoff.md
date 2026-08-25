# AI coding agent handoff

Status: **canonical takeover guide**

This page is the stable handoff for AI-assisted development. It is manually maintained and authoritative only as navigation; source, tests, schemas, migrations, and task-relevant contracts still decide behavior.

## Five-minute takeover

1. Read `AGENTS.md` and `docs/ai-agent-development-workflow.md`.
2. Run `git status --short --branch`, identify the base/merge-base, and do not assume an open PR is on `main`.
3. If `docs/active-development-plan.md` exists and names the branch, resume its current phase and verify its status against Git before editing.
4. Read `docs/agent-map.md`, then the relevant row's source, proving tests, and canonical contract.
5. Read `docs/README.md`, `docs/architecture.md`, and the task-relevant canonical contract.
6. Inspect the exact implementation, types/schemas, persistence objects, and tests for the subsystem.
7. State an evidence map and the invariants that must remain unchanged before editing.
8. Work in coherent phase batches, run the phase validation gate, and leave the active plan ready for the next takeover.

Do not infer a missing endpoint, setting, field, metric, state, permission, or database behavior. Search for it.

## Current baseline

- Product: Character Relay; Echo Masque is its evaluation module.
- Production platform connector: Discord.
- API/runtime: FastAPI + Python under `src/echo_masque/`.
- Portal: React/Vite under `web/src/`.
- Connector: Node/discord.js under `connectors/discord/`.
- Persistence: SQLAlchemy; the Phase 1 PostgreSQL + pgvector foundation is implemented,
  while SQLite remains a development/test and temporary production-migration source.
- Knowledge Fabric Phase 7 is complete on the active branch. Phase 5 adds
  source-aligned FTS/dense/entity-graph retrieval over derived index records and one internal
  `KnowledgeQueryEngine`. `list_effective_corpora()` is the sole server/corpus authorization
  resolver and is applied before each channel ranks. PostgreSQL uses `simple` FTS plus a
  pgvector HNSW index for the E5-small/384 profile; SQLite retains a deterministic test fallback.
  `current` reports local freshness as `insufficient` until an approved freshness schema and
  authorized live lookup are introduced. Phase 6 composes that engine only after a Character turn
  is selected, resolves an existing scope without creating one, removes legacy RAG/Server Wiki
  prompt injection, and uses a fail-closed Character epistemic boundary. Its default admits no
  corpus Evidence until Phase 10's persisted authored policy exists; queries remain non-blocking.
  Live external fallback remains Phase 9 because no source/tool/evidence contract authorizes it.
  Phase 7 adds a Fabric-only, regenerable source-overview Projection with explicit
  SourceVersion/Evidence dependencies, invalidation on a new source snapshot, lazy deterministic
  rebuild, and dependency-first lifecycle deletion. The Character-internal `knowledge.search` Tool
  now shares the same fail-closed Knowledge Context gate; it no longer calls Server Wiki lookup.
  Legacy Wiki tables/API/Portal are deferred compatibility only until the Phase 11 cutover.
  Phase 8a adds a library-only deterministic adapter for an already-authorized Fabric Source:
  manual text, Markdown, OOXML DOCX, and digital PDF bytes become existing immutable snapshot,
  canonical structure, and Evidence records through the Phase 3 service. It neither exposes an
  upload/local-path/network surface nor owns R2/S3 publication. Textless PDFs fail as a typed
  OCR-required outcome; no fabricated text is persisted. Phase 8b adds the similarly library-only
  `git_snapshot` compiler: a trusted caller supplies immutable commit/tree/file bytes; a pure
  policy excludes unsafe paths, secret/key material, dependency/build/cache paths, and undecodable
  bytes before any R2 artifact or Evidence exists. It neither invokes Git nor reads a local path,
  makes network calls, or accepts credentials. The existing ingestion service alone publishes the
  private R2/S3-compatible artifact. New Git commits atomically supersede the prior available
  version for the same Source without deleting its provenance/index rows; a retained commit can be
  reactivated. Generic Source history remains unchanged. External Git/website acquisition and
  freshness authority are Phase 9 work.
  Phase 4's corpus-bound canonical entities,
  evidence-backed runtime-resolution history, conflicting assertions, world events, typed Evidence
  Graph relations, and lifecycle cleanup remain unchanged. Canonical identity is
  `(corpus_id, entity_type, normalized_name)`; matching names never infer cross-corpus identity.
  Phase 3's immutable source versions, canonical content/Evidence, and private Cloudflare
  R2/S3-compatible artifact storage remain unchanged. Phase 2's
  canonical Server tuple `(platform, connection_id, workspace_id)` and explicit
  `KnowledgeServerAdministrator` membership remain unchanged. Only authenticated Super Admin can
  bootstrap/manage membership; owner-scoped Discord profiles and user-to-connection access grants
  are not substitutes. Resume from the Phase 9 record in `docs/active-development-plan.md`.
- Production topology: PostgreSQL + pgvector is the target. While SQLite remains in use,
  keep one app replica and one persistent `/data` Volume.
- Application configuration prefix: `CHARACTER_RELAY_*`.
- Intelligence authority: Intelligence Core v3. Topic authority and Topic fallback are forbidden.
- Public Demo: shared, server-enforced read-only workspace; do not weaken mutation boundaries in the client or API.

Branch/PR status and live deployment health are intentionally not frozen here. Check Git and the relevant CI/deployment system at task start.

## Active development takeover

`docs/active-development-plan.md` is the persistent branch-local handoff for multi-phase work. Use it only when its recorded branch matches the current branch. It should let an agent with no chat history recover:

- the approved scope and explicit out-of-scope work;
- the current phase and its allowed change surface;
- source, contract, and test evidence already established;
- invariants and security/authority boundaries;
- validation already run and validation still required;
- the phase commit gate, unresolved conflicts, and next concrete action.

Do not turn the plan into a second architecture contract. When implementation changes authority or product behavior, update the relevant canonical document and point the plan to it.

For an applicable active plan, use one integration owner: sub-agents may research, verify, test, or edit assigned non-overlapping files, while the main agent reviews the combined diff, resolves evidence conflicts, runs the phase gate, and creates at most one implementation commit for the phase. Do not create checkpoint commits or rerun the full suite after every small change.

## Module, source, and proof map

| Subsystem | Owning source | Proof/tests | Contract |
| --- | --- | --- | --- |
| API composition | `src/echo_masque/api/app.py`, `src/echo_masque/api/routes/` | API and phase tests in `tests/` | `docs/architecture.md` |
| Authentication/accounts/vault | `src/echo_masque/auth.py`, `src/echo_masque/account_lifecycle.py`, `src/echo_masque/credentials.py`, auth/account routes | `tests/test_phase15_*.py` | `docs/phase-15-security.md` |
| Character Cards/prompts | character routes, `src/echo_masque/character_prompts.py`, target modules | `tests/test_character_*.py`, `tests/test_prompt_*.py` | prompt/evaluation phase docs |
| Deployment/server workspace | deployment routes and `src/echo_masque/persistence/deployment_*` | `tests/test_deployments.py`, `tests/test_deployment_*.py` | `docs/discord-server-workspace.md` |
| Discord delivery | `connectors/discord/src/` | co-located Connector Vitest files | `connectors/discord/README.md` |
| Conversation structure | `conversation_relations.py`, `conversation_structure_resolver.py`, conversation-structure persistence | `tests/test_conversation_relations_v3.py`, `tests/test_conversation_structure_*.py` | `docs/intelligence-core-v3-architecture.md` |
| Belief/entity/evidence | `belief_revision_v3.py`, `current_turn_belief_v3.py`, `evidence_graph_v3.py`, matching persistence | Intelligence v3 and belief/evidence tests | `docs/intelligence-core-v3-architecture.md` |
| Context/participation | `context_resolver_v3.py`, `participation_planner_v3.py` | context/planner/participation tests | `docs/intelligence-core-v3-architecture.md` |
| Character/Social Turn | `src/echo_masque/orchestration/`, conversation runtime | character/social graph tests | `docs/langgraph-roadmap.md` |
| Media | `media_*`, `planner_media.py`, `conversation_media.py`, generated-media modules | `tests/test_media_*.py`, planner/generated-media tests | media contracts/roadmaps |
| Knowledge/RAG/Wiki | `knowledge_*`, `character_turn_context_v3.py`, `character_turn_context_types.py`, related persistence | knowledge/context RAG tests | `docs/context-rag-v1.md` |
| Tools/scheduler | `tool_runtime.py`, `tool_external.py`, scheduler/condition-watch modules | tool/watch/scheduler tests | tool-calling docs |
| Observability | `runtime_trace.py`, provider trace modules/routes | runtime/provider trace tests | `docs/provider-tracing.md` |
| Evaluation lab | scenario/test-pack/run/matrix/authoring/calibration modules and routes | Phase 13–16 tests | Phase 14/16 docs |
| Public Demo | `public_demo.py`, middleware/quota, auth/API integration | `tests/test_public_demo*.py` | read-only invariant in `AGENTS.md`/README |
| Portal | feature components/APIs under `web/src/` | `web/src/*.test.ts` | UI contracts and approved references |

Search before relying on a glob or a historical filename; the table identifies ownership areas, not an exhaustive dependency graph.

## Non-negotiable runtime boundaries

- Runtime owns scope, permissions, identity, lifecycle, and side effects.
- Raw messages/media/tool results/external results remain provenance evidence.
- Conversation Threads structure conversation; they are not durable knowledge authority.
- Episodes describe what happened; Beliefs describe revisable current belief.
- Wiki is a derived readable projection and cannot outrank source evidence.
- Relationship/Impression are social intelligence, not factual memory.
- Planner-only media knowledge cannot silently become Character perception.
- `unresolved` is a valid outcome; do not force low-confidence identity or membership.
- Demo remains read-only and credentials never enter logs, exports, traces, docs, or generated wiki.
- Generated UI images govern composition only; current APIs/types/tests govern data and behavior.

## Validation map

```bash
# Python
python -m ruff check .
python -m mypy src
python -m pytest

# Portal
cd web
npm ci
npm run typecheck
npm test
npm run build

# Discord Connector
cd connectors/discord
npm ci
npm run typecheck
npm test
npm run build
```

For changed protected decision logic, also run the configured bounded mutation scope and record
its result or the reason it does not yet apply:

```bash
# Python (Ubuntu CI or an installed WSL distribution)
mutmut run
mutmut export-cicd-stats

# Portal / Discord Connector
cd web && npm run test:mutation
cd connectors/discord && npm run test:mutation
```

See `docs/mutation-testing.md` for the initial scopes, survivor classification, and cadence. Do
not make a full-repository mutation run a routine per-edit check.

Use the root Docker/CI workflows for deployment validation. Live acceptance needs real deployment authority and secrets; never substitute invented local values.

## End-of-task handoff

Record:

- branch/base and scope;
- canonical docs and exact source contracts read;
- tests added/relied on and commands run;
- UI reference, when applicable;
- intentional deviations and adjacent work left out;
- unresolved conflicts or live evidence still required.

For a multi-phase branch, also update `docs/active-development-plan.md` with the current phase status, commands/results, commit hash when committed, and the exact next takeover action.

If architecture changed, update its canonical contract and the affected row in `docs/agent-map.md` in the same coherent phase.
