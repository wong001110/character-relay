# Intelligence Core v3 — Phase 0 Dependency Inventory

Branch-local active implementation inventory. This is not generated OpenWiki output.

## Conversation / Topic authority surface

Primary old Topic implementation:
- `src/echo_masque/conversation_topic.py`
- `src/echo_masque/conversation_topic_lifecycle.py`
- `src/echo_masque/conversation_topic_observed.py`
- `src/echo_masque/utility_topic_runtime.py`
- `src/echo_masque/persistence/conversation_topic_models.py`
- `src/echo_masque/persistence/conversation_topic_repository.py`
- `src/echo_masque/persistence/conversation_topic_decision_models.py`
- `src/echo_masque/persistence/conversation_topic_decision_repository.py`

Topic-adjacent graph/shadow paths:
- `src/echo_masque/conversation_graph_topic_shadow.py`
- `src/echo_masque/conversation_graph_shadow.py`
- `src/echo_masque/participation_shadow_v4.py`
- connector participation shadow files under `connectors/discord/src/`

Known tests proving/locking old Topic behavior:
- `tests/test_conversation_topic_memory.py`
- `tests/test_conversation_topic_observed.py`
- `tests/test_topic_rolling_identity.py`
- `tests/test_conversation_graph_topic_shadow.py`

Replacement owner: Phase 1 Conversation Structure + later Phase 10 hard delete.

## Existing Segment / Semantic Thread surface

Current implementation already partially separates Burst from semantic discussion:
- `src/echo_masque/conversation_segmentation.py`
- `src/echo_masque/persistence/conversation_segment_models.py`
- `src/echo_masque/persistence/conversation_segment_repository.py`
- `src/echo_masque/api/routes/deployment_conversation_structure.py`
- `web/src/ConversationStructurePanel.tsx`
- `web/src/conversationStructureApi.ts`

Current weaknesses confirmed in source:
- `SemanticThreadRecord` stores one mutable `summary` plus accumulated `keywords`.
- `ConversationSegmentRecord.semantic_thread_id` acts as direct assignment.
- `update_thread_evidence()` appends recent summaries/keywords into thread identity.
- `conversation_segmentation._utility_decision()` skips Utility when `len(messages) <= 1`.
- deterministic fallback attaches/creates primarily from semantic similarity after local reply clustering.
- Utility capability name is still `topic_intelligence` despite performing burst/thread structure work.

Replacement owner: Phase 1.

## Episode surface

Primary:
- `src/echo_masque/conversation_episode.py`
- `src/echo_masque/persistence/conversation_episode_models.py`
- `src/echo_masque/persistence/conversation_episode_repository.py`
- `src/echo_masque/episodic_sql_rag.py`
- `src/echo_masque/persistence/episodic_sql_rag_models.py`
- `src/echo_masque/persistence/episodic_sql_rag_repository.py`
- `tests/test_conversation_episode_projection.py`
- `tests/test_episodic_sql_rag.py`

Consolidation paths that may still tie Episode lifecycle to Topic/conversation consolidation:
- `src/echo_masque/conversation_consolidation.py`
- `src/echo_masque/conversation_consolidation_events.py`
- `src/echo_masque/layered_conversation_consolidation.py`
- `tests/test_server_knowledge_consolidation.py`

Replacement owner: Phase 2 for Episode formation, Phase 4/8 for downstream knowledge/memory projection.

## Pending Action / Tool continuation

Primary:
- `src/echo_masque/tool_continuation.py`
- `src/echo_masque/tool_runtime.py`
- `src/echo_masque/internal_context.py`
- `tests/test_tool_continuation_deferred_plan_v4.py`
- `tests/test_tool_continuation_deferred_v4.py`
- `tests/test_tool_semantic_continuation.py`

Turn-routing dependencies that may inject Topic/Pending Action decisions:
- `src/echo_masque/turn_intelligence.py`
- `src/echo_masque/character_turn_intelligence.py`
- `src/echo_masque/context_layer.py`
- connector telemetry under `connectors/discord/src/turnIntelligenceTelemetry*`

Replacement owner: Phase 2 standalone PendingAction, Phase 6 Context Resolver, Phase 7 planner cleanup.

## Memory / Belief surface

Core/authored memory:
- `src/echo_masque/persistence/core_memory_models.py`
- `src/echo_masque/persistence/core_memory_repository.py`
- `src/echo_masque/memory_layers.py`
- `tests/test_core_memory.py`
- `tests/test_memory_layers.py`

