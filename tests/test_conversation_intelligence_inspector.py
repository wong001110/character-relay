from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast

from echo_masque.api.routes.conversation_intelligence import (
    inspect_character_intelligence,
    inspect_topic_timeline,
)
from echo_masque.character_learned_state import (
    CharacterLearnedStateService,
    LearnedStateEvidence,
)
from echo_masque.persistence.conversation_topic_repository import ConversationTopicRepository
from echo_masque.persistence.database import Database
from echo_masque.persistence.repository import Repository


def _request(database: Database, repository: Repository) -> Any:
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(database=database, repository=repository))
    )


def _user(owner_id: str) -> Any:
    return SimpleNamespace(id=owner_id)


def _card(repository: Repository, owner_id: str) -> str:
    target = repository.create_target(name="test", target_kind="custom", config={})
    card = repository.create_character_card(
        owner_id=owner_id,
        target_id=target.id,
        display_name="Ann",
        subtitle="",
        subject_type="companion",
        persona_summary="A careful companion.",
        traits=["curious"],
        tags=["cat"],
        expected_tone=None,
        forbidden_behaviors=[],
        memory_summary=None,
        preferred_suites=[],
        portrait_variant="lavender",
    )
    return card.id


def test_character_inspector_exposes_stored_decayed_and_provenance() -> None:
    database = Database("sqlite:///:memory:")
    database.initialize()
    repository = Repository(database)
    owner_id = "owner-a"
    card_id = _card(repository, owner_id)
    evidence_time = datetime.now(UTC) - timedelta(days=30)
    CharacterLearnedStateService(database).record_evidence(
        LearnedStateEvidence(
            owner_id=owner_id,
            character_card_id=card_id,
            state_type="interest",
            subject_type="topic",
            subject_key="photography",
            delta=0.8,
            confidence=0.8,
            source_type="runtime_admission",
            source_message_id="message-1",
            source_burst_id="burst-1",
            reason_code="voluntary_topic_participation",
        ),
        now=evidence_time,
    )

    result = inspect_character_intelligence(
        card_id,
        cast(Any, _request(database, repository)),
        cast(Any, _user(owner_id)),
    )

    assert result.character_display_name == "Ann"
    assert len(result.items) == 1
    item = result.items[0]
    assert item.state_type == "interest"
    assert item.subject_key == "photography"
    assert item.stored_value > item.current_value > 0
    assert item.stored_confidence > item.current_confidence > 0
    assert item.provenance[0].source_burst_id == "burst-1"
    assert item.provenance[0].reason_code == "voluntary_topic_participation"


def test_topic_inspector_is_owner_and_scope_isolated() -> None:
    database = Database("sqlite:///:memory:")
    database.initialize()
    repository = Repository(database)
    topics = ConversationTopicRepository(database)
    common = {
        "platform": "discord",
        "connection_id": "connection-1",
        "guild_id": "guild-1",
        "channel_id": "channel-1",
        "thread_id": "",
        "summary": "summary",
        "keywords_json": '["alpha"]',
        "open_loops_json": '["follow up"]',
        "pending_actions_json": "[]",
        "participants_json": '["actor-1"]',
        "last_message_id": "message-1",
    }
    own = topics.create(owner_id="owner-a", topic_label="Own Topic", **common)
    topics.create(owner_id="owner-b", topic_label="Other Owner", **common)
    topics.create(
        owner_id="owner-a",
        topic_label="Other Channel",
        **{**common, "channel_id": "channel-2"},
    )

    result = inspect_topic_timeline(
        cast(Any, _request(database, repository)),
        cast(Any, _user("owner-a")),
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="channel-1",
        thread_id="",
        limit=20,
    )

    assert [item.topic_label for item in result.items] == ["Own Topic"]
    assert result.current_topic_id == own.id
    assert result.items[0].keywords == ("alpha",)
    assert result.items[0].open_loops == ("follow up",)
