# AI agent module map

Status: **maintained navigation for AI-assisted development**

Use this map after `AGENTS.md` and before editing. It shortens orientation; source, types,
tests, migrations, and canonical contracts remain authoritative. Update only the row affected
by a coherent phase—do not regenerate unrelated documentation.

| Work area | Start in source | Proving tests | Contract / entry point |
| --- | --- | --- | --- |
| Application/API composition | `src/echo_masque/api/app.py`, `src/echo_masque/api/routes/` | API tests in `tests/` | `docs/architecture.md` |
| Auth, credentials, Public Demo | `auth.py`, `credentials.py`, `public_demo.py` | `tests/test_phase15_*.py`, `tests/test_public_demo*.py` | `docs/security.md` |
| Discord ingress and delivery | `connectors/discord/src/`, `api/routes/connectors.py` | Connector Vitest and Discord route tests | `connectors/discord/README.md`, `docs/discord-server-workspace.md` |
| Character turn / Roleplay | `connector_runtime.py`, `orchestration/character_turn_graph.py`, `smart_output.py` | `test_character_turn_graph.py`, `test_roleplay_prompt_composition.py` | `docs/turn-director-prompt-implementation.md` |
| Intelligence Core v3 | `conversation_structure_resolver.py`, `context_resolver_v3.py`, `participation_planner_v3.py` | `test_conversation_structure_*.py`, context/planner tests | `docs/intelligence-core-v3-architecture.md` |
| Utility / Turn Director | `utility_gateway_*.py`, `connector_runtime.py` | `test_utility_gateway_*.py`, `test_turn_director_runtime.py` | `docs/turn-director-prompt-implementation.md` |
| Social intelligence | `social_intelligence_v3.py`, `social_event_runtime.py` | `test_social_event_runtime_v3.py` | Intelligence v3 contract |
| Media and tools | `media_*`, `tool_runtime.py`, `internal_context.py` | `test_media_*.py`, `test_tool_runtime.py` | media/tool contracts named in `docs/agent-handoff.md` |
| Knowledge Fabric scope/content/interpretation/query/context/projection | `persistence/knowledge_fabric_*`, `knowledge_fabric_projection_policy.py`, `knowledge_fabric_ingestion*.py`, `knowledge_fabric_interpretation_policy.py`, `knowledge_fabric_query*.py`, `knowledge_fabric_context.py`, `knowledge_fabric_epistemic_policy.py`, `knowledge_object_storage.py`, `api/routes/knowledge_fabric.py` | `tests/test_knowledge_fabric_phase2.py` through `test_knowledge_fabric_phase5.py`, `test_knowledge_fabric_projection.py`, `test_knowledge_fabric_epistemic_policy.py`, `test_internal_context_knowledge_search.py`, `test_character_turn_context_v3.py`, PostgreSQL foundation tests | `docs/knowledge-fabric-architecture.md`, active Phase 7 plan |
| Legacy Knowledge, RAG, Wiki / Phase 11 compatibility | `knowledge_*`, `server_knowledge_v3_repository.py`, `knowledge_consolidation_v3.py`, Portal knowledge routes/components | knowledge/wiki compatibility tests | `docs/context-rag-v1.md`, Knowledge Fabric Phase 11 plan |
| Observability | `providers/trace.py`, `runtime_trace.py` | `test_provider_trace*.py`, runtime trace tests | `docs/provider-tracing.md` |
| Evaluation / calibration | evaluation services and `api/routes/` | `test_phase14.py`, `test_phase16_*.py` | `docs/phase-14-experiment-matrix.md`, `docs/phase-16-authoring.md` |
| Portal | `web/src/main.tsx`, `web/src/App.tsx`, `web/src/portalRoutes.ts`, `web/src/DeploymentCenter.tsx`, `web/src/ConversationStructurePanel.tsx`, `web/src/conversationThreadMap.ts`, `web/src/conversationRelationBoard.ts`, `src/echo_masque/api/app.py` | `web/src/portalEnvironment.test.ts`, `web/src/conversationEpisodeBoard.test.ts`, `web/src/conversationThreadMap.test.ts`, `web/src/conversationRelationBoard.test.ts`, `tests/test_conversation_structure_v3.py`, `tests/test_conversation_relations_v3.py`, `tests/test_portal_static_routes.py` | `docs/ui-ux-contract.md`, `docs/ui-page-migration-plan.md`, `docs/portal-routing-environments-plan.md`, `docs/portal-development.md` |
| Database foundation / migration | `persistence/database.py`, `schema_migrations.py`, `sqlite_to_postgres_migration.py`, `scripts/migrate_sqlite_to_postgres.py` | `tests/test_database_foundation.py`, storage/deployment regression tests, PostgreSQL CI service | `docs/railway-deployment.md`, `docs/storage-safety.md`, `docs/active-development-plan.md` |
| Test / CI / mutation quality | `pyproject.toml`, `web/stryker.config.json`, `connectors/discord/stryker.config.json`, `.github/workflows/ci.yml`, `.github/workflows/mutation.yml` | pytest/Vitest plus configured bounded mutation scopes and PostgreSQL foundation integration | `docs/mutation-testing.md`, `docs/manual-validation.md` |

## Required handoff record

For every non-trivial phase, update the branch plan or relevant status document with:

1. source, contract, and test evidence used;
2. invariants preserved and authority/security boundaries;
3. focused validation commands and results;
4. the single phase commit hash after the gate passes;
5. intentional omissions and the next concrete takeover action.

If a map row becomes inaccurate because ownership moved, update it in the same commit as the
ownership change. Never place secrets, raw Discord captures, provider prompts, or credentials in
this map or a handoff.