Conversation Memory vNext:
- `src/echo_masque/persistence/memory_vnext_models.py`
- `src/echo_masque/persistence/memory_vnext_repository.py`
- `tests/test_memory_vnext_internal_tools.py`

Other memory/intelligence/recall:
- `src/echo_masque/memory_intelligence.py`
- `src/echo_masque/persistence/memory_intelligence_models.py`
- `src/echo_masque/persistence/memory_layer_models.py`
- `src/echo_masque/character_recall.py`
- `src/echo_masque/recall_media_connector_runtime.py`
- `src/echo_masque/api/routes/conversation_memory_control.py`
- `tests/test_character_recall.py`
- `tests/test_character_recall_current_message.py`
- `tests/test_recall_freshness.py`

Replacement owner: Phase 4 unified Belief Store/current-turn revision. Raw evidence and authored meaning must be preserved.

## Graph / authority / media association surface

Current general graph persistence:
- `src/echo_masque/persistence/conversation_graph_models.py`
- `src/echo_masque/persistence/conversation_graph_repository.py`
- `tests/test_conversation_graph_repository.py`

Graph producers/projectors:
- `src/echo_masque/conversation_graph_shadow.py`
- `src/echo_masque/conversation_graph_topic_shadow.py`
- `src/echo_masque/conversation_media_graph.py`
- `tests/test_conversation_graph_shadow.py`
- `tests/test_conversation_graph_topic_shadow.py`

Replacement owner: Phase 3 unified Evidence Graph; Phase 10 deletes duplicate/shadow authority paths.

## Relationship / Impression / Learned State

Social Model:
- `src/echo_masque/character_relationships.py`
- `src/echo_masque/persistence/character_relationship_models.py`
- `src/echo_masque/api/relationship_schemas.py`
- `src/echo_masque/api/routes/character_relationships.py`
- `web/src/DeploymentRelationshipPanel.tsx`
- `web/src/relationshipApi.ts`
- `tests/test_character_relationships_v2.py`

Generic learned/behavior state:
- `src/echo_masque/character_learned_state.py`
- `src/echo_masque/persistence/character_learned_state_models.py`
- `src/echo_masque/persistence/character_learned_state_event_models.py`
- `tests/test_character_learned_state.py`
- `tests/test_character_learned_state_history.py`

Smart Participation outcome side effects:
- `src/echo_masque/smart_participation_outcome.py`

Replacement owner: Phase 5. Preserve dedicated directional relationship model and Impression persistence, remove generic relationship scalar/admission-only familiarity evidence, wire Impression into live context.

## Knowledge / RAG / Wiki / internal context

Knowledge/RAG:
- `src/echo_masque/knowledge_retrieval.py`
- `src/echo_masque/knowledge_route_gate.py`
- `src/echo_masque/persistence/knowledge_models.py`
- `src/echo_masque/persistence/knowledge_repository.py`
- `src/echo_masque/context_layer.py`
- `src/echo_masque/internal_context.py`
- `tests/test_context_rag.py`
- `tests/test_knowledge_route_gate.py`
- `tests/test_knowledge_route_assessment_v4.py`

Wiki:
- `src/echo_masque/knowledge_wiki.py`
- `src/echo_masque/persistence/wiki_page_models.py`
- `src/echo_masque/persistence/wiki_page_repository.py`
- `src/echo_masque/persistence/wiki_aware_knowledge_repository.py`
- `tests/test_knowledge_wiki.py`
- `tests/test_knowledge_wiki_runtime.py`

Replacement owner: Phase 6 Context Resolver + Phase 8 Wiki projection. Raw Knowledge documents remain authoritative.

## Media planner/runtime surface

Planning/attention/dependency:
- `src/echo_masque/planner_media.py`
- `src/echo_masque/media_attention.py`
- `src/echo_masque/media_dependency.py`
- `src/echo_masque/api/routes/planner_media.py`
- `tests/test_planner_media_contract.py`
- `tests/test_media_attention.py`
- `tests/test_media_dependency_v2.py`

Runtime/perception:
- `src/echo_masque/media_runtime.py`
- `src/echo_masque/media_connector_runtime.py`
- `src/echo_masque/live_media.py`
- `src/echo_masque/live_media_enhanced.py`
- `src/echo_masque/platform_media.py`
- `src/echo_masque/platform_keyframes.py`
- `src/echo_masque/conversation_media.py`
- `src/echo_masque/persistence/conversation_media_models.py`
- `src/echo_masque/persistence/conversation_media_repository.py`
- `tests/test_media_connector_runtime.py`
- `tests/test_media_awareness.py`
- `tests/test_passive_image_perception.py`
- `tests/test_platform_media.py`

