from __future__ import annotations

from echo_masque.api.connector_schemas import DiscordInboundMessage
from echo_masque.persistence.database import Database
from echo_masque.persistence.deployment_repository import DeploymentRepository
from echo_masque.persistence.discord_identity_repository import DiscordIdentityRepository
from echo_masque.persistence.models import CharacterCardRecord, TargetRecord
from echo_masque.social_event_runtime import ExplicitReplySocialEventProjector
from echo_masque.social_intelligence_v3 import SocialIntelligenceV3Service


def _seed() -> tuple[Database, str, str]:
    database = Database("sqlite://")
    database.initialize()
    with database.session() as session:
        session.add(TargetRecord(id="target-1", name="Target", target_kind="custom"))
        session.flush()
        session.add(
            CharacterCardRecord(
                id="card-1",
                owner_id="owner-1",
                target_id="target-1",
                display_name="Ann",
            )
        )
        session.commit()
    deployments = DeploymentRepository(database)
    connection = deployments.create_connection(
        owner_id="owner-1",
        platform="discord",
        display_name="Discord",
        connection_mode="bot",
        external_account_id="bot-1",
        status="active",
        metadata={},
    )
    deployment = deployments.create_deployment(
        owner_id="owner-1",
        character_card_id="card-1",
        connection_id=connection.id,
        workspace_id="guild-1",
        workspace_name="Guild",
        channel_id="channel-1",
        channel_name="general",
        thread_id="",
        thread_name="",
        participation_mode="smart",
        memory_scope="server",
        version_label="",
        sticker_count=0,
        status="active",
    )
    DiscordIdentityRepository(database).register_message_routes(
        connection_id=connection.id,
        deployment_id=deployment.id,
        workspace_id="guild-1",
        channel_id="channel-1",
        thread_id="",
        webhook_id="webhook-1",
        message_ids=["character-message"],
    )
    return database, connection.id, deployment.id


def _reply(*, connection_id: str, deployment_id: str) -> DiscordInboundMessage:
    return DiscordInboundMessage(
        connection_id=connection_id,
        deployment_id=deployment_id,
        message_id="user-reply",
        guild_id="guild-1",
        channel_id="channel-1",
        author_id="user-1",
        author_display_name="User",
        text="Got it",
        replied_to_bot=True,
        reply_to_message_id="character-message",
    )


def test_explicit_reply_to_known_character_creates_resolved_direct_interaction() -> None:
    database, connection_id, deployment_id = _seed()

    applied = ExplicitReplySocialEventProjector(database).observe(
        _reply(connection_id=connection_id, deployment_id=deployment_id)
    )

    assert applied is not None
    assert applied.applied is True
    assert applied.event.event_type == "direct_interaction"
    assert applied.event.status == "active"
    assert applied.event.source_relation_id
    assert applied.relationship is not None
    assert applied.relationship.familiarity > 0.0


def test_unresolved_semantic_interpretation_does_not_change_relationship_state() -> None:
    database, _, deployment_id = _seed()

    applied = SocialIntelligenceV3Service(database).record_event(
        owner_id="owner-1",
        source_deployment_id=deployment_id,
        target_type="actor",
        target_key="",
        event_type="insult",
        confidence=0.8,
        source_relation_id="semantic-relation-1",
        relation_resolved=False,
        source_message_ids=("ambiguous-message",),
        reason="semantic target unresolved",
    )

    assert applied.applied is False
    assert applied.event.status == "unresolved"
    assert applied.relationship is None


def test_impression_remains_available_to_character_prompt_context() -> None:
    database, _, deployment_id = _seed()
    service = SocialIntelligenceV3Service(database)
    service.revise_impression(
        owner_id="owner-1",
        source_deployment_id=deployment_id,
        target_type="actor",
        target_key="user-1",
        summary="Keeps explanations concise.",
        observations=("Responds well to direct answers.",),
        confidence=0.9,
        evidence_refs=("message:user-reply",),
    )

    guidance = service.prompt_context(
        owner_id="owner-1",
        source_deployment_id=deployment_id,
        target_type="actor",
        target_key="user-1",
    )

    assert any("Current impression: Responds well to direct answers." in item for item in guidance)


def test_relationship_prompt_context_uses_qualitative_posture_without_scores() -> None:
    database, _, deployment_id = _seed()
    service = SocialIntelligenceV3Service(database)
    service.record_event(
        owner_id="owner-1",
        source_deployment_id=deployment_id,
        target_type="actor",
        target_key="user-1",
        event_type="praise",
        confidence=1.0,
        relation_resolved=True,
        source_message_ids=("message-1",),
        reason="test",
    )

    guidance = service.prompt_context(
        owner_id="owner-1",
        source_deployment_id=deployment_id,
        target_type="actor",
        target_key="user-1",
    )

    text = "\n".join(guidance)
    assert "Suggested social posture:" in text
    assert "familiarity=" not in text
    assert "affinity=" not in text
    assert "trust=" not in text
    assert "comfort=" not in text
