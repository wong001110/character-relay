from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr

from echo_masque.api import create_app
from echo_masque.config import Settings
from echo_masque.persistence.conversation_structure_models import ConversationSegmentV3Record
from echo_masque.persistence.conversation_structure_repository import (
    ConversationStructureRepository,
)
from echo_masque.persistence.database import Database
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord
from echo_masque.persistence.discovery_models import (
    DeploymentDiscoveryExposureRecord,
    DeploymentDiscoveryProfileRecord,
)
from echo_masque.persistence.discovery_repository import DiscoveryRepository


def _settings(path: Path) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{path}",
        legacy_local_user_enabled=False,
        bootstrap_admin_email="cursor-admin@example.com",
        bootstrap_admin_password=SecretStr("CursorAdmin2026!"),
        bootstrap_admin_display_name="Cursor Admin",
        credential_encryption_keys=SecretStr(Fernet.generate_key().decode("ascii")),
    )


def test_discovery_exposure_cursor_continues_without_duplicates_and_keeps_scope(tmp_path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'discovery-page.db'}")
    database.initialize()
    now = datetime(2026, 8, 24, 10, 0, tzinfo=UTC)
    with database.session() as session:
        session.add_all(
            [
                DeploymentDiscoveryExposureRecord(
                    id=f"exposure-{index}",
                    owner_id="owner-a",
                    deployment_id="deployment-a",
                    discovery_item_id=f"item-{index}",
                    last_exposed_at=now - timedelta(minutes=index),
                    first_exposed_at=now - timedelta(minutes=index),
                )
                for index in range(3)
            ]
            + [
                DeploymentDiscoveryExposureRecord(
                    id="other-deployment",
                    owner_id="owner-a",
                    deployment_id="deployment-b",
                    discovery_item_id="item-other-deployment",
                    last_exposed_at=now + timedelta(minutes=1),
                    first_exposed_at=now,
                ),
                DeploymentDiscoveryExposureRecord(
                    id="other-owner",
                    owner_id="owner-b",
                    deployment_id="deployment-a",
                    discovery_item_id="item-other-owner",
                    last_exposed_at=now + timedelta(minutes=2),
                    first_exposed_at=now,
                ),
            ]
        )
        session.commit()

    repository = DiscoveryRepository(database)
    first, cursor = repository.list_exposures_page(
        owner_id="owner-a", deployment_id="deployment-a", limit=2
    )
    assert [item.id for item in first] == ["exposure-0", "exposure-1"]
    assert cursor is not None

    second, next_cursor = repository.list_exposures_page(
        owner_id="owner-a", deployment_id="deployment-a", limit=2, cursor=cursor
    )
    assert [item.id for item in second] == ["exposure-2"]
    assert next_cursor is None
    assert {item.id for item in first}.isdisjoint(item.id for item in second)


def test_conversation_segment_cursor_continues_within_server_scope(tmp_path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'conversation-page.db'}")
    database.initialize()
    now = datetime(2026, 8, 24, 10, 0, tzinfo=UTC)
    with database.session() as session:
        session.add_all(
            [
                ConversationSegmentV3Record(
                    id=f"segment-{index}",
                    owner_id="owner-a",
                    burst_id=f"burst-{index}",
                    segment_key=f"key-{index}",
                    connection_id="connection-a",
                    guild_id="guild-a",
                    channel_id="channel-a",
                    created_at=now - timedelta(minutes=index),
                )
                for index in range(3)
            ]
            + [
                ConversationSegmentV3Record(
                    id="other-guild",
                    owner_id="owner-a",
                    burst_id="other-guild-burst",
                    segment_key="other-guild-key",
                    connection_id="connection-a",
                    guild_id="guild-b",
                    channel_id="channel-b",
                    created_at=now + timedelta(minutes=1),
                ),
                ConversationSegmentV3Record(
                    id="other-owner",
                    owner_id="owner-b",
                    burst_id="other-owner-burst",
                    segment_key="other-owner-key",
                    connection_id="connection-a",
                    guild_id="guild-a",
                    channel_id="channel-a",
                    created_at=now + timedelta(minutes=2),
                ),
            ]
        )
        session.commit()

    repository = ConversationStructureRepository(database)
    first, cursor = repository.recent_segments_page(
        owner_id="owner-a", connection_id="connection-a", guild_id="guild-a", limit=2
    )
    assert [item.id for item in first] == ["segment-0", "segment-1"]
    assert cursor is not None

    second, next_cursor = repository.recent_segments_page(
        owner_id="owner-a",
        connection_id="connection-a",
        guild_id="guild-a",
        limit=2,
        cursor=cursor,
    )
    assert [item.id for item in second] == ["segment-2"]
    assert next_cursor is None
    assert {item.id for item in first}.isdisjoint(item.id for item in second)


def test_discovery_cursor_endpoint_rejects_malformed_cursor_after_scope_check(tmp_path) -> None:
    app = create_app(_settings(tmp_path / "cursor-route.db"))
    client = TestClient(app)
    login = client.post(
        "/api/auth/login",
        json={"email": "cursor-admin@example.com", "password": "CursorAdmin2026!"},
    )
    assert login.status_code == 200, login.text
    owner_id = app.state.auth_repository.get_user_by_email("cursor-admin@example.com")
    assert owner_id is not None
    with app.state.database.session() as session:
        session.add(
            CharacterDeploymentRecord(
                id="deployment-a",
                owner_id=owner_id.id,
                character_card_id="character-a",
                connection_id="connection-a",
                platform="discord",
                workspace_id="guild-a",
                workspace_name="Guild A",
                channel_id="channel-a",
                channel_name="general",
                thread_id="",
                thread_name="",
                participation_mode="smart",
                memory_scope="server_shared",
                version_label="Current",
                sticker_count=0,
                status="active",
            )
        )
        session.add(
            DeploymentDiscoveryProfileRecord(
                deployment_id="deployment-a",
                owner_id=owner_id.id,
            )
        )
        session.commit()

    response = client.get(
        "/api/deployments/deployment-a/discovery/exposures",
        params={"cursor": "not-a-valid-cursor"},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "Invalid pagination cursor."
