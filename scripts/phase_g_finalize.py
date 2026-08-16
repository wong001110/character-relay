from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(
            f"{path}: expected exactly one match, found {count}: {old[:120]!r}"
        )
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


app = "src/echo_masque/api/app.py"
replace_once(
    app,
    "from echo_masque.context_layer import ContextOrchestrator\n",
    "from echo_masque.context_layer import ContextOrchestrator\n"
    "from echo_masque.conversation_consolidation import ConversationConsolidationService\n",
)
replace_once(
    app,
    "from echo_masque.persistence.memory_vnext_repository import MemoryVNextRepository\n",
    "from echo_masque.persistence.memory_vnext_repository import MemoryVNextRepository\n"
    "from echo_masque.persistence.server_knowledge_repository import (\n"
    "    ConsolidationCheckpointRepository,\n"
    "    ConversationAuthorityGraphRepository,\n"
    "    ServerWikiRepository,\n"
    ")\n",
)
replace_once(
    app,
    "    knowledge_repository = KnowledgeRepository(database)\n"
    "    context_orchestrator = ContextOrchestrator(knowledge_repository)\n",
    "    knowledge_repository = KnowledgeRepository(database)\n"
    "    server_wiki_repository = ServerWikiRepository(database)\n"
    "    conversation_authority_graph_repository = ConversationAuthorityGraphRepository(\n"
    "        database\n"
    "    )\n"
    "    consolidation_checkpoint_repository = ConsolidationCheckpointRepository(database)\n"
    "    context_orchestrator = ContextOrchestrator(knowledge_repository)\n",
)
replace_once(
    app,
    "        episode_repository=ConversationEpisodeRepository(database),\n"
    "        settings=resolved,\n"
    "    )\n"
    "    tool_registry = MediaToolRegistry(\n",
    "        episode_repository=ConversationEpisodeRepository(database),\n"
    "        settings=resolved,\n"
    "        wiki_lookup_backend=server_wiki_repository.lookup,\n"
    "    )\n"
    "    tool_registry = MediaToolRegistry(\n",
)
replace_once(
    app,
    "    planner_utility_gateway = UtilityGatewayRouter(\n"
    "        runtime_service,\n"
    "        caller=ExistingProviderUtilityCaller(),\n"
    "    )\n"
    "    planner_media_service = PlannerMediaDescriptorService(\n",
    "    planner_utility_gateway = UtilityGatewayRouter(\n"
    "        runtime_service,\n"
    "        caller=ExistingProviderUtilityCaller(),\n"
    "    )\n"
    "    conversation_consolidation_service = ConversationConsolidationService(\n"
    "        topic_repository=ConversationTopicRepository(database),\n"
    "        episode_repository=ConversationEpisodeRepository(database),\n"
    "        memory_repository=memory_vnext_repository,\n"
    "        wiki_repository=server_wiki_repository,\n"
    "        graph_repository=conversation_authority_graph_repository,\n"
    "        checkpoint_repository=consolidation_checkpoint_repository,\n"
    "        gateway=planner_utility_gateway,\n"
    "    )\n"
    "    planner_media_service = PlannerMediaDescriptorService(\n",
)
replace_once(
    app,
    "        condition_watch_repository,\n"
    "        memory_vnext_repository=memory_vnext_repository,\n"
    "    )\n",
    "        condition_watch_repository,\n"
    "        memory_vnext_repository=memory_vnext_repository,\n"
    "        server_wiki_repository=server_wiki_repository,\n"
    "        conversation_authority_graph_repository=conversation_authority_graph_repository,\n"
    "        consolidation_checkpoint_repository=consolidation_checkpoint_repository,\n"
    "    )\n",
)
replace_once(
    app,
    "        await browser_runtime.start()\n"
    "        await scheduled_reminder_delivery.start()\n"
    "        await condition_watch_service.start()\n"
    "        try:\n"
    "            yield\n"
    "        finally:\n"
    "            await condition_watch_service.stop()\n"
    "            await scheduled_reminder_delivery.stop()\n"
    "            await browser_runtime.stop()\n",
    "        await browser_runtime.start()\n"
    "        await scheduled_reminder_delivery.start()\n"
    "        await condition_watch_service.start()\n"
    "        await conversation_consolidation_service.start()\n"
    "        try:\n"
    "            yield\n"
    "        finally:\n"
    "            await conversation_consolidation_service.stop()\n"
    "            await condition_watch_service.stop()\n"
    "            await scheduled_reminder_delivery.stop()\n"
    "            await browser_runtime.stop()\n",
)
replace_once(
    app,
    "    app.state.memory_vnext_repository = memory_vnext_repository\n"
    "    app.state.internal_context_service = internal_context_service\n",
    "    app.state.memory_vnext_repository = memory_vnext_repository\n"
    "    app.state.server_wiki_repository = server_wiki_repository\n"
    "    app.state.conversation_authority_graph_repository = (\n"
    "        conversation_authority_graph_repository\n"
    "    )\n"
    "    app.state.consolidation_checkpoint_repository = consolidation_checkpoint_repository\n"
    "    app.state.conversation_consolidation_service = conversation_consolidation_service\n"
    "    app.state.internal_context_service = internal_context_service\n",
)

