# R5-B: retire redundant conversational authority

Self-review, 2026-10-02. Parent: `22483baecfb84e6265a36dfbd8eb734eecb0632a`.
This is a coherent backend retirement slice, not Portal/Connector completion or a rollout.

## Ownership changes

The production app no longer composes a semantic participation scorer, numerical relationship
engine, belief extractor, semantic Conversation Structure/Runtime/maintenance, Discovery/presence
scheduler or Roast/interaction runtime. Pending effects use the separately tested R5-A repository.
Room Routing, source context, explicit notes, scoped history/knowledge search, actual media,
canonical Knowledge Fabric, explicit user reminders, credentials and durable delivery remain.

The unified Expression catalog retains names, tags, manual/ingestion interpretation and exact
owner/connection/guild identity. Selection happens only after the Character supplies an intent.
The old candidate/run/node/retry workflow and incoming-sticker fallback store are deleted.
One-time, explicitly requested metadata suggestions remain available through the existing gateway.

Fresh schemas do not register retired ORM models. An inert allowlist names tables eligible for a
future explicit offline reset; it neither reads them nor deletes them at startup. The Topic guard
exempts only literal set entries after validating the module contains no executable runtime.
Legacy SQLite-to-PostgreSQL transfer refuses retired conversational data until an explicit reset.
Accounts, credentials, authored cards, approved evaluation artifacts and canonical corpora are not
reset targets. No production data was read, deleted, transferred or migrated by this change.

## Faults discovered and repaired

- Pending effect state used to depend on a semantic Thread: extracted in R5-A.
- Account cleanup now uses exact owner-bound RoomScope hashes and independent notes/effects;
  malformed owned scope aborts before deletion. Local legacy claims cannot transfer room evidence
  or effect authority. Unscoped authored notes can be claimed; same-room other-owner data survives.
- Incoming sticker interpretation dropped description/tags/format on the unified catalog path;
  these are now forwarded. Omitted optional metadata does not erase stored values or manual text.
- Knowledge prompt truncation could split JSON or mismatch dropped hits with source IDs. Bounded
  complete untrusted wrappers now map by evidence ID; oversized wrappers are omitted safely.

## Verification receipt

Python 3.13.5; compatible SQLAlchemy 2.0.50. Full backend after core cleanup and strict inert-table
scope guard: `pytest -n 2 -q -o addopts=""`: **1373 passed, 7 skipped**. The final obsolete canonical
runtime-entity bridge removal is covered by the subsequent focused knowledge/database/retirement
suite: **44 passed, 4 skipped**; full head integration is repeated at R6/CI. Whole-source mypy and whole-repo Ruff pass.
Skipped PostgreSQL/live checks are not passes; no Discord/model quality or performance claim.

## Test retirement and replacement map

Old tests solely prescribing removed simulation/selection/extraction are deleted, not skipped.
Negative isolation and source integrity tests are retained or ported to the supported path:

| Old responsibility | Current proving tests |
| --- | --- |
| Planner/semantic selection and targets | `test_room_routing.py`, `test_room_routing_api.py`, `test_room_director_pool.py`, `test_room_routing_replay.py` |
| Semantic context/summary-to-evidence | `test_room_context.py`, `test_explicit_notes.py`, `test_room_delivery_sources.py` |
| Belief/relation extraction and numerical decay | `test_explicit_notes.py`, `test_chat_retirement.py`; numerical/automatic behavior intentionally no longer supported |
| Discovery/sleep/autonomous activity | removed; explicit scheduling retained in `test_scheduled_reminder_service.py` (historical name; see current exact path below) and related route/job tests |
| Knowledge privacy/injection/graph interpretation | `test_fabric_retrieval_review.py`, `test_knowledge_fabric_security.py`, `test_knowledge_fabric_phase4.py` |
| Eager expression workflow and sticker fallback | `test_expression_retrieval.py`, `test_interaction_sessions_and_stickers.py`, `test_room_context.py` |
| Lifecycle and storage boundaries | `test_database_foundation.py`, `test_chat_retirement.py`, `test_knowledge_fabric_hard_cutover.py`, `test_phase13_account_delete.py` |
| Reentry/uncertain effects/fresh drafts | `test_pending_actions.py`, `test_tool_continuation_review.py`, `test_draft_freshness.py`, `test_runtime_durability.py` |

The following exact files contained the intentionally retired behavior (individual function names
remain in Git history). File count/test count reduction is not a quality improvement metric:

- `tests/test_character_learned_state.py` (6 former test functions)
- `tests/test_character_learned_state_history.py` (1 former test functions)
- `tests/test_character_relationships_v2.py` (4 former test functions)
- `tests/test_character_turn_context_v3.py` (12 former test functions)
- `tests/test_conversation_media_provenance_v3.py` (2 former test functions)
- `tests/test_conversation_relations_v3.py` (3 former test functions)
- `tests/test_conversation_runtime_memory_lifecycle.py` (5 former test functions)
- `tests/test_conversation_structure_resolver.py` (3 former test functions)
- `tests/test_conversation_structure_v3.py` (5 former test functions)
- `tests/test_current_turn_belief_v3.py` (5 former test functions)
- `tests/test_deployment_activity.py` (5 former test functions)
- `tests/test_deployment_activity_media.py` (1 former test functions)
- `tests/test_deployment_belief_management.py` (2 former test functions)
- `tests/test_deployment_presence.py` (3 former test functions)
- `tests/test_deployment_presence_rhythm.py` (5 former test functions)
- `tests/test_deployment_presence_sleep_policy.py` (2 former test functions)
- `tests/test_discovery_completion.py` (5 former test functions)
- `tests/test_discovery_conversation_pagination.py` (3 former test functions)
- `tests/test_discovery_domain.py` (3 former test functions)
- `tests/test_discovery_media_inspection.py` (3 former test functions)
- `tests/test_discovery_no_key_sources.py` (2 former test functions)
- `tests/test_episodic_sql_rag.py` (1 former test functions)
- `tests/test_intelligence_v3_migration_ledger.py` (5 former test functions)
- `tests/test_intelligence_v3_projection_lifecycle.py` (7 former test functions)
- `tests/test_knowledge_gap_discovery_v3.py` (5 former test functions)
- `tests/test_participation_admission_policy.py` (7 former test functions)
- `tests/test_participation_planner_v3.py` (4 former test functions)
- `tests/test_planner_media_contract.py` (5 former test functions)
- `tests/test_recall_freshness.py` (2 former test functions)
- `tests/test_recall_media_connector_runtime.py` (1 former test functions)
- `tests/test_room_routing_legacy_replay.py` (4 former test functions)
- `tests/test_semantic_participation.py` (7 former test functions)
- `tests/test_semantic_profile_api.py` (1 former test functions)
- `tests/test_semantic_runtime_memory.py` (6 former test functions)
- `tests/test_smart_participation.py` (2 former test functions)
- `tests/test_smart_participation_generation.py` (2 former test functions)
- `tests/test_smart_participation_v3_route.py` (10 former test functions)
- `tests/test_social_event_runtime_v3.py` (4 former test functions)
- `tests/test_social_identity_presentation.py` (2 former test functions)
- `tests/test_youtube_discovery.py` (4 former test functions)

## Remaining work (not hidden as live testing)

Connector still contains replaced API clients/local bot-loop/configuration. Portal still has old
panels. R5-C removes these consumers and adds supported daily controls/observations. R6 supplies
explicit reset/card portability/replay fence and integrated evidence. No permanent old-runtime
fallback or obsolete schema-preservation requirement is accepted.
