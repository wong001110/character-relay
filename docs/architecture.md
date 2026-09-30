# Architecture and codebase ownership

**Source map plus accepted Room Director target; not a claim that the target is implemented.**
Current source and evidence: [PROJECT_STATE.md](../PROJECT_STATE.md).
Accepted outcomes: [group-chat refactor plan](plans/discord-group-chat-core.md).
The 2026-09-30 direction replaces the old strategy; missing unpublished work is not a baseline.

## Existing physical layout

```text
AGENTS.md                     one AI-Native Development policy
PROJECT_STATE.md              one current progress / takeover record
src/echo_masque/              Python runtime (historical package name retained)
  api/                       FastAPI contracts, composition and routes
  orchestration/             Character / Social Turn orchestration
  persistence/               SQLAlchemy repositories and migrations
  providers/                 model adapters and trace metadata
connectors/discord/src/       Discord ingestion, context, routing and safe delivery
web/src/                     React/Vite daily Portal and optional evaluation UI
tests/                       behavior and integration tests
scripts/                     developer/operator tooling
.github/workflows/           existing verification / explicitly invoked live workflows
docs/                        active plan, ownership, contracts, user/operator references
```

Agent Continuity is an optional environment-side execution aid. The product has no dependency on
its SQLite state, snapshots, Library storage, bootstrap or private ledger. Do not put them in Git.

## Existing source ownership and planned disposition

| Boundary | Current source / consumers | Refactor disposition |
| --- | --- | --- |
| Ingress and sources | Connector `index.ts`, `contextBuffer.ts`, `routing.ts`, `turnIngress.ts`; Python `api/connector_schemas.py` | KEEP safe buffer; SIMPLIFY explicit routing; scoped bounded Reply ancestry and source revision |
| Participation | `participation_planner_v3.py`, `semantic_participation.py`, `api/routes/smart_participation_vnext.py`, `orchestration/social_turn_graph.py` | REPLACE scoring/embedding selection with runtime rules and one Room Director; no permanent planner fallback |
| Structure | `conversation_structure_resolver.py`, `conversation_runtime.py`, structure/runtime repositories | REPLACE mandatory inferred Segment/Thread with message provenance; retain native Discord Thread identity |
| Character context | `context_resolver_v3.py`, `character_turn_context_v3.py`, `connector_runtime.py` | SIMPLIFY focused current evidence plus relevant explicit notes; Character owns recall/tool/expression choices |
| Existing Turn Director | `turn_director.py`, `utility_gateway_contracts.py`, `orchestration/character_turn_graph.py` | RETIRE post-admission reply/recall planning; distinct from the new room-level selector |
| Provider infrastructure | `utility_gateway_router.py`, provider adapters, quotas/credentials | KEEP and reuse Free Token Pool; strict free-only bounded room-selection task; no Jev or second gateway |
| Memory/history | `internal_context.py`, `current_turn_belief_v3.py`, Belief and conversation runtime repositories | REPLACE ordinary automatic writers / lifecycle dependency with explicit notes and source-linked searchable history |
| Relationships | `social_intelligence_v3.py`, `social_event_runtime.py`, relationship repositories/routes | REPLACE numerical state, decay and event/impression simulation with scoped directional notes |
| Expressions | `expression_retrieval.py`, catalog ingestion, Connector Smart Output | SIMPLIFY to optional intent then metadata/sparse resolution; vision only at ingestion if needed |
| Jobs/tools/media | `tool_runtime.py`, `media_tools.py`, `mcp_gateway.py`, `pending_actions_v3.py`, `turn_jobs.py`, `turn_progress.py` | KEEP grants/receipts; separate ingress from slow work; never replay effects for wording refresh |
| Delivery | Connector `delivery.ts`, `webhookManager.ts`, `smartOutput.ts`, `durableRuntime.ts`; Discord identity repository | KEEP unsent/partial/uncertain policy and response-source links; add fresh-draft integration |
| Auth/storage/egress | `auth.py`, `credentials.py`, `security_controls.py`, `network_safety.py`, `api/app.py` | KEEP identity, Demo read-only, credential/URL/DNS and resource boundaries |
| Observation/Portal | provider traces, runtime trace buffer, debug capture and API routes; deployment/feature panels | SIMPLIFY to one correlated interaction view; remove obsolete settings and Roast entry points |

