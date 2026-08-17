import asyncio
from typing import Any, cast

from echo_masque.internal_context import INTERNAL_CONTEXT_TOOL_IDS, InternalContextService
from echo_masque.media_tools import MediaToolRegistry
from echo_masque.persistence.conversation_episode_repository import ConversationEpisodeRepository
from echo_masque.persistence.conversation_topic_repository import ConversationTopicRepository
from echo_masque.persistence.database import Database
from echo_masque.persistence.memory_intelligence_models import ConversationMemoryRecord
from echo_masque.persistence.memory_vnext_repository import MemoryVNextRepository
from echo_masque.providers import ChatToolCall, ChatToolFunctionCall
from echo_masque.semantic_participation import SemanticEmbeddingUnavailable
from echo_masque.tool_runtime import ToolExecutionContext


class SparseOnlyEncoder:
    model_name = "offline"
    dimension = 2

    def embed_query(self, text: str) -> list[float]:
        del text
        raise SemanticEmbeddingUnavailable("offline")

    def embed_passage(self, text: str) -> list[float]:
        del text
        raise SemanticEmbeddingUnavailable("offline")


def service(database: Database) -> InternalContextService:
    return InternalContextService(
        memory_repository=MemoryVNextRepository(database),
        topic_repository=ConversationTopicRepository(database),
        episode_repository=ConversationEpisodeRepository(database),
        encoder=cast(Any, SparseOnlyEncoder()),
    )


def context(*, user_id: str = "user-a", guild_id: str = "guild-a") -> ToolExecutionContext:
    return ToolExecutionContext(
        owner_id="owner-1",
        deployment_id="deployment-1",
        character_card_id="character-1",
        platform="discord",
        connection_id="connection-1",
        guild_id=guild_id,
        channel_id="general",
        message_id="m1",
        initiator_user_id=user_id,
        topic_id="topic-1",
    )


def test_memory_vnext_is_server_and_subject_scoped() -> None:
    database = Database("sqlite://")
    database.initialize()
    repository = MemoryVNextRepository(database)
    repository.create(
        owner_id="owner-1",
        character_card_id="character-1",
        connection_id="connection-1",
        guild_id="guild-a",
        scope_type="character_user",
        subject_user_id="user-a",
        memory_type="preference",
        content="user-a likes Miyabi",
    )
    repository.create(
        owner_id="owner-1",
        character_card_id="character-1",
        connection_id="connection-1",
        guild_id="guild-a",
        scope_type="character_user",
        subject_user_id="user-b",
        memory_type="preference",
        content="user-b dislikes Miyabi",
    )
    repository.create(
        owner_id="owner-1",
        character_card_id="character-1",
        connection_id="connection-1",
        guild_id="guild-b",
        scope_type="character_server",
        memory_type="event",
        content="guild-b discussed Miyabi",
    )
    result = service(database).memory_search({"query": "Miyabi", "limit": 8}, context())
    assert "user-a likes Miyabi" in result
    assert "user-b dislikes Miyabi" not in result
    assert "guild-b discussed Miyabi" not in result


def test_internal_tools_are_runtime_owned_and_hidden_from_manual_catalog() -> None:
    database = Database("sqlite://")
    database.initialize()
    registry = MediaToolRegistry(internal_context_service=service(database))
    catalog_ids = {item.id for item in registry.catalog()}
    assert all(tool_id not in catalog_ids for tool_id in INTERNAL_CONTEXT_TOOL_IDS)
    assert registry.internal_tool_ids() == INTERNAL_CONTEXT_TOOL_IDS
    assert registry.tool_id_for_provider_name("memory_search") == "memory.search"

    call = ChatToolCall(
        id="call-memory",
        function=ChatToolFunctionCall(name="memory_search", arguments='{"query":"Miyabi"}'),
    )
    result = asyncio.run(
        registry.execute(
            call,
            enabled_tool_ids=INTERNAL_CONTEXT_TOOL_IDS,
            context=context(),
        )
    )
    assert result.trace.status == "completed"
    assert '"scope": "runtime_injected"' in result.content


def test_legacy_dirty_memory_is_deleted_only_once() -> None:
    database = Database("sqlite://")
    database.initialize()
    with database.session() as session:
        session.add(
            ConversationMemoryRecord(
                id="legacy-1",
                owner_id="owner-1",
                character_card_id="character-1",
                deployment_id="deployment-1",
                platform="discord",
                connection_id="connection-1",
                guild_id="guild-a",
                channel_id="general",
                thread_id="",
                subject_user_id="user-a",
                memory_type="preference",
                content="dirty legacy memory",
            )
        )
        session.commit()
    repository = MemoryVNextRepository(database)
    assert repository.reset_legacy_dirty_data_once() == 1
    assert repository.reset_legacy_dirty_data_once() == 0
    with database.session() as session:
        assert session.get(ConversationMemoryRecord, "legacy-1") is None