lifecycle = "src/echo_masque/evaluation_lifecycle.py"
replace_once(
    lifecycle,
    "from echo_masque.persistence.wiki_page_repository import WikiPageRepository\n",
    "from echo_masque.persistence.server_knowledge_repository import (\n"
    "    ConsolidationCheckpointRepository,\n"
    "    ConversationAuthorityGraphRepository,\n"
    "    ServerWikiRepository,\n"
    ")\n"
    "from echo_masque.persistence.wiki_page_repository import WikiPageRepository\n",
)
replace_once(
    lifecycle,
    "        memory_vnext_repository: MemoryVNextRepository | None = None,\n"
    "    ) -> None:\n",
    "        memory_vnext_repository: MemoryVNextRepository | None = None,\n"
    "        server_wiki_repository: ServerWikiRepository | None = None,\n"
    "        conversation_authority_graph_repository: (\n"
    "            ConversationAuthorityGraphRepository | None\n"
    "        ) = None,\n"
    "        consolidation_checkpoint_repository: (\n"
    "            ConsolidationCheckpointRepository | None\n"
    "        ) = None,\n"
    "    ) -> None:\n",
)
replace_once(
    lifecycle,
    "        self.memory_vnext_repository = memory_vnext_repository or MemoryVNextRepository(database)\n",
    "        self.memory_vnext_repository = memory_vnext_repository or MemoryVNextRepository(database)\n"
    "        self.server_wiki_repository = server_wiki_repository or ServerWikiRepository(database)\n"
    "        self.conversation_authority_graph_repository = (\n"
    "            conversation_authority_graph_repository\n"
    "            or ConversationAuthorityGraphRepository(database)\n"
    "        )\n"
    "        self.consolidation_checkpoint_repository = (\n"
    "            consolidation_checkpoint_repository\n"
    "            or ConsolidationCheckpointRepository(database)\n"
    "        )\n",
)
replace_once(
    lifecycle,
    "        memory_vnext_count = self.memory_vnext_repository.delete_owner(user_id)\n"
    "        deployment_counts = self.deployment_repository.delete_owner(user_id)\n",
    "        memory_vnext_count = self.memory_vnext_repository.delete_owner(user_id)\n"
    "        server_wiki_count = self.server_wiki_repository.delete_owner(user_id)\n"
    "        authority_graph_count = self.conversation_authority_graph_repository.delete_owner(\n"
    "            user_id\n"
    "        )\n"
    "        consolidation_checkpoint_count = (\n"
    "            self.consolidation_checkpoint_repository.delete_owner(user_id)\n"
    "        )\n"
    "        deployment_counts = self.deployment_repository.delete_owner(user_id)\n",
)
replace_once(
    lifecycle,
    "            \"conversation_memory_vnext\": memory_vnext_count,\n"
    "            **deployment_counts,\n",
    "            \"conversation_memory_vnext\": memory_vnext_count,\n"
    "            \"server_wiki_pages\": server_wiki_count,\n"
    "            \"conversation_authority_edges\": authority_graph_count,\n"
    "            \"conversation_consolidation_checkpoints\": consolidation_checkpoint_count,\n"
    "            **deployment_counts,\n",
)
replace_once(
    lifecycle,
    "        memory_vnext_count = self.memory_vnext_repository.claim_owner(\n"
    "            \"local-user\",\n"
    "            actor_user_id,\n"
    "        )\n"
    "        combined = {\n",
    "        memory_vnext_count = self.memory_vnext_repository.claim_owner(\n"
    "            \"local-user\",\n"
    "            actor_user_id,\n"
    "        )\n"
    "        server_wiki_count = self.server_wiki_repository.claim_owner(\n"
    "            \"local-user\",\n"
    "            actor_user_id,\n"
    "        )\n"
    "        authority_graph_count = self.conversation_authority_graph_repository.claim_owner(\n"
    "            \"local-user\",\n"
    "            actor_user_id,\n"
    "        )\n"
    "        consolidation_checkpoint_count = (\n"
    "            self.consolidation_checkpoint_repository.claim_owner(\n"
    "                \"local-user\",\n"
    "                actor_user_id,\n"
    "            )\n"
    "        )\n"
    "        combined = {\n",
)
replace_once(
    lifecycle,
    "            \"conversation_memory_vnext\": memory_vnext_count,\n"
    "            **identity_counts,\n",
    "            \"conversation_memory_vnext\": memory_vnext_count,\n"
    "            \"server_wiki_pages\": server_wiki_count,\n"
    "            \"conversation_authority_edges\": authority_graph_count,\n"
    "            \"conversation_consolidation_checkpoints\": consolidation_checkpoint_count,\n"
    "            **identity_counts,\n",
)