Python paths are relative to `src/echo_masque/` unless otherwise qualified. Inspect actual call sites
and tests before deleting modules: a shared encoder may still serve tool/RAG/media retrieval.
Renaming `echo_masque` or reorganizing every import is not required to deliver this refactor.

## Target responsibilities

Discord normalizes events, stable identities, source revisions, effective platform permissions and
transport. Python owns authorization, budgets, jobs, model invocation and publication. The Portal
uses backend authority rather than enforcing it only in UI.

1. Runtime forms an eligible bounded snapshot. Platform-addressed work routes directly, including
   fair handling of multiple direct requests. Ambiguous batches can call a Room Director.
2. Room Director proposes NONE or deployment + target + mode from public visible evidence. It has
   no tools/private memory/card catalog and does not confer permission or request paid fallback.
3. Runtime validates the proposal and builds current context from the target, readable Reply
   ancestors, a small recent window, selected Character card and relevant permitted notes.
4. Character chooses wording, ignore, on-demand recall/tools and optional expression intent.
5. Runtime resolves expressions, checks freshness/grants and preserves idempotent safe delivery.

No mandatory semantic topic graph, additional supervisor runtime, old Turn Director, pre-selection
embedding relevance, per-role inner-thought loop or rolling summary engine in the target.
The isolated replay harness is evaluation tooling, not a second production orchestration path.

## Data and cutover boundaries

Old conversation, Belief, Episode, relationship and vector data may be discarded at a separately
authorized cutover; compatibility with those rows is not a design constraint. Preserve authored
character content through a validated export/import where practical; imported cards never restore
secrets or grants. Record unsupported fields instead of retaining obsolete runtime dependencies.

The cutover must stop old producers, drain/quarantine active and uncertain work, establish a new
input watermark and rehearse reset/card roundtrip on a disposable database. No automatic startup
purge. New raw messages and response-source evidence remain necessary after a fresh start.
PostgreSQL + pgvector remains the existing production storage topology; no new service required.

Embedding providers are retrieval adapters with provider/model/dimension/version namespaces.
Index documents in bounded batches; ordinary search cannot become synchronous bulk backfill.
No-result or sparse-only retrieval is valid when dense indexes are unavailable; unknown usage is
not reported as free/zero. Removing FastEmbed requires an actual remaining-consumer audit.

## Invariants and verification

Preserve owner/room/native Thread/role/requester scope, deny-by-default tools, credential isolation,
Public Demo read-only, source attribution, media epistemics, delivery receipts and effect idempotency.
Derived notes/indexes inherit source visibility. Drafts and bot claims are not authority or evidence
of external effects. Source deletions and grant revocations are rechecked at the applicable boundary.

For each replaced component: characterize behavior, implement replacement acceptance, wire actual
consumers, delete old entry points/flags/config/docs, run proportional integration and applicable
protected-logic mutation tests. A standalone class or stub pass does not complete production wiring.
Self-review, CI, human-model quality and live deployment acceptance are separate evidence categories.
Temporary offline comparison against a pinned old commit is allowed; a permanent runtime fallback
is not. Do not erase negative security tests because old product behavior is being retired.

## Existing verified extraction

PR #207 introduced `connectors/discord/src/delivery.ts` for confirmed receipt accumulation and
unsent/partial/uncertain fallback policy; both webhook and native split delivery consume it.
`ContextBuffer` has bounded snapshots and edit/delete invalidation. These are retained foundations,
not proof of complete restart history, draft refresh, new Director or old-runtime retirement.
Future actual source moves are recorded here only after they exist; phase progress stays in
PROJECT_STATE.md. Historical documents and old branch logs are navigation, not execution authority.
