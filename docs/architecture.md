# Architecture and codebase ownership

**Current source map + accepted target boundaries; incremental implementation on PR #207.**
The merged runtime baseline is recorded in [PROJECT_STATE.md](../PROJECT_STATE.md).
The [group-chat plan](plans/discord-group-chat-core.md) is the accepted target for the next change.
Source and tests prove current behavior; the plan supersedes conflicting old target designs.

## Existing physical layout (P2a adds the focused delivery policy module)

```text
AGENTS.md                     one AI-Native Development policy
PROJECT_STATE.md              one current status / takeover record
src/echo_masque/              Python domain/runtime; historical package name remains intentional
  api/                       FastAPI schemas, composition and routes
  orchestration/             existing Character / Social Turn orchestration
  persistence/               existing SQLAlchemy records, repositories and migrations
  providers/                 provider adapters and traces
  targets/                   model and evaluation target adapters
connectors/discord/src/       Discord Gateway, routing, context and delivery
web/src/                     React/Vite Portal, feature APIs and UI
  components/                shared UI components
tests/                       Python behavior and integration tests
scripts/                     existing development/operator scripts
.github/workflows/           existing verification/deployment workflows
docs/
  plans/                     accepted bounded change plans (only state-linked work is active)
  architecture.md            ownership and migration boundaries
  developer/                 setup and validation commands
  contracts/                 specialized product/security constraints
  user/                      product usage
  operator/                  deployment and incident procedures
  history/                   reference index, never current execution authority
```

No placeholder source packages, new agent runtime or alternative persistence layer is introduced.
The `echo_masque` namespace is a compatibility/package boundary, not an obsolete coding method;
renaming it is not a prerequisite for this work.

## Responsibility boundaries

Discord owns platform ingestion, source-message metadata, acknowledgements, notifications and
transport. Python owns authorization, durable jobs, model/tool budgets and product state. The
model chooses relevant contributions or silence from visible evidence; it does not grant access.
The Portal operates existing APIs and cannot enforce authority on behalf of the backend.

| Work area | Existing entry points | Verification surface |
| --- | --- | --- |
| Ingress, context, Reply identity | `connectors/discord/src/index.ts`, `contextBuffer.ts`, `routing.ts`, `turnIngress.ts`; `src/echo_masque/api/connector_schemas.py` | Connector Vitest; schema/Discord route tests |
| Delivery and webhook source links | `connectors/discord/src/webhookManager.ts`, `smartOutput.ts`, `durableRuntime.ts`; `src/echo_masque/persistence/discord_identity_repository.py` | Partial-send, retry, duplicate-event and identity tests |
| Role turns and prompt assembly | `src/echo_masque/connector_runtime.py`, `character_turn_context_v3.py`, `smart_output.py`, `orchestration/character_turn_graph.py` | `tests/test_character_turn_context_v3.py`, `test_smart_output.py`, `test_interaction_grounding.py` |
| Multi-role selection/continuation | `src/echo_masque/participation_planner_v3.py`, `api/routes/smart_participation_vnext.py`, `orchestration/social_turn_graph.py`; Connector routing/Smart Output | `tests/test_participation_planner_v3.py`, `test_smart_participation_v3_route.py`; Connector tests |
| Scoped notes and recall | `src/echo_masque/internal_context.py`, `context_resolver_v3.py`, `current_turn_belief_v3.py`, `persistence/belief_repository.py`, `persistence/conversation_runtime_repository.py` | `tests/test_memory_recall_review.py`, scoped note/lifecycle tests |
| Relationship retirement/replacement | `src/echo_masque/social_intelligence_v3.py`, `social_event_runtime.py`, relationship persistence and routes | `tests/test_social_event_runtime_v3.py`; new accepted note-update cases |
| Tool execution, media and jobs | `src/echo_masque/tool_runtime.py`, `media_tools.py`, `mcp_gateway.py`, `pending_actions_v3.py`, `turn_jobs.py`, `turn_progress.py`, `targets/prompt_model.py` | Existing tool/MCP/media/job tests plus cancellation and authority cases |
| Identity, storage and egress | `src/echo_masque/auth.py`, `credentials.py`, `security_controls.py`, `network_safety.py`, `api/app.py`, `persistence/` | Account/Demo/credential, PostgreSQL, egress and applicable mutation scopes |
| Observation | `src/echo_masque/providers/trace.py`, `runtime_trace_buffer.py`, `discord_debug_capture.py`, trace/debug API routes; `connectors/discord/src/eventReporter.ts` | Trace redaction, authorization, retention and dropped-event tests |
| Portal and offline evaluation | `web/src/DeploymentCenter.tsx`, feature panels/APIs, `src/echo_masque/api/routes/`, evaluation/authoring services | Co-located Vitest, affected Python tests and real browser journeys |

