from __future__ import annotations

from datetime import UTC, datetime

from echo_masque.character_learned_state import (
    CharacterLearnedStateService,
    LearnedStateEvidence,
)
from echo_masque.persistence.database import Database


def test_learned_state_appends_scoped_before_after_history() -> None:
    database = Database("sqlite://")
    database.initialize()
    service = CharacterLearnedStateService(database)
    now = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)

    service.record_evidence(
        LearnedStateEvidence(
            owner_id="owner-1",
            character_card_id="card-ann",
            state_type="interest",
            subject_type="topic",
            subject_key="topic:topic-1",
            delta=0.4,
            confidence=0.8,
            source_type="runtime_admission",
            source_message_id="m1",
            source_burst_id="burst-1",
            reason_code="voluntary_topic_participation",
            connection_id="connection-1",
            guild_id="guild-1",
            channel_id="general",
            topic_id="topic-1",
        ),
        now=now,
    )
    service.record_evidence(
        LearnedStateEvidence(
            owner_id="owner-1",
            character_card_id="card-ann",
            state_type="interest",
            subject_type="topic",
            subject_key="topic:topic-1",
            delta=0.2,
            confidence=0.6,
            source_type="runtime_admission",
            source_message_id="m2",
            source_burst_id="burst-2",
            reason_code="voluntary_topic_participation",
            connection_id="connection-1",
            guild_id="guild-1",
            channel_id="general",
            topic_id="topic-1",
        ),
        now=now,
    )

    events = service.list_events_for_character(
        owner_id="owner-1",
        character_card_id="card-ann",
        connection_id="connection-1",
        guild_id="guild-1",
        state_types=("interest",),
    )

    assert len(events) == 2
    newest, oldest = events
    assert oldest.value_before == 0.0
    assert oldest.value_after > 0.0
    assert newest.value_before == oldest.value_after
    assert newest.value_after > newest.value_before
    assert newest.guild_id == "guild-1"
    assert newest.topic_id == "topic-1"
