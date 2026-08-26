# Character Relay architecture

Status: **current repository/service map**

This page maps responsibilities to source. It does not replace the detailed authority contracts named below.

## Product and service boundaries

```text
Browser
  -> React Portal (web/src)
  -> FastAPI application (src/echo_masque/api)

Discord Gateway
  -> Discord Connector (connectors/discord)
  -> connector-only authenticated API routes
  -> Python runtime/orchestration

Python runtime
  -> domain services and runtime authority
  -> provider and external capability adapters
  -> SQLAlchemy persistence
  -> PostgreSQL + pgvector for the Knowledge Fabric production contract (SQLite remains a dev/test or migration source)
```

The Portal is a client, not an authority boundary. Authentication, ownership, Demo read-only enforcement, quotas, credentials, deployment scope, tool authorization, and delivery decisions remain server-side.

## Runtime flow

```text
platform event
  -> connector normalization and durable ingress boundary
  -> audience / participation evidence
  -> Social Turn orchestration
  -> Character Turn graph
       -> turn_resolve
       -> turn_context
       -> turn_model
       -> turn_tool_execution -> turn_model (bounded loop)
       -> turn_smart_output
       -> turn_authority
  -> platform renderer and durable delivery
```

The Discord Connector owns Discord Gateway/Webhook mechanics and platform event deduplication. The Python runtime owns character scope, participation/semantic contracts, model/tool authorization, and persistent product state.

## Intelligence Core v3

```text
raw evidence
  -> conversation relations / segments / threads
  -> episodes
  -> entities and evidence graph
  -> beliefs and social state
  -> context resolver
  -> participation planner
  -> Character / Tool runtime
```

Threads are conversation structure, Episodes are durable projections of what happened, Beliefs are revisable interpretations, and Fabric Projections are derived readable caches. Raw evidence remains provenance truth.

The v3 hard cutover removed Topic authority. Topic fallback, Topic lifecycle authority, Topic-scoped durable memory, `topic_id` continuation authority, Topic Wiki identity, and Topic-driven Discovery are forbidden. The complete contract is `docs/intelligence-core-v3-architecture.md`.

## Ownership map

| Responsibility | Primary source |
| --- | --- |
| Application composition/lifespan | `src/echo_masque/api/app.py` |
| HTTP contracts | `src/echo_masque/api/routes/`, API schema modules |
| Configuration | `src/echo_masque/config.py` |
| Authentication/accounts/credentials | `auth.py`, `account_lifecycle.py`, `credentials.py`, related routes/repositories |
| Character/prompt runtime | character routes, `character_prompts.py`, target/provider modules |
| Discord server/deployment state | deployment routes and `persistence/deployment_*` |
| Discord transport/delivery | `connectors/discord/src/` |
| Character/Social orchestration | `src/echo_masque/orchestration/`, conversation runtime modules |
| Conversation structure | `conversation_relations.py`, `conversation_structure_resolver.py`, conversation-structure persistence |
| Belief/entity/evidence | v3 belief/evidence modules and matching persistence |
| Context and participation | `context_resolver_v3.py`, `participation_planner_v3.py` |
| Media perception/delivery | media, planner-media, conversation-media, generated-media modules |
| Knowledge Fabric | `knowledge_fabric_*`, `character_turn_context_v3.py`, `character_turn_context_types.py`, Fabric persistence/routes/Portal panels |
| Tools/scheduling | tool runtime/external modules, scheduler and condition-watch modules |
| Observability | runtime/provider trace modules, repositories, and Admin routes |
| Evaluation/authoring/calibration | scenario, run, matrix, authoring, calibration modules/routes |
| Public Demo | `public_demo.py`, `public_demo_middleware.py`, `public_demo_quota.py` |
| Portal | `web/src/`, shared UI primitives under `web/src/components/` |

Persistence models/repositories live under `src/echo_masque/persistence/`. Do not make a second authority store to avoid changing an existing repository; first determine whether the new state is authoritative, derived, rebuildable, or turn-local.