Paths in one table cell after a directory-qualified path share that area's root unless explicitly
qualified otherwise. Verify file existence and call sites in the checkout; this is navigation,
not an exhaustive dependency graph or test execution receipt.

## Target organization (proposed unless recorded below)

Organize by stable responsibilities rather than phase numbers, agent roles or additional versions.
Preserve the three deployable surfaces; do not split them into new services just to rename folders.

| Boundary | Target responsibility | Safe migration rule |
| --- | --- | --- |
| Conversation core | visible message/provenance selection, bounded participation, draft freshness and final action | Reuse one turn pipeline; choose supported graph/sequential entry based on existing consumers, not a mandatory LangGraph migration |
| Notes / relationships | explicit durable notes, bounded relationship text, scoped history reads | One authoritative store per record; migrate consumers before retiring simulation writers |
| Tools / jobs / delivery | runtime grants, budgets, execution, cancellation, outbox/delivery receipts | Separate execution state from delivery state; preserve idempotency and uncertain outcomes |
| Platform adapter | Discord normalization, permission-aware source fetching, edits/deletes, rendering and transport | Thin `index.ts`; extract coherent ingress/context/delivery modules behind existing interfaces |
| Observation | correlated interaction metadata, usage, outcome reasons and controlled raw capture | Not a second task store; failed diagnostic writes do not change delivery truth |
| Portal / evaluation | focused daily operations, optional advanced research, offline quality checks | Feature-local components and tests; remove Roast consumers rather than hiding only the tab |

Concrete directories may be `conversation/`, `notes/`, `tools/`, `observability/` inside the current
Python package and feature-oriented subdirectories in Connector/Portal, but these are examples,
not mandated empty packages. The implementation agent chooses names after inspecting dependencies.
Record actual moves here. Prefer bounded extraction over a repository-wide import rewrite.

For each move: characterize behavior, move source and relevant tests, update imports/composition,
remove old call sites/flags/routes/exports, then run the changed surface's checks. Avoid permanent
V3/V4 parallel engines, forwarding runtime modules or a fallback that revives a retired behavior.
Temporary migration adapters require a named removal checkpoint in PROJECT_STATE.md. Historical
user data and immutable evaluation/source evidence may remain without an active runtime consumer.

## Invariants across the reorganization

- Runtime owns identity, effective room/Thread permissions, scoped credentials, tool grants,
  side effects, resource budgets, job lifecycles and delivery decisions.
- Public Demo remains server-enforced read-only. Imported cards and notes cannot grant tools.
- Preserve raw source provenance and deletion/retention contracts; generated drafts are not facts.
- Stored execution progress, evidence, long-term notes and diagnostic events are distinct records.
- PostgreSQL + pgvector is the existing production storage contract; SQLite is for development,
  tests or approved migration inputs. This plan does not change production topology.
- Retired Topic authority, Topic-scoped memory and Topic-driven Wiki are not reintroduced.
- Media routing hints do not prove perception. A model must not claim to inspect unavailable media.
- Approved datasets and completed evaluation snapshots keep their approval/immutability boundaries.
- No credentials or raw private transcripts in source, ordinary logs, exports or planning records.

## Documentation organization and retired entry points

Current authority is deliberately small: AGENTS.md (policy), PROJECT_STATE.md (status), this map
(ownership), and the active plan (accepted outcomes/acceptance). Developer/operator/user references
remain separate because they serve different tasks, not parallel development workflows.

The former agent map, handoff, workflow and active-branch-plan files contain **links only**. Their
old policy, stale branch status and execution instructions have been removed. Existing historical
links remain navigable, but cannot start another workflow. Old content remains in Git history.
No OpenWiki generation/bootstrap or fixed Main/Sub topology is part of the current practice.

## Implemented boundary extraction: P2a

`connectors/discord/src/delivery.ts` now owns confirmed-receipt accumulation and the
unsent/partial/uncertain fallback decision. Both `webhookManager.ts` and native split delivery in
`index.ts` use it; there is no second active send policy. The existing durability repository stores
partial receipts and keeps the entire operation uncertain without treating the draft as dialogue.
`ContextBuffer` owns bounded snapshots and edit/delete invalidation; this is not a memory database.
The remaining target moves and runtime retirements are pending in PROJECT_STATE.md.
