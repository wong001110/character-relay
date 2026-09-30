# Architecture and codebase ownership

**Actual source map + accepted lightweight Room Director target.**
Baseline/progress: [PROJECT_STATE.md](../PROJECT_STATE.md). Accepted outcomes and tests:
[group-chat core plan](plans/discord-group-chat-core.md). Target below is not a completion claim.

## Existing layout and retained infrastructure

`src/echo_masque/` is the Python domain/runtime (historical package name is intentional), with
FastAPI in `api/`, existing graphs in `orchestration/`, SQLAlchemy/PostgreSQL in `persistence/`,
provider adapters in `providers/`. `connectors/discord/src/` owns Gateway and transport.
`web/src/` is the React/Vite Portal. `tests/`, `scripts/` and `.github/workflows/` own product
verification/operator commands. No new service topology, supervisor platform or coding-agent
runtime is part of the refactor. Agent Continuity execution state stays outside the checkout.

## Actual baseline ownership and intended disposition

| Boundary | Existing paths | Disposition |
| --- | --- | --- |
| Ingress/source buffer | Connector `index.ts`, `contextBuffer.ts`, `routing.ts`, `turnIngress.ts`; Python `api/connector_schemas.py` | KEEP safety; simplify around source-focused direct routing |
| Delivery | Connector `delivery.ts`, `webhookManager.ts`, `smartOutput.ts`, `durableRuntime.ts`; Python Discord identity/durability repositories | KEEP confirmed/partial/uncertain receipts and no-whole-answer-retry protection |
| Selection | `participation_planner_v3.py`, `semantic_participation.py`, `api/routes/smart_participation_vnext.py`, social-turn graph | REPLACE with rules + one Room Director; no semantic scoring or old fallback |
| Conversation organization | `conversation_structure_resolver.py`, `conversation_runtime.py`, old Segment/Thread repositories | REPLACE permanent semantic graph dependency with raw source/reply/version structure; preserve native Discord Threads |
| Character turn | `character_turn_context_v3.py`, `context_resolver_v3.py`, `orchestration/character_turn_graph.py`, `turn_director.py` | SIMPLIFY focused context; remove inner Director reply/recall planning; Character owns content/tools/recall |
| Utility gateway | `utility_gateway_router.py`, `utility_gateway_contracts.py`, existing provider/quota/credential code | KEEP infrastructure; dedicated Room Director proposal, no second provider pool |
| Durable recall | `internal_context.py`, belief/conversation repositories and Knowledge Fabric tools | REPLACE ordinary Belief/Segment coupling; explicit scoped notes and searchable source history; optional knowledge retrieval |
| Relationships | `social_intelligence_v3.py`, `social_event_runtime.py`, relation records/routes | DELETE numeric/event/decay simulation; small directional notes with actor/scope/version checks |
| Expressions | `expression_retrieval.py`, catalog/Connector expression adapters | SIMPLIFY intent-first sparse metadata resolution; no per-turn dense or vision |
| Tools/media/jobs | `tool_runtime.py`, `media_tools.py`, `mcp_gateway.py`, `pending_actions_v3.py`, `turn_jobs.py`, `turn_progress.py` | KEEP authorization and bounded durable effects; decouple slow work from ingress |
| Observation | provider traces, runtime trace buffer, Discord captures, eventReporter and debug routes | SIMPLIFY metadata-first correlated outcomes, attempts/costs and controlled raw capture |
| Portal | `web/src/DeploymentCenter.tsx`, feature panels/APIs and Python routes | SIMPLIFY daily controls; DELETE Roast and retired settings/consumers, not merely tabs |

These are inspected navigation boundaries, not an exhaustive dependency graph. Verify consumers
and tests before removing modules. Shared FastEmbed consumers include retrieval paths outside
participation; remove the dependency only after every supported consumer has a replacement.

## Target decision and trust boundaries

```text
Discord -> room buffer/provenance -> runtime eligibility/direct routing
  ambiguous -> Room Director (existing Free Token Pool; stateless; public summaries only)
  clear request ----------------------------------------------+
  NONE ends attempt                                           |
  speaker + source proposal -> runtime scope/budget validation -+
  -> focused context + selected card + relevant small notes
  -> Character (answer/ignore; optional retrieval/tools/expression intent)
  -> sparse expression resolver + freshness/current grants -> safe delivery
```

The Room Director chooses participation only. It cannot grant tools, read private character memory,
choose provider permissions, or deliver. Runtime enforces visibility before prompts and before effects.
Its strict null/none decision is distinct from timeout/malformed/unavailable/invalid-selection states.
The old inner Turn Director is not retained behind the new outer Director. Character may decline
without making runtime iterate over other roles. No permanent semantic Thread is needed for replies.

`target_message_id` anchors focus, not the entire context. Context may include permitted raw Reply
ancestors and a bounded room window. Native Discord Threads, authors, requests and credential scopes
remain distinct. New/private sources cannot be inferred from summaries or selected by model fiat.
No full private character cards are sent to the Director; public selection summaries are separate.

## State ownership

Runtime source messages/versions, jobs, effect/delivery receipts, explicit notes, retrieval indexes
and diagnostics are different records. Drafts are not shared history. Notes and indexes inherit
source scope. Raw/history chunks are searchable on demand, not automatically injected per character.
Relationships influence tone only. Retrieval filters authorization before sparse/dense scoring;
query-time misses must not synchronously backfill a history embedding backlog. Embedding spaces
are namespaced by provider/model/dimension/version. Expression lookup uses semantic metadata.

The user permits old application-data reset; retain no compatibility graph or dual store solely
for migration. Prefer exporting portable authored card content without grants/secrets. Reconcile
pending/uncertain effects before a separately approved live cutover; new evidence/receipts remain
required. Accounts, credentials and infrastructure configuration are not incidental reset targets.
PostgreSQL + pgvector remains production storage; SQLite remains development/test or approved input.

## Verification and retirement

Preserve authentication, owner/room/role/requester scoping, Public Demo read-only, egress/DNS checks,
MCP/tool grants, media evidence and delivery idempotency. Retire call sites, composition, producers,
API/UI/settings/env/docs and old behavior-only tests, retaining negative invariants and new coverage.
Benchmark adapters are offline evaluation only and must never be imported as production fallback.
Temporary adapters need a removal gate; no indefinite V3/V4 engines or hidden old defaults.

R1 compares current Planner, rules only and rules + Director, with exact model/source identity,
label provenance, whole-conversation splits, uncertainty and failure-vs-NONE accounting. Production
ambient activation requires actual model evidence, not a mock. Direct/source improvements may
proceed independently. Mutation/fault and affected Python/Connector/Portal/PostgreSQL checks prove
changed boundaries. Browser evidence applies to real changed journeys, not builds alone.

## Already implemented at the baseline

`delivery.ts` centralizes confirmed-receipt accumulation and unsent/partial/uncertain decisions.
`webhookManager.ts` and native split delivery reuse it. Durable uncertainty does not advance dialogue.
`ContextBuffer` owns bounded deep snapshots and edit/delete invalidation. These foundation/P2a
protections exist; the full refactor and lost P3-P6 work do not. Record subsequent implementation
facts in PROJECT_STATE.md and update this map only when ownership actually changes.
