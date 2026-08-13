from __future__ import annotations

from dataclasses import dataclass

from echo_masque.api.connector_schemas import DiscordInboundMessage
from echo_masque.config import Settings
from echo_masque.context_layer import ContextOrchestrator
from echo_masque.conversation_topic import ConversationTopicMemoryService
from echo_masque.persistence import Database, KnowledgeRepository
from echo_masque.persistence.conversation_topic_repository import ConversationTopicRepository
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord
from echo_masque.prompt_budget import select_tool_ids_for_turn
from echo_masque.semantic_turn_runtime import SemanticTurnSignalStore
from echo_masque.tool_continuation import ToolContinuationService
from echo_masque.tool_runtime import ToolCatalogItem, ToolExecutionContext


class _SemanticEncoder:
    model_name = "test/continuation-e5"
    dimension = 7

    @staticmethod
    def _vector(text: str) -> list[float]:
        normalized = text.casefold()
        if "retry the previous" in normalized or "再试试" in normalized or "再来一次" in normalized:
            return [0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        if "continue the same previous" in normalized:
            return [0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0]
        if "cancel, stop, abandon" in normalized:
            return [0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0]
        if "clarify, correct" in normalized:
            return [0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0]
        if "start a new unrelated" in normalized or "换个话题" in normalized:
            return [0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0]
        if "image" in normalized or "cat" in normalized or "猫" in normalized:
            return [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        if "weather" in normalized:
            return [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]
        return [1.0 / 7.0] * 7

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)

    def embed_passage(self, text: str) -> list[float]:
        return self._vector(text)


@dataclass
class _Assignments:
    ids: tuple[str, ...] = ()

    def get_enabled_tools_for_runtime(self, deployment_id: str) -> tuple[str, ...]:
        del deployment_id
        return self.ids


class _ImageRegistry:
    def catalog(self) -> tuple[ToolCatalogItem, ...]:
        return (
            ToolCatalogItem(
                id="image.generate",
                display_name="Generate Image",
                description="Generate and deliver one image for the current Character.",
                category="image",
                operation="write",
                risk="medium",
                side_effect=True,
                provider_function_name="image_generate",
                available=True,
            ),
        )


def _settings() -> Settings:
    return Settings(
        environment="test",
        semantic_embedding_enabled=True,
        knowledge_semantic_retrieval_enabled=False,
    )


def _deployment() -> CharacterDeploymentRecord:
    return CharacterDeploymentRecord(
        id="deployment-ann",
        owner_id="owner-1",
        character_card_id="card-ann",
        connection_id="connection-1",
        platform="discord",
        workspace_id="guild-a",
        workspace_name="Guild",
        channel_id="general",
        channel_name="general",
        thread_id="",
        thread_name="",
        participation_mode="smart",
        memory_scope="channel_isolated",
        version_label="Current",
        sticker_count=0,
        status="active",
        last_error="",
    )


def _payload(text: str, *, message_id: str, author_id: str = "user-1") -> DiscordInboundMessage:
    return DiscordInboundMessage(
        connection_id="connection-1",
        deployment_id="deployment-ann",
        message_id=message_id,
        guild_id="guild-a",
        guild_name="Guild",
        channel_id="general",
        channel_name="general",
        category_id="",
        thread_id="",
        thread_name="",
        author_id=author_id,
        author_display_name=author_id,
        text=text,
        mentioned_bot=True,
        smart_candidate=True,
    )


def _orchestrator() -> tuple[ContextOrchestrator, _Assignments, ConversationTopicMemoryService]:
    database = Database("sqlite://")
    database.initialize()
    knowledge = KnowledgeRepository(database, semantic_enabled=False)
    encoder = _SemanticEncoder()
    topic_memory = ConversationTopicMemoryService(
        ConversationTopicRepository(database),
        settings=_settings(),
        encoder=encoder,
        semantic_enabled=True,
    )
    continuation = ToolContinuationService(
        topic_memory,
        settings=_settings(),
        encoder=encoder,
    )
    orchestrator = ContextOrchestrator(
        knowledge,
        settings=_settings(),
        topic_memory=topic_memory,
        tool_continuation_service=continuation,
    )
    assignments = _Assignments()
    orchestrator.deployment_tool_repository = assignments  # type: ignore[assignment]
    return orchestrator, assignments, topic_memory


def setup_function() -> None:
    SemanticTurnSignalStore.reset_for_test()


def teardown_function() -> None:
    SemanticTurnSignalStore.reset_for_test()


def test_unassigned_image_request_becomes_pending_then_retry_exposes_tool() -> None:
    orchestrator, assignments, topic_memory = _orchestrator()
    deployment = _deployment()

    first = orchestrator.build(
        payload=_payload("generate a cat image", message_id="m1"),
        deployment=deployment,
        character_name="Ann",
    )
    assert first.trace.blocked_side_effect_intents == ["image.generate"]
    assert first.trace.continuation_tool_ids == []

    topic = topic_memory.active_for_turn(
        owner_id="owner-1",
        payload=_payload("generate a cat image", message_id="m1"),
    )
    assert topic is not None
    assert [item.tool_id for item in topic.pending_actions] == ["image.generate"]
    assert topic.pending_actions[0].state == "blocked_unavailable"

    assignments.ids = ("image.generate",)
    second_payload = _payload("你再试试", message_id="m2")
    second = orchestrator.build(
        payload=second_payload,
        deployment=deployment,
        character_name="Ann",
    )
    assert second.trace.continuation_tool_ids == ["image.generate"]

    selected = select_tool_ids_for_turn(
        _ImageRegistry(),  # type: ignore[arg-type]
        ("image.generate",),
        ToolExecutionContext(
            owner_id="owner-1",
            deployment_id="deployment-ann",
            character_card_id="card-ann",
            platform="discord",
            connection_id="connection-1",
            guild_id="guild-a",
            channel_id="general",
            message_id="m2",
            trigger_text="你再试试",
            initiator_user_id="user-1",
        ),
        settings=_settings(),
        encoder=_SemanticEncoder(),
    )
    assert selected == ("image.generate",)


def test_pending_side_effect_cannot_be_inherited_by_another_user() -> None:
    orchestrator, assignments, _ = _orchestrator()
    deployment = _deployment()
    orchestrator.build(
        payload=_payload("generate a cat image", message_id="m1", author_id="user-1"),
        deployment=deployment,
        character_name="Ann",
    )

    assignments.ids = ("image.generate",)
    other_user = orchestrator.build(
        payload=_payload("你再试试", message_id="m2", author_id="user-2"),
        deployment=deployment,
        character_name="Ann",
    )

    assert other_user.trace.continuation_tool_ids == []


def test_unrelated_new_topic_does_not_expose_pending_side_effect() -> None:
    orchestrator, assignments, _ = _orchestrator()
    deployment = _deployment()
    orchestrator.build(
        payload=_payload("generate a cat image", message_id="m1"),
        deployment=deployment,
        character_name="Ann",
    )

    assignments.ids = ("image.generate",)
    weather = orchestrator.build(
        payload=_payload("what is tomorrow's weather", message_id="m2"),
        deployment=deployment,
        character_name="Ann",
    )

    assert weather.trace.continuation_tool_ids == []
