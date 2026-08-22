from types import SimpleNamespace

from echo_masque.api.routes.intelligence_product_completion import (
    deployment_social_intelligence,
)
from echo_masque.auth import AuthenticatedUser
from echo_masque.persistence.database import Database
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord
from echo_masque.persistence.deployment_repository import DeploymentRepository
from echo_masque.persistence.discord_identity_models import (
    DeploymentMessageIdentityRecord,
    DiscordGuildActorIdentityRecord,
)
from echo_masque.persistence.models import CharacterCardRecord, TargetRecord
from echo_masque.social_intelligence_v3 import SocialIntelligenceV3Service


def _database() -> Database:
    database = Database("sqlite://")
    database.initialize()
    with database.session() as session:
        session.add(TargetRecord(id="target-1", name="Target", target_kind="custom"))
        session.commit()
    with database.session() as session:
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
        session.flush()
        session.add_all(
            [
                CharacterDeploymentRecord(
                    id="deployment-center",
                    owner_id="owner-1",
                    character_card_id="card-center",
                    connection_id="connection-1",
                    platform="discord",
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
                ),
                CharacterDeploymentRecord(
                    id="deployment-other",
                    owner_id="owner-1",
                    character_card_id="card-other",
                    connection_id="connection-1",
                    platform="discord",
                    workspace_id="guild-1",
                    workspace_name="Guild",
                    channel_id="other",
                    channel_name="other",
                    thread_id="",
                    thread_name="",
                    participation_mode="smart",
                    memory_scope="server",
                    version_label="",
                    sticker_count=0,
                    status="active",
                ),
            ]
        )
        session.flush()
        session.add_all(
            [
                DeploymentMessageIdentityRecord(
                    deployment_id="deployment-other",
                    owner_id="owner-1",
                    mode="webhook",
                    display_name="Deployed Zhi",
                    avatar_url="https://example.test/deployed-zhi.png",
                ),
                DiscordGuildActorIdentityRecord(
                    id="actor-1",
                    owner_id="owner-1",
                    connection_id="connection-1",
                    guild_id="guild-1",
                    user_id="855820638199349248",
                    guild_display_name="Server Nickname",
                    global_display_name="Global Name",
                    username="discord-user",
                    avatar_url="https://cdn.discordapp.com/avatars/example/avatar.png",
                    is_bot=False,
                ),
            ]
        )
        session.commit()
    return database


def _view(database: Database):  # type: ignore[no-untyped-def]
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(deployment_repository=DeploymentRepository(database))
        )
    )
    user = AuthenticatedUser(
        id="owner-1", email="owner@example.test", display_name="Owner", role="user", is_active=True
    )
    return deployment_social_intelligence("deployment-center", request, user)  # type: ignore[arg-type]


def test_social_product_preserves_actor_identity_presentation_without_changing_key() -> None:
    database = _database()
    SocialIntelligenceV3Service(database).record_event(
        owner_id="owner-1",
        source_deployment_id="deployment-center",
        target_type="actor",
        target_key="855820638199349248",
        event_type="direct_interaction",
        confidence=0.8,
        relation_resolved=True,
        source_message_ids=("human-message",),
    )
    item = _view(database).items[0]
    assert item.target_key == "855820638199349248"
    assert item.label == "Server Nickname"
    assert item.avatar_url == "https://cdn.discordapp.com/avatars/example/avatar.png"
    assert item.target_type == "actor"
    assert item.target_kind == "user"


def test_social_product_uses_deployment_identity_for_character_neighbor() -> None:
    database = _database()
    SocialIntelligenceV3Service(database).record_event(
        owner_id="owner-1",
        source_deployment_id="deployment-center",
        target_type="deployment",
        target_key="deployment-other",
        event_type="direct_interaction",
        confidence=0.8,
        relation_resolved=True,
        source_message_ids=("character-message",),
    )
    item = _view(database).items[0]
    assert item.target_key == "deployment-other"
    assert item.label == "Other Card"
    assert item.avatar_url == "https://example.test/deployed-zhi.png"
    assert item.target_type == "deployment"
    assert item.target_kind == "character"
