from __future__ import annotations

from echo_masque.persistence.core_memory_repository import CoreMemoryRepository
from echo_masque.persistence.database import Database
from echo_masque.persistence.memory_vnext_repository import MemoryVNextRepository


def test_core_memory_visibility_is_explicitly_scoped() -> None:
    database = Database("sqlite://")
    database.initialize()
    repository = CoreMemoryRepository(database)

    global_memory = repository.upsert(
        owner_id="owner-1",
        character_card_id="character-ann",
        content="The user prefers concise technical explanations.",
        scope_type="character_global",
        memory_type="preference",
        priority=0.9,
    )
    server_memory = repository.upsert(
        owner_id="owner-1",
        character_card_id="character-ann",
        content="In this server, project discussions belong to Character Relay.",
        scope_type="character_server",
        connection_id="connection-1",
        guild_id="guild-1",
        memory_type="fact",
    )
    user_memory = repository.upsert(
        owner_id="owner-1",
        character_card_id="character-ann",
        content="User 7 prefers being called Seven.",
        scope_type="character_user",
        connection_id="connection-1",
        guild_id="guild-1",
        subject_user_id="user-7",
        memory_type="preference",
    )

    without_subject = repository.list_for_character(
        owner_id="owner-1",
        character_card_id="character-ann",
        connection_id="connection-1",
        guild_id="guild-1",
    )
    assert {item.id for item in without_subject} == {global_memory.id, server_memory.id}

    with_subject = repository.list_for_character(
        owner_id="owner-1",
        character_card_id="character-ann",
        connection_id="connection-1",
        guild_id="guild-1",
        subject_user_id="user-7",
    )
    assert {item.id for item in with_subject} == {
        global_memory.id,
        server_memory.id,
        user_memory.id,
    }

    other_server = repository.list_for_character(
        owner_id="owner-1",
        character_card_id="character-ann",
        connection_id="connection-1",
        guild_id="guild-2",
        subject_user_id="user-7",
    )
    assert {item.id for item in other_server} == {global_memory.id}


def test_core_memory_can_be_prioritized_archived_and_restored() -> None:
    database = Database("sqlite://")
    database.initialize()
    repository = CoreMemoryRepository(database)
    created = repository.upsert(
        owner_id="owner-1",
        character_card_id="character-ann",
        content="Remember this durable fact.",
        priority=0.6,
    )

    archived = repository.update(
        owner_id="owner-1",
        memory_id=created.id,
        priority=0.95,
        status="archived",
    )
    assert archived.priority == 0.95
    assert archived.status == "archived"
    assert repository.list_for_character(
        owner_id="owner-1",
        character_card_id="character-ann",
    ) == ()

    restored = repository.update(
        owner_id="owner-1",
        memory_id=created.id,
        status="active",
    )
    assert restored.status == "active"


def test_synthesized_memory_remains_separate_from_core_memory() -> None:
    database = Database("sqlite://")
    database.initialize()
    synthesized = MemoryVNextRepository(database).create(
        owner_id="owner-1",
        character_card_id="character-ann",
        connection_id="connection-1",
        guild_id="guild-1",
        scope_type="character_server",
        memory_type="fact",
        content="Background synthesis produced this fact.",
        confidence=0.9,
        importance=0.8,
    )

    promoted = CoreMemoryRepository(database).upsert(
        owner_id="owner-1",
        character_card_id=synthesized.character_card_id,
        connection_id=synthesized.connection_id,
        guild_id=synthesized.guild_id,
        scope_type="character_server",
        memory_type=synthesized.memory_type,
        content=synthesized.content,
        priority=0.9,
        source_memory_id=synthesized.id,
    )

    assert promoted.source_memory_id == synthesized.id
    assert MemoryVNextRepository(database).get(synthesized.id, "owner-1") is not None
    assert promoted.id != synthesized.id