## Authority and data rules

1. Runtime validates model output and owns identity, scope, permissions, lifecycle, and side effects.
2. Credentials are encrypted or environment-resolved and never serialized into product records, exports, traces, reports, or docs.
3. Owner/server/character visibility may stay the same or become narrower; it must not become wider by inference.
4. Raw messages, raw media references, completed tool results, and external source results are provenance evidence.
5. Derived graph, Fabric Projections, summaries, embeddings, and indexes never outrank their source evidence.
6. Observability failure is diagnostic and must not break a Character request.
7. Public Demo mutation denial is server-owned; UI disabling is only an additional affordance.
8. PostgreSQL + pgvector is the production contract for Fabric; SQLite is not a parallel Knowledge authority.

## UI architecture

```text
design tokens
  -> business-agnostic UI primitives
  -> scrapbook visual objects
  -> Character Relay shared components
  -> feature pages
```

`docs/ui-ux-contract.md`, `docs/ui-component-library.md`, and `docs/ui-page-migration-plan.md` govern UI work. Approved reference images govern composition/hierarchy only; source APIs, types, and tests govern actual data and behavior.

## Evaluation architecture

```text
Scenario / Test Pack
  -> trial or Matrix runner
  -> Character target
  -> Judge
  -> evidence, verdict, snapshot, report
```

Evidence precedes scores. Draft/AI-assisted authoring cannot create executable ground truth without explicit approval. Completed snapshots remain immutable and secret-free.

## Deployment boundary

The root Docker image builds the Portal and serves it with FastAPI. Railway uses one service, one replica, and a persistent Volume mounted at `/data`. Application variables use the `CHARACTER_RELAY_*` prefix. See `docs/railway-deployment.md` and `docs/storage-safety.md`.

## Where proof lives

- Python behavior: `tests/`.
- Portal behavior: co-located `web/src/*.test.ts` files plus typecheck/build.
- Discord Connector: co-located Connector Vitest files plus typecheck/build/container checks.
- Merge gates and deployment smoke: `.github/workflows/`.
- Detailed source-to-test navigation: `docs/agent-handoff.md`.

## Maintainability hotspots and decomposition order

The 2026-08-22 baseline has several oversized coordination modules. Recalculate before planning; the counts are orientation, not limits:

| Module | Baseline lines | Safe first boundary |
| --- | ---: | --- |
| `connectors/discord/src/index.ts` | 3,588 | extract Gateway ingress/event normalization, deployment cache, and delivery adapters behind existing tests |
| `web/src/DeploymentCenter.tsx` | 1,821 | split Server Passport, notebook page orchestration, and deployment editor without changing API ownership |
| `src/echo_masque/persistence/deployment_repository.py` | 1,167 | separate connection/profile/deployment query and lifecycle concerns while retaining one transaction boundary |
| `connectors/discord/src/smartParticipation.ts` | 1,150 | separate evidence collection, scoring, and selection contracts |
| `src/echo_masque/tool_runtime.py` | 1,092 | separate proposal validation, execution, and side-effect/idempotency coordination |
| `src/echo_masque/persistence/matrix_repository.py` | 1,072 | separate definition/task execution, analytics, and lifecycle queries |

Do these as focused behavior-preserving changes with characterization tests; do not combine them with product or schema changes. The Portal production build also currently warns that its main JavaScript chunk exceeds 500 kB. Introduce route/feature-level lazy loading only after measuring the actual navigation and loading behavior, and keep typecheck/Vitest/build as the minimum gate.

Two quality gates remain intentionally explicit rather than guessed: CI does not yet enforce a measured Python coverage floor, and the Portal has no browser end-to-end suite. Establish the coverage baseline from a clean `main` run before selecting a non-regressive threshold. Add the first browser flow around sign-in -> authenticated workspace -> Admin storage access, then expand by production risk; unit tests and a successful build are not substitutes for that flow.
