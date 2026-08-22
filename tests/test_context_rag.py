from __future__ import annotations

from echo_masque.persistence import Database, KnowledgeRepository
from echo_masque.persistence.knowledge_repository import chunk_document


def repository() -> KnowledgeRepository:
    database = Database("sqlite://")
    database.initialize()
    return KnowledgeRepository(database)


def test_chunk_document_is_bounded_and_deterministic() -> None:
    content = ("alpha " * 250) + "\n\n" + ("beta " * 250)
    first = chunk_document(content, max_chars=400, overlap_chars=60)
    second = chunk_document(content, max_chars=400, overlap_chars=60)

    assert first == second
    assert len(first) > 2
    assert all(0 < len(item) <= 400 for item in first)


def test_server_scope_never_leaks_to_another_guild() -> None:
    repo = repository()
    base = repo.create_base(
        owner_id="owner-1",
        name="Guild A knowledge",
        description="",
        scope_type="server",
        connection_id="connection-1",
        guild_id="guild-a",
    )
    repo.create_document(
        owner_id="owner-1",
        knowledge_base_id=base.id,
        title="Launch notes",
        content="The launch password is orchid-72. Keep this note inside Guild A.",
    )

    allowed = repo.retrieve_for_turn(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-a",
        channel_id="channel-1",
        thread_id="",
        character_card_id="card-ann",
        query="launch password",
    )
    blocked = repo.retrieve_for_turn(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-b",
        channel_id="channel-1",
        thread_id="",
        character_card_id="card-ann",
        query="launch password",
    )

    assert allowed.eligible_base_count == 1
    assert allowed.candidates
    assert "orchid-72" in allowed.candidates[0].resource.content
    assert blocked.eligible_base_count == 0
    assert blocked.candidates == ()


def test_channel_scope_and_chinese_sparse_retrieval() -> None:
    repo = repository()
    base = repo.create_base(
        owner_id="owner-1",
        name="中文频道资料",
        description="",
        scope_type="channel",
        connection_id="connection-1",
        guild_id="guild-a",
        channel_id="channel-1",
    )
    repo.create_document(
        owner_id="owner-1",
        knowledge_base_id=base.id,
        title="角色设定",
        content="宁最喜欢的饮料是无糖乌龙茶。她不喜欢过甜的奶茶。",
    )

    result = repo.retrieve_for_turn(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-a",
        channel_id="channel-1",
        thread_id="",
        character_card_id="card-ann",
        query="宁喜欢喝什么饮料?",
    )

    assert result.eligible_base_count == 1
    assert result.candidates
    assert "无糖乌龙茶" in result.candidates[0].resource.content
