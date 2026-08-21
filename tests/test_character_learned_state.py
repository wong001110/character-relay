from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from echo_masque.character_learned_state import (
    CharacterLearnedStateService,
    LearnedStateEvidence,
)
from echo_masque.character_relationships import CharacterRelationshipService
from echo_masque.persistence import Database
from echo_masque.persistence.character_learned_state_models import CharacterLearnedStateRecord
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord


def service(tmp_path: Path) -> tuple[Database, CharacterLearnedStateService]:
    database = Database(f"sqlite:///{tmp_path / 'learned-state.db'}")
    database.initialize()
    return database, CharacterLearnedStateService(database)


def evidence(
    *,
    delta: float,
    state_type: str = "interest",
    subject_key: str = "photography",
    owner_id: str = "owner-1",
    character_card_id: str = "card-ann",
    source_message_id: str = "message-1",
) -> LearnedStateEvidence:
    return LearnedStateEvidence(
        owner_id=owner_id,
        character_card_id=character_card_id,
        state_type=state_type,  # type: ignore[arg-type]
        subject_type="concept",
        subject_key=subject_key,
        delta=delta,
        confidence=0.8,
        source_type="explicit_feedback",
        source_message_id=source_message_id,
        source_burst_id="burst-1",
        reason_code="reviewed_evidence",
    )


def test_positive_and_negative_evidence_are_bounded_and_counted(tmp_path: Path) -> None:
    _database, learned = service(tmp_path)
    now = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)

    first = learned.record_evidence(evidence(delta=1.0), now=now)
    second = learned.record_evidence(
        evidence(delta=-1.0, source_message_id="message-2"),
        now=now + timedelta(seconds=1),
    )

    assert 0.0 < first.value <= 1.0
    assert second.positive_evidence_count == 1
    assert second.negative_evidence_count == 1
    assert second.evidence_count == 2
    assert second.contradiction_count == 1
    assert -1.0 <= second.value <= 1.0
    assert 0.0 <= second.confidence <= 1.0


def test_half_life_decay_is_applied_on_read_without_mutating_history(tmp_path: Path) -> None:
    database, learned = service(tmp_path)
    now = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)
    created = learned.record_evidence(
        evidence(delta=1.0, state_type="salience"),
        now=now,
    )
    half_life = learned.half_life_seconds("salience")

    decayed = learned.get(
        owner_id="owner-1",
        character_card_id="card-ann",
        state_type="salience",
        subject_type="concept",
        subject_key="photography",
        now=now + timedelta(seconds=half_life),
    )

    assert decayed is not None
    assert decayed.value == round(created.value * 0.5, 6)
    assert decayed.confidence == round(created.confidence * 0.5, 6)
    with database.session() as session:
        stored = session.get(CharacterLearnedStateRecord, created.id)
        assert stored is not None
        assert stored.value == created.value
        assert stored.confidence == created.confidence


def test_state_isolated_by_owner_and_character(tmp_path: Path) -> None:
    _database, learned = service(tmp_path)
    now = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)
    learned.record_evidence(evidence(delta=1.0), now=now)
    learned.record_evidence(
        evidence(delta=-1.0, owner_id="owner-2"),
        now=now,
    )
    learned.record_evidence(
        evidence(delta=-1.0, character_card_id="card-ning"),
        now=now,
    )

    ann = learned.get(
        owner_id="owner-1",
        character_card_id="card-ann",
        state_type="interest",
        subject_type="concept",
        subject_key="photography",
        now=now,
    )
    owner_two = learned.get(
        owner_id="owner-2",
        character_card_id="card-ann",
        state_type="interest",
        subject_type="concept",
        subject_key="photography",
        now=now,
    )
    ning = learned.get(
        owner_id="owner-1",
        character_card_id="card-ning",
        state_type="interest",
        subject_type="concept",
        subject_key="photography",
        now=now,
    )

    assert ann is not None and ann.value > 0
    assert owner_two is not None and owner_two.value < 0
    assert ning is not None and ning.value < 0


def test_provenance_is_bounded_and_never_requires_raw_message_text(tmp_path: Path) -> None:
    database, learned = service(tmp_path)
    now = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)
    latest = None
    for index in range(12):
        latest = learned.record_evidence(
            evidence(
                delta=1.0,
                source_message_id=f"message-{index}",
            ),
            now=now + timedelta(seconds=index),
        )
    assert latest is not None

    with database.session() as session:
        stored = session.get(CharacterLearnedStateRecord, latest.id)
        assert stored is not None
        provenance = json.loads(stored.provenance_json)

    assert len(provenance) == 8
    assert provenance[0]["source_message_id"] == "message-4"
    assert provenance[-1]["source_message_id"] == "message-11"
    assert all("text" not in item and "message" not in item for item in provenance)


def test_short_term_fatigue_decays_faster_than_lived_relationship_state(tmp_path: Path) -> None:
    database, learned = service(tmp_path)
    with database.session() as session:
        session.add(
            CharacterDeploymentRecord(
                id="deployment-ann",
                owner_id="owner-1",
                character_card_id="card-ann",
                connection_id="connection-1",
                platform="discord",
                workspace_id="guild-1",
                workspace_name="Guild",
                channel_id="channel-1",
                channel_name="general",
            )
        )
        session.commit()
    relationships = CharacterRelationshipService(database)
    now = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)
    fatigue = learned.record_evidence(
        evidence(delta=1.0, state_type="participation_fatigue"),
        now=now,
    )
    relationship = relationships.record_evidence(
        owner_id="owner-1",
        source_deployment_id="deployment-ann",
        target_type="actor",
        target_key="user-1",
        dimension="familiarity",
        delta=1.0,
        confidence=0.8,
        reason_code="meaningful_direct_interaction",
        source_message_id="message-2",
        now=now,
    )
    later = now + timedelta(hours=8)

    fatigue_later = learned.get(
        owner_id="owner-1",
        character_card_id="card-ann",
        state_type="participation_fatigue",
        subject_type="concept",
        subject_key="photography",
        now=later,
    )
    relationship_later = relationships.get_state(
        owner_id="owner-1",
        source_deployment_id="deployment-ann",
        target_type="actor",
        target_key="user-1",
        now=later,
    )

    assert fatigue_later is not None
    assert relationship_later is not None
    assert fatigue_later.value < fatigue.value * 0.1
    assert relationship_later.familiarity > relationship.familiarity * 0.9


def test_zero_signal_is_rejected(tmp_path: Path) -> None:
    _database, learned = service(tmp_path)
    try:
        learned.record_evidence(evidence(delta=0.0))
    except ValueError as exc:
        assert "non-zero" in str(exc)
    else:
        raise AssertionError("zero learned-state evidence must be rejected")
