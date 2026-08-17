from __future__ import annotations

from datetime import UTC, datetime, timedelta

from echo_masque.memory_layers import (
    CharacterMemorySummaryService,
    CoreMemoryRevisionRepository,
    SynthesizedMemoryFreshnessRepository,
)
from echo_masque.persistence.core_memory_repository import CoreMemoryRepository
from echo_masque.persistence.database import Database
from echo_masque.persistence.memory_vnext_repository import MemoryVNextRepository


def test_synthesized_freshness_is_metadata_not_destructive_authority() -> None:
    database = Database("sqlite://")
    database.initialize()
    memory = MemoryVNextRepository(database).create(
        owner_id="owner-1",
        character_card_id="character-ann",
        connection_id="connection-1",
        guild_id="guild-1",
        scope_type="character_server",
        memory_type="event",
        content="The user plans a short trip.",
        confidence=0.9,
        importance=0.8,
    )
    freshness = SynthesizedMemoryFreshnessRepository(database)
    now = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
    freshness.mark_confirmed(memory, now=now)

    assert freshness.refresh_staleness(now=now + timedelta(days=15)) == 1
    state = freshness.get(memory.id)
    assert state is not None
    assert state.freshness_status == "stale"
    assert MemoryVNextRepository(database).get(memory.id, "owner-1") is not None


def test_memory_summary_is_versioned_only_when_sources_change() -> None:
    database = Database("sqlite://")
    database.initialize()
    core = CoreMemoryRepository(database)
    core.upsert(
        owner_id="owner-1",
        character_card_id="character-ann",
        connection_id="connection-1",
        guild_id="guild-1",
        scope_type="character_server",
        memory_type="preference",
        content="The user prefers concise technical answers.",
        priority=0.95,
    )
    summaries = CharacterMemorySummaryService(database)

    first = summaries.refresh(
        owner_id="owner-1",
        character_card_id="character-ann",
        connection_id="connection-1",
        guild_id="guild-1",
    )
    same = summaries.refresh(
        owner_id="owner-1",
        character_card_id="character-ann",
        connection_id="connection-1",
        guild_id="guild-1",
    )
    assert first is not None and same is not None
    assert first.id == same.id
    assert first.version == 1

    core.upsert(
        owner_id="owner-1",
        character_card_id="character-ann",
        connection_id="connection-1",
        guild_id="guild-1",
        scope_type="character_server",
        memory_type="fact",
        content="Character Relay is the current project.",
        priority=0.9,
    )
    changed = summaries.refresh(
        owner_id="owner-1",
        character_card_id="character-ann",
        connection_id="connection-1",
        guild_id="guild-1",
    )
    assert changed is not None
    assert changed.version == 2
    assert changed.id != first.id
    assert "Character Relay" in changed.summary_text


def test_core_revision_can_restore_a_previous_snapshot() -> None:
    database = Database("sqlite://")
    database.initialize()
    core = CoreMemoryRepository(database)
    history = CoreMemoryRevisionRepository(database)
    memory = core.upsert(
        owner_id="owner-1",
        character_card_id="character-ann",
        content="Original durable preference.",
        priority=0.8,
    )
    revision = history.record(memory=memory, action="created")
    core.update(
        owner_id="owner-1",
        memory_id=memory.id,
        content="Updated durable preference.",
        priority=0.95,
    )

    restored = history.restore(owner_id="owner-1", revision_id=revision.id)
    assert restored.content == "Original durable preference."
    assert restored.priority == 0.8