Replacement owner: Phase 3 media/entity association + Phase 7 epistemic contract. Preserve objective perception and cache/provenance behavior.

## Discovery surface

Autonomous discovery is already implemented:
- `src/echo_masque/discovery_runtime.py`
- `src/echo_masque/deployment_discovery_intelligence.py`
- `src/echo_masque/deployment_discovery_service.py`
- `src/echo_masque/discovery_media_inspection.py`
- `src/echo_masque/discovery_social_association.py`
- `src/echo_masque/youtube_discovery.py`
- `src/echo_masque/youtube_no_key_discovery.py`
- `src/echo_masque/bilibili_discovery.py`
- `src/echo_masque/persistence/discovery_models.py`
- `src/echo_masque/persistence/discovery_repository.py`
- deployment Discovery API/UI under `src/echo_masque/api/routes/deployment_discovery.py` and `web/src/DeploymentDiscovery*`

Replacement owner: Phase 8 rewires Topic seed/association to recent Entity/Thread/Episode/Behavior signals without collapsing Discovery into current-turn Web Search.

## Participation / Turn Intelligence overlap

Core participation paths:
- `src/echo_masque/smart_participation.py`
- `src/echo_masque/semantic_participation.py`
- `src/echo_masque/participation_admission_policy.py`
- `src/echo_masque/participation_context_rerank.py`
- `src/echo_masque/participation_final_utility.py`
- `src/echo_masque/participation_tiebreak.py`
- `src/echo_masque/conversation_planner.py`
- `src/echo_masque/conversation_reply_planner.py`
- `src/echo_masque/turn_intelligence.py`
- `src/echo_masque/character_turn_intelligence.py`
- `src/echo_masque/orchestration/character_turn_graph.py`
- `src/echo_masque/orchestration/social_turn_graph.py`

Connector participation/routing:
- `connectors/discord/src/smartParticipation.ts`
- `connectors/discord/src/routing.ts`
- `connectors/discord/src/turnIngress.ts`
- related tests in connector src.

Replacement owner: Phase 7 Participation Planner after Phase 6 Context Resolver is available.

## Portal/observability surface

Conversation/Intelligence:
- `src/echo_masque/api/routes/conversation_intelligence.py`
- `src/echo_masque/api/routes/conversation_intelligence_observation.py`
- `src/echo_masque/api/routes/conversation_burst_observability.py`
- `src/echo_masque/api/routes/deployment_conversation_structure.py`
- `web/src/ConversationIntelligenceInspector.tsx`
- `web/src/ConversationIntelligenceInspectorLegacy.tsx`
- `web/src/ConversationStructurePanel.tsx`
- `web/src/conversationIntelligenceApi.ts`
- `web/src/conversationStructureApi.ts`

Social/participation/media traces also exist in dedicated panels/APIs.

Replacement owner: Phase 9. Legacy Topic audit/compatibility UI is removed rather than preserved.

## Destructive DB migration surface identified now

Known Topic-specific tables/models to remove after consumer cutover:
- `conversation_topics` (model in `conversation_topic_models.py`)
- Topic decision table(s) from `conversation_topic_decision_models.py`
- Topic-related indexes/columns discovered during implementation grep/schema review
- Topic graph/shadow derived rows where stored
- Topic Wiki pages (`page_key=topic:*`) and `source_topic_ids`-style provenance when confirmed in schema

Known Conversation Structure schema that must evolve rather than be discarded blindly:
- `semantic_threads`
- `conversation_segments`

New schema families expected before final hard delete:
- Message Relations
- Conversation Threads v3 fields
- Thread Memberships
- Thread Working State
- standalone PendingAction
- Entity/Evidence Graph revisions
- Belief Store
- SocialEvent/Impression revisions

## Final hard-cutover grep gate

Before Phase 10 exit, repository-wide search must classify every remaining occurrence of these terms:

- `ConversationTopic`
- `conversation_topic`
- `topic_id`
- `topic_local`
- `topic.search`
- `ACTIVE_TOPIC`
- `TOPIC_EVIDENCE`
- `TurnTopicDecision`
- `page_key=topic:` / `topic:` Wiki identity
- `source_topic_ids`
- `utility_topic_runtime`
- Topic lifecycle/consolidation references

Allowed remaining occurrences after cutover are only historical/deprecation/migration documentation if deliberately retained; no runtime authority, schema, UI compatibility, internal Tool, or test may depend on them.