consolidation = "src/echo_masque/conversation_consolidation.py"
replace_once(consolidation, "from sqlalchemy import or_, select\n", "from sqlalchemy import select\n")
replace_once(
    consolidation,
    "                if result.status == \"partial\":\n"
    "                    # Retry only through a later maintenance sweep; do not hot-loop an exhausted\n"
    "                    # free Utility provider.\n"
    "                    self.checkpoint_repository.save(\n"
    "                        owner_id=owner_id,\n"
    "                        topic_id=topic_id,\n"
    "                        connection_id=(\n"
    "                            self.topic_repository.get(topic_id, owner_id).connection_id\n"
    "                            if self.topic_repository.get(topic_id, owner_id) is not None\n"
    "                            else \"\"\n"
    "                        ),\n"
    "                        guild_id=(\n"
    "                            self.topic_repository.get(topic_id, owner_id).guild_id\n"
    "                            if self.topic_repository.get(topic_id, owner_id) is not None\n"
    "                            else \"\"\n"
    "                        ),\n"
    "                        source_hash=(\n"
    "                            self.checkpoint_repository.get(owner_id=owner_id, topic_id=topic_id)\n"
    "                            .source_hash\n"
    "                            if self.checkpoint_repository.get(\n"
    "                                owner_id=owner_id, topic_id=topic_id\n"
    "                            )\n"
    "                            is not None\n"
    "                            else \"\"\n"
    "                        ),\n"
    "                        status=\"partial\",\n"
    "                        reason=\"utility_retry_pending\",\n"
    "                        episode_count=result.episode_count,\n"
    "                        memory_count=result.memory_count,\n"
    "                        wiki_page_id=result.wiki_page_id,\n"
    "                        graph_edge_count=result.graph_edge_count,\n"
    "                        utility_status=result.utility_status,\n"
    "                    )\n",
    "",
)
replace_once(
    consolidation,
    "            records = list(\n"
    "                session.scalars(\n"
    "                    select(ConversationTopicRecord)\n"
    "                    .where(\n"
    "                        or_(\n"
    "                            ConversationTopicRecord.status.in_([\"cooling\", \"closed\", \"archived\"]),\n"
    "                            ConversationTopicRecord.message_count >= _SIZE_CHECKPOINT_MESSAGES,\n"
    "                        )\n"
    "                    )\n"
    "                    .order_by(ConversationTopicRecord.updated_at.asc())\n"
    "                    .limit(self.batch_size * 4)\n"
    "                )\n"
    "            )\n",
    "            records = list(\n"
    "                session.scalars(\n"
    "                    select(ConversationTopicRecord)\n"
    "                    .order_by(ConversationTopicRecord.updated_at.asc())\n"
    "                    .limit(self.batch_size * 6)\n"
    "                )\n"
    "            )\n",
)
replace_once(
    consolidation,
    '                        "Build one compact Discord-server-scoped derived Wiki page from the supplied "\n',
    '                        "Build a compact server-scoped Wiki page from the supplied "\n',
)
replace_once(
    consolidation,
    '        participant_alias = {f"u{index}": value for index, value in enumerate(participant_ids, start=1)}\n',
    '        participant_alias = {\n'
    '            f"u{index}": value\n'
    '            for index, value in enumerate(participant_ids, start=1)\n'
    '        }\n',
)
replace_once(
    consolidation,
    '                        "Extract only durable Character memory from supplied shared Episode evidence. "\n'
    '                        "Choose only supplied refs/enums. Runtime owns scope and writes. Return strict "\n',
    '                        "Extract durable Character memory from shared Episode evidence. "\n'
    '                        "Choose supplied refs/enums only. Runtime owns scope and writes. "\n',
)

test_file = Path("tests/test_server_knowledge_consolidation.py")
test_text = test_file.read_text(encoding="utf-8")
test_text = test_text.replace("import pytest\n", "import asyncio\n")
test_text = test_text.replace(
    "@pytest.mark.asyncio\nasync def test_topic_cooling_signal_builds_wiki_and_typed_graph() -> None:\n",
    "def test_topic_cooling_signal_builds_wiki_and_typed_graph() -> None:\n",
)
test_text = test_text.replace(
    "        processed = await service.run_once()\n",
    "        processed = asyncio.run(service.run_once())\n",
)
test_file.write_text(test_text, encoding="utf-8")
