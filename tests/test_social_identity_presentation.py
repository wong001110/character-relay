from __future__ import annotations

from echo_masque.character_learned_state import CharacterLearnedStateService, LearnedStateEvidence
from echo_masque.conversation_intelligence_observation import ConversationIntelligenceObservationService
from echo_masque.persistence.database import Database
from echo_masque.persistence.deployment_repository import DeploymentRepository
from echo_masque.persistence.discord_identity_repository import DiscordIdentityRepository
from echo_masque.persistence.models import CharacterCardRecord, TargetRecord


def _database() -> Database:
    database = Database("sqlite://")
    database.initialize()
    with database.session() as session:
        session.add(TargetRecord(id="target-1", name="Target", target_kind="custom"))
        session.add_all(
            [
                CharacterCardRecord(
                    id="card-center",
                    owner_id="owner-1",
                    target_id="target-1",
                    display_name="Center Card",
                ),
                CharacterCardRecord(
                    id="card-other",
                    owner_id="owner-1",
                    target_id="target-1",
                    display_name="Other Card",
                ),
            ]
        )
        session.commit()
    return database


def _relationship(
    database: Database,
    *,
    subject_key: str,
    source_message_id: str,
    connection_id: str = "connection-1",
) -> None:
    CharacterLearnedStateService(database).record_evidence(
        LearnedStateEvidence(
            owner_id="owner-1",
            character_card_id="card-center",
            state_type="relationship",
            subject_type="actor",
            subject_key=subject_key,
            delta=0.4,
            confidence=0.8,
            source_type="runtime_admission",
            source_message_id=source_message_id,
            connection_id=connection_id,
            guild_id="guild-1",
            channel_id="general",
        )
    )


def test_social_graph_resolves_guild_member_name_and_avatar_without_changing_uid_key() -> None:
    database = _database()
    identities = DiscordIdentityRepository(database)
    identities.upsert_guild_actor_identity(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        user_id="855820638199349248",
        guild_display_name="Server Nickname",
        global_display_name="Global Name",
        username="discord-user",
        avatar_url="https://cdn.discordapp.com/avatars/example/avatar.png",
    )
    _relationship(
        database,
        subject_key="actor:855820638199349248",
        source_message_id="human-message",
    )

    items = ConversationIntelligenceObservationService(database).social_ego_graph(
        owner_id="owner-1",
        character_card_id="card-center",
        connection_id="connection-1",
        guild_id="guild-1",
    )

    assert len(items) == 1
    item = items[0]
    assert item.subject_key == "actor:855820638199349248"
    assert item.discord_user_id == "855820638199349248"
    assert item.label == "Server Nickname"
    assert item.avatar_url == "https://cdn.discordapp.com/avatars/example/avatar.png"
    assert item.subject_type == "actor"
    assert item.is_bot is False


def test_social_graph_prefers_deployment_identity_for_character_neighbor() -> None:
    database = _database()
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
        character_card_id="card-other",
        connection_id=connection.id,
        workspace_id="guild-1",
        workspace_name="Guild",
        channel_id="general",
        channel_name="general",
        thread_id="",
        thread_name="",
        participation_mode="smart",
        memory_scope="server",
        version_label="",
        sticker_count=0,
        status="active",
    )
    identities = DiscordIdentityRepository(database)
    identities.upsert_identity(
        deployment_id=deployment.id,
        owner_id="owner-1",
        mode="webhook",
        display_name="Deployed Zhi",
        avatar_url="https://example.test/deployed-zhi.png",
    )
    identities.register_message_routes(
        connection_id=connection.id,
        deployment_id=deployment.id,
        workspace_id="guild-1",
        channel_id="general",
        thread_id="",
        webhook_id="webhook-1",
        message_ids=["character-message"],
    )
    _relationship(
        database,
        subject_key="actor:discord-bot-user",
        source_message_id="character-message",
        connection_id=connection.id,
    )

    items = ConversationIntelligenceObservationService(database).social_ego_graph(
        owner_id="owner-1",
        character_card_id="card-center",
        connection_id=connection.id,
        guild_id="guild-1",
    )

    assert len(items) == 1
    item = items[0]
    assert item.subject_key == "character:card-other"
    assert item.character_card_id == "card-other"
    assert item.label == "Deployed Zhi"
    assert item.avatar_url == "https://example.test/deployed-zhi.png"
    assert item.subject_type == "character"
    assert item.is_bot is True
