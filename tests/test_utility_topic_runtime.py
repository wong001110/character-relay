from __future__ import annotations

from datetime import UTC, datetime, timedelta

from echo_masque.api.connector_schemas import DiscordInboundMessage
from echo_masque.persistence.conversation_topic_repository import ConversationTopicRepository
from echo_masque.persistence.database import Database
from echo_masque.utility_gateway_contracts import TopicUtilityDecision
from echo_masque.utility_topic_runtime import UtilityTopicMemoryService


class _TopicEncoder:
    model_name = "test/topic-e5"
    dimension = 4

    @staticmethod
    def _vector(text: str) -> list[float]:
        normalized = text.casefold()
        if (
            "retry the previous" in normalized
            or "continue the same previous" in normalized
            or "cancel, stop, abandon" in normalized
            or "clarify, correct" in normalized
        ):
            return [0.0, 1.0, 0.0, 0.0]
        if "start a new unrelated" in normalized:
            return [0.0, 0.0, 0.0, 1.0]
        if "rag" in normalized or "llm wiki" in normalized:
            return [1.0, 0.0, 0.0, 0.0]
        if "绝区零" in normalized or "反派" in normalized:
            return [0.0, 0.0, 1.0, 0.0]
        return [0.25, 0.25, 0.25, 0.25]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)

    def embed_passage(self, text: str) -> list[float]:
        return self._vector(text)


class _AlwaysContinueGateway:
    def __init__(self) -> None:
        self.calls = 0

    def topic_decision(self, *, prompt: str) -> tuple[TopicUtilityDecision, object]:
        self.calls += 1
        return TopicUtilityDecision(decision="continue", confidence=0.99), object()


def _payload(text: str, *, message_id: str) -> DiscordInboundMessage:
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
        author_id="user-1",
        author_display_name="Juen",
        text=text,
        mentioned_bot=True,
        smart_candidate=True,
    )


def test_utility_judge_cannot_revive_stale_unmatched_topic() -> None:
    database = Database("sqlite://")
    database.initialize()
    repository = ConversationTopicRepository(database)
    gateway = _AlwaysContinueGateway()
    service = UtilityTopicMemoryService(
        repository,
        encoder=_TopicEncoder(),
        semantic_enabled=True,
        gateway=gateway,  # type: ignore[arg-type]
    )
    started = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)

    first = service.observe_turn(
        owner_id="owner-1",
        payload=_payload("RAG and LLM Wiki architecture", message_id="m1"),
        now=started,
    )
    zzz = service.observe_turn(
        owner_id="owner-1",
        payload=_payload("绝区零这段剧情谁是反派?", message_id="m2"),
        now=started + timedelta(days=2),
    )

    assert first is not None
    assert zzz is not None
    assert zzz.id != first.id
    assert gateway.calls == 0
