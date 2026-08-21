from __future__ import annotations

from datetime import UTC, datetime, timedelta

from echo_masque.persistence import Database
from echo_masque.persistence.belief_models import BeliefV3Record
from echo_masque.persistence.belief_repository import BeliefRepository


def _repository() -> tuple[Database, BeliefRepository]:
    database = Database("sqlite://")
    database.initialize()
    return database, BeliefRepository(database)


def _create_active_belief(
    repository: BeliefRepository,
    *,
    now: datetime,
    valid_to: datetime | None = None,
    stale_after: datetime | None = None,
):
    return repository.create(
        owner_id="owner-1",
        character_card_id="card-ann",
        connection_id="connection-1",
        guild_id="guild-1",
        subject_entity_id="",
        subject_ref="user-1",
        predicate="preference",
        value_text="Prefers a concise update.",
        scope="server",
        authority_class="conversation",
        authority_score=0.8,
        origin="conversation",
        confidence=0.9,
        importance=0.8,
        status="active",
        evidence_refs=("message-1",),
        valid_to=valid_to,
        stale_after=stale_after,
        now=now,
    )


def test_expired_belief_is_removed_from_v3_recall_and_marked_expired() -> None:
    database, beliefs = _repository()
    now = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)
    expired = _create_active_belief(
        beliefs,
        now=now - timedelta(days=1),
        valid_to=now - timedelta(seconds=1),
    )

    recalled = beliefs.recall(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        character_card_id="card-ann",
        now=now,
    )

    assert expired.id not in {item.id for item in recalled}
    with database.session() as session:
        stored = session.get(BeliefV3Record, expired.id)
        assert stored is not None
        assert stored.status == "expired"


def test_stale_belief_is_downgraded_to_provisional_for_v3_recall() -> None:
    _database, beliefs = _repository()
    now = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)
    stale = _create_active_belief(
        beliefs,
        now=now - timedelta(days=1),
        stale_after=now - timedelta(seconds=1),
    )

    recalled = beliefs.recall(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        character_card_id="card-ann",
        now=now,
    )

    assert [(item.id, item.status) for item in recalled] == [(stale.id, "provisional")]
