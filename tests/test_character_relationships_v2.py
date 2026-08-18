from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from echo_masque.character_relationships import CharacterRelationshipService
from echo_masque.persistence import Database
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord
from echo_masque.persistence.models import CharacterCardRecord


def seed(database: Database) -> None:
    with database.session() as session:
        session.add_all(
            [
                CharacterCardRecord(
                    id="card-a",
                    owner_id="owner-1",
                    target_id="target-1",
                    display_name="A",
                    persona_summary="Direct and analytical.",
                ),
                CharacterCardRecord(
                    id="card-b",
                    owner_id="owner-1",
                    target_id="target-1",
                    display_name="B",
                    persona_summary="Warm but stubborn.",
                ),
                CharacterDeploymentRecord(
                    id="dep-a",
                    owner_id="owner-1",
                    character_card_id="card-a",
                    connection_id="connection-1",
                    platform="discord",
                    workspace_id="guild-1",
                    workspace_name="Guild",
                    channel_id="general",
                    channel_name="general",
                    participation_mode="smart",
                ),
                CharacterDeploymentRecord(
                    id="dep-b",
                    owner_id="owner-1",
                    character_card_id="card-b",
                    connection_id="connection-1",
                    platform="discord",
                    workspace_id="guild-1",
                    workspace_name="Guild",
                    channel_id="other",
                    channel_name="other",
                    participation_mode="smart",
                ),
            ]
        )
        session.commit()


def service() -> CharacterRelationshipService:
    database = Database("sqlite://")
    database.initialize()
    seed(database)
    return CharacterRelationshipService(database)


def test_canonical_prior_initializes_directional_server_baseline() -> None:
    relationships = service()
    relationships.upsert_prior(
        owner_id="owner-1",
        source_character_card_id="card-a",
        target_character_card_id="card-b",
        relationship_type="partners",
        description="Long-term partners.",
        familiarity=0.9,
        affinity=0.8,
        trust=0.85,
        comfort=0.78,
    )
    relationships.upsert_prior(
        owner_id="owner-1",
        source_character_card_id="card-b",
        target_character_card_id="card-a",
        relationship_type="partners",
        description="Long-term partners.",
        familiarity=0.9,
        affinity=0.68,
        trust=0.72,
        comfort=0.6,
    )

    a_to_b = relationships.initialize_character_pair(
        owner_id="owner-1",
        source_deployment_id="dep-a",
        target_deployment_id="dep-b",
    )
    b_to_a = relationships.initialize_character_pair(
        owner_id="owner-1",
        source_deployment_id="dep-b",
        target_deployment_id="dep-a",
    )

    assert a_to_b.affinity == pytest.approx(0.8)
    assert b_to_a.affinity == pytest.approx(0.68)
    assert a_to_b.trust != b_to_a.trust


def test_dynamic_delta_decays_toward_canonical_baseline_not_zero() -> None:
    relationships = service()
    relationships.upsert_prior(
        owner_id="owner-1",
        source_character_card_id="card-a",
        target_character_card_id="card-b",
        relationship_type="partners",
        description="",
        familiarity=0.9,
        affinity=0.7,
        trust=0.8,
        comfort=0.7,
    )
    now = datetime.now(UTC)
    relationships.initialize_character_pair(
        owner_id="owner-1",
        source_deployment_id="dep-a",
        target_deployment_id="dep-b",
        now=now,
    )
    after_conflict = relationships.record_evidence(
        owner_id="owner-1",
        source_deployment_id="dep-a",
        target_type="deployment",
        target_key="dep-b",
        dimension="affinity",
        delta=-0.4,
        confidence=1.0,
        reason_code="meaningful_conflict",
        now=now,
    )
    later = relationships.get_state(
        owner_id="owner-1",
        source_deployment_id="dep-a",
        target_type="deployment",
        target_key="dep-b",
        now=now + timedelta(days=90),
    )
    assert later is not None
    assert after_conflict.affinity == pytest.approx(0.3)
    assert later.affinity > after_conflict.affinity
    assert later.affinity < 0.7
    assert later.affinity == pytest.approx(0.6, abs=0.02)


def test_ordinary_interaction_only_increases_familiarity() -> None:
    relationships = service()
    current = relationships.record_interaction_familiarity(
        owner_id="owner-1",
        source_deployment_id="dep-a",
        target_type="actor",
        target_key="human-1",
        source_message_id="m1",
        source_burst_id="burst-1",
    )
    assert current.familiarity > 0
    assert current.affinity == 0
    assert current.trust == 0
    assert current.comfort == 0


def test_social_prompt_is_bounded_and_uses_evidence_grounded_impression() -> None:
    relationships = service()
    relationships.record_interaction_familiarity(
        owner_id="owner-1",
        source_deployment_id="dep-a",
        target_type="actor",
        target_key="human-1",
    )
    relationships.record_evidence(
        owner_id="owner-1",
        source_deployment_id="dep-a",
        target_type="actor",
        target_key="human-1",
        dimension="comfort",
        delta=0.5,
        confidence=0.8,
        reason_code="repeated_relaxed_interaction",
    )
    relationships.upsert_impression(
        owner_id="owner-1",
        source_deployment_id="dep-a",
        target_type="actor",
        target_key="human-1",
        summary="Uses concrete examples when discussing technical problems.",
        observations=(
            "Often explains technical problems with screenshots.",
            "Prefers direct technical discussion.",
            "This extra observation should remain bounded.",
        ),
        evidence_refs=("m1", "m2"),
        confidence=0.8,
    )
    guidance = relationships.social_prompt_guidance(
        owner_id="owner-1",
        source_deployment_id="dep-a",
        target_type="actor",
        target_key="human-1",
        max_chars=300,
    )
    assert guidance
    combined = "\n".join(guidance)
    assert len(combined) <= 320
    assert "screenshots" in combined or "direct technical" in combined
    assert "social context" in combined.lower()
