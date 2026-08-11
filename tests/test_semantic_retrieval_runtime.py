from __future__ import annotations

from echo_masque.api.connector_schemas import DiscordInboundMessage
from echo_masque.conversation_media import ConversationMediaReferenceService
from echo_masque.live_media import LiveMediaContext
from echo_masque.persistence import (
    ConversationMediaReferenceRepository,
    Database,
    KnowledgeRepository,
)
from echo_masque.reader_cleanup import clean_public_reader_text


class FakeSemanticEncoder:
    model_name = "fake-e5"
    dimension = 3

    def __init__(self) -> None:
        self.passage_calls = 0
        self.query_calls = 0

    @staticmethod
    def _vector(text: str) -> list[float]:
        lowered = text.casefold()
        if any(token in lowered for token in ("speak", "selection", "relevance", "join")):
            return [1.0, 0.0, 0.0]
        if any(token in lowered for token in ("像他", "glasses", "眼镜", "男人", "man")):
            return [0.0, 1.0, 0.0]
        return [0.0, 0.0, 1.0]

    def embed_passage(self, text: str) -> list[float]:
        self.passage_calls += 1
        return self._vector(text)

    def embed_query(self, text: str) -> list[float]:
        self.query_calls += 1
        return self._vector(text)


def inbound(message_id: str, text: str) -> DiscordInboundMessage:
    return DiscordInboundMessage(
        connection_id="connection-1",
        deployment_id="deployment-1",
        message_id=message_id,
        guild_id="guild-1",
        guild_name="Guild",
        channel_id="channel-1",
        channel_name="general",
        author_id="user-1",
        author_display_name="Juen",
        text=text,
    )


def test_knowledge_hybrid_retrieval_recovers_semantic_match_and_reuses_vector() -> None:
    database = Database("sqlite://")
    database.initialize()
    encoder = FakeSemanticEncoder()
    repository = KnowledgeRepository(
        database,
        semantic_encoder=encoder,
        semantic_enabled=True,
    )
    base = repository.create_base(
        owner_id="owner-1",
        name="Runtime docs",
        description="",
        scope_type="global",
    )
    repository.create_document(
        owner_id="owner-1",
        knowledge_base_id=base.id,
        title="Turn routing",
        content="Eligible personas are ranked with relevance and initiative before turn selection.",
    )
    repository.create_document(
        owner_id="owner-1",
        knowledge_base_id=base.id,
        title="Storage",
        content="SQLite stores bounded runtime records and cached analysis metadata.",
    )

    first = repository.retrieve_for_turn(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="channel-1",
        thread_id="",
        character_card_id="card-1",
        query="Who should speak next?",
    )
    first_passage_calls = encoder.passage_calls
    second = repository.retrieve_for_turn(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="channel-1",
        thread_id="",
        character_card_id="card-1",
        query="Who should speak next?",
    )

    assert first.candidates
    assert first.candidates[0].resource.document_title == "Turn routing"
    assert first.candidates[0].signals["dense"] == 1.0
    assert second.candidates[0].resource.chunk_id == first.candidates[0].resource.chunk_id
    assert encoder.passage_calls == first_passage_calls


def test_media_semantic_recall_handles_implicit_reference_without_keyword() -> None:
    database = Database("sqlite://")
    database.initialize()
    encoder = FakeSemanticEncoder()
    repository = ConversationMediaReferenceRepository(database)
    service = ConversationMediaReferenceService(
        repository,
        semantic_encoder=encoder,
        semantic_enabled=True,
    )
    original = inbound("image-message", "看这个")
    context = LiveMediaContext(
        source_key="sha256:image-1",
        kind="image",
        label="photo.png",
        summary="A man wearing red glasses is standing beside a desk.",
        notable_details=("He is smiling.",),
    )
    service.remember_perceived(
        owner_id="owner-1",
        deployment_id="deployment-1",
        character_card_id="card-1",
        payload=original,
        contexts=(context,),
    )

    memories = service.resolve_for_turn(
        deployment_id="deployment-1",
        character_card_id="card-1",
        payload=inbound("follow-up", "你不觉得很像他吗?"),
    )

    assert len(memories) == 1
    assert memories[0].message_id == "image-message"
    assert "red glasses" in memories[0].context.summary


def test_public_reader_cleanup_removes_guest_popup_noise_but_keeps_article() -> None:
    result = clean_public_reader_text(
        "登录后继续\n扫码登录\n打开 App 阅读完整内容\n"
        "这是文章标题\n这里是第一段真正的正文, 解释产品设计和实现细节。\n"
        "这里是第二段正文, 仍然应该被保留。"
    )

    assert result.state == "cleaned"
    assert "登录后继续" not in result.text
    assert "扫码登录" not in result.text
    assert "第一段真正的正文" in result.text


def test_public_reader_cleanup_detects_guest_wall_when_no_article_remains() -> None:
    result = clean_public_reader_text(
        "登录后继续\n扫码登录\n打开 App 查看\n下载 App\nSign in to continue\nOpen in app"
    )

    assert result.state == "guest_blocked"
