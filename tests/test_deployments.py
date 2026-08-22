from pathlib import Path
from typing import cast
from uuid import uuid4

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr

from echo_masque.api import create_app
from echo_masque.config import Settings
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord

ADMIN_EMAIL = "relay-admin@example.com"
ADMIN_PASSWORD = "CharacterRelayAdmin2026!"


def settings(path: Path) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{path}",
        legacy_local_user_enabled=False,
        bootstrap_admin_email=ADMIN_EMAIL,
        bootstrap_admin_password=SecretStr(ADMIN_PASSWORD),
        bootstrap_admin_display_name="Relay Admin",
        credential_encryption_keys=SecretStr(Fernet.generate_key().decode("ascii")),
    )


def login(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200, response.text


def create_character(client: TestClient) -> dict[str, object]:
    response = client.post(
        "/api/characters/prompt-model",
        json={
            "display_name": "Ann",
            "subtitle": "Published social character",
            "subject_type": "companion",
            "persona_summary": "A calm character prepared for group-chat deployment.",
            "traits": ["calm", "observant"],
            "tags": ["deployment"],
            "expected_tone": "Warm but concise.",
            "forbidden_behaviors": ["invent private memories"],
            "memory_summary": "Keep each group memory isolated.",
            "preferred_suites": ["identity_integrity"],
            "portrait_variant": "lavender",
            "provider": "deepseek",
            "base_url": "https://api.deepseek.com",
            "model": "deepseek-v4-flash",
            "system_prompt": "You are Ann.",
            "temperature": 0.4,
            "api_key": "test-provider-key",
        },
    )
    assert response.status_code == 201, response.text
    return cast(dict[str, object], response.json())


def create_connection(client: TestClient, suffix: str = "primary") -> dict[str, object]:
    response = client.post(
        "/api/connections",
        json={
            "platform": "discord",
            "display_name": f"Discord Bot {suffix}",
            "connection_mode": "managed",
            "external_account_id": f"bot-{suffix}",
            "status": "connected",
            "metadata": {},
        },
    )
    assert response.status_code == 201, response.text
    return cast(dict[str, object], response.json())


def deployment_payload(
    *,
    character_id: object,
    connection_id: object,
    workspace_id: str,
    channel_id: str,
    channel_name: str,
    status: str = "paused",
) -> dict[str, object]:
    return {
        "character_card_id": character_id,
        "connection_id": connection_id,
        "workspace_id": workspace_id,
        "workspace_name": f"Server {workspace_id}",
        "channel_id": channel_id,
        "channel_name": channel_name,
        "thread_id": "",
        "thread_name": "",
        "participation_mode": "mention_and_reply",
        "memory_scope": "channel_isolated",
        "version_label": "v1.0",
        "sticker_count": 12,
        "status": status,
    }


def test_connection_and_deployment_lifecycle(tmp_path: Path) -> None:
    client = TestClient(create_app(settings(tmp_path / "deployments.db")))
    login(client)
    character = create_character(client)

    connection_response = client.post(
        "/api/connections",
        json={
            "platform": "discord",
            "display_name": "Primary Discord Bot",
            "connection_mode": "managed",
            "external_account_id": "bot-123",
            "status": "connected",
            "metadata": {"guild_installation": "pending"},
        },
    )
    assert connection_response.status_code == 201, connection_response.text
    connection = connection_response.json()

    payload = deployment_payload(
        character_id=character["id"],
        connection_id=connection["id"],
        workspace_id="guild-001",
        channel_id="channel-001",
        channel_name="#ann-room",
    )
    deployment_response = client.post("/api/deployments", json=payload)
    assert deployment_response.status_code == 201, deployment_response.text
    deployment = deployment_response.json()
    assert deployment["character_display_name"] == "Ann"
    assert deployment["platform"] == "discord"
    assert deployment["channel_name"] == "#ann-room"
    assert deployment["sticker_count"] == 12

    duplicate = client.post("/api/deployments", json=payload)
    assert duplicate.status_code == 409

    duplicate_other_channel = client.post(
        "/api/deployments",
        json={
            **payload,
            "channel_id": "channel-002",
            "channel_name": "#another-room",
        },
    )
    assert duplicate_other_channel.status_code == 409

    listed = client.get(f"/api/deployments?character_card_id={character['id']}")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [deployment["id"]]

    activated = client.patch(
        f"/api/deployments/{deployment['id']}/status",
        json={"status": "active", "last_error": ""},
    )
    assert activated.status_code == 200, activated.text
    assert activated.json()["status"] == "active"

    updated = client.put(
        f"/api/deployments/{deployment['id']}",
        json={
            "participation_mode": "smart",
            "memory_scope": "server_shared",
            "sticker_count": 18,
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["participation_mode"] == "smart"
    assert updated.json()["memory_scope"] == "server_shared"
    assert updated.json()["sticker_count"] == 18

    deleted_connection = client.delete(f"/api/connections/{connection['id']}")
    assert deleted_connection.status_code == 204
    assert client.get("/api/connections").json() == []
    assert client.get("/api/deployments").json() == []


def test_same_character_can_deploy_to_different_discord_servers_but_not_move_into_conflict(
    tmp_path: Path,
) -> None:
    client = TestClient(create_app(settings(tmp_path / "deployment-server-identity.db")))
    login(client)
    character = create_character(client)
    connection = create_connection(client, "server-identity")

    first = client.post(
        "/api/deployments",
        json=deployment_payload(
            character_id=character["id"],
            connection_id=connection["id"],
            workspace_id="guild-a",
            channel_id="channel-a",
            channel_name="#a",
        ),
    )
    assert first.status_code == 201, first.text

    second = client.post(
        "/api/deployments",
        json=deployment_payload(
            character_id=character["id"],
            connection_id=connection["id"],
            workspace_id="guild-b",
            channel_id="channel-b",
            channel_name="#b",
        ),
    )
    assert second.status_code == 201, second.text

    conflict_move = client.put(
        f"/api/deployments/{second.json()['id']}",
        json={
            "workspace_id": "guild-a",
            "workspace_name": "Server guild-a",
            "channel_id": "channel-c",
            "channel_name": "#c",
        },
    )
    assert conflict_move.status_code == 409, conflict_move.text


def test_platform_account_is_editable_and_keeps_user_label_after_heartbeat(
    tmp_path: Path,
) -> None:
    app = create_app(settings(tmp_path / "connection-edit.db"))
    client = TestClient(app)
    login(client)
    created = client.post(
        "/api/connections",
        json={
            "platform": "discord",
            "display_name": "Original label",
            "connection_mode": "managed",
            "external_account_id": "",
            "status": "disconnected",
            "metadata": {},
        },
    )
    assert created.status_code == 201, created.text
    connection_id = created.json()["id"]

    updated = client.patch(
        f"/api/connections/{connection_id}",
        json={
            "display_name": "My Companion Server Bot",
            "connection_mode": "local",
            "external_account_id": "manual-bot-id",
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["display_name"] == "My Companion Server Bot"
    assert updated.json()["connection_mode"] == "local"
    assert updated.json()["external_account_id"] == "manual-bot-id"

    assert app.state.deployment_repository.heartbeat_connection(
        connection_id=connection_id,
        platform="discord",
        external_account_id="live-bot-id",
        display_name="CharacterRelayBot#1234",
        status="connected",
        last_error="",
    )
    listed = client.get("/api/connections")
    assert listed.status_code == 200
    account = listed.json()[0]
    assert account["display_name"] == "My Companion Server Bot"
    assert account["external_account_id"] == "live-bot-id"
    assert account["metadata"]["connector_display_name"] == "CharacterRelayBot#1234"


def test_deployment_rejects_missing_owned_resources(tmp_path: Path) -> None:
    client = TestClient(create_app(settings(tmp_path / "deployment-ownership.db")))
    login(client)

    response = client.post(
        "/api/deployments",
        json={
            "character_card_id": "missing-character",
            "connection_id": "missing-connection",
            "workspace_id": "",
            "workspace_name": "",
            "channel_id": "channel-001",
            "channel_name": "#general",
            "thread_id": "",
            "thread_name": "",
            "participation_mode": "mention_only",
            "memory_scope": "channel_isolated",
            "version_label": "Current",
            "sticker_count": 0,
            "status": "paused",
        },
    )
    assert response.status_code == 404


def test_new_connections_and_deployments_reject_unsupported_platforms_but_keep_legacy_records(
    tmp_path: Path,
) -> None:
    app = create_app(settings(tmp_path / "legacy-platform-compatibility.db"))
    client = TestClient(app)
    login(client)
    character = create_character(client)

    for platform in ("whatsapp", "telegram"):
        response = client.post(
            "/api/connections",
            json={
                "platform": platform,
                "display_name": f"{platform.title()} connector",
                "connection_mode": "managed",
                "external_account_id": "",
                "status": "disconnected",
                "metadata": {},
            },
        )
        assert response.status_code == 422
        assert "Only Discord connections can be created" in response.json()["detail"]

    owner = app.state.auth_repository.get_user_by_email(ADMIN_EMAIL)
    assert owner is not None
    legacy_connection = app.state.deployment_repository.create_connection(
        owner_id=owner.id,
        platform="whatsapp",
        display_name="Retired WhatsApp connector",
        connection_mode="local",
        external_account_id="legacy-device",
        status="disconnected",
        metadata={},
    )
    legacy_deployment_id = str(uuid4())
    with app.state.database.session() as session:
        session.add(
            CharacterDeploymentRecord(
                id=legacy_deployment_id,
                owner_id=owner.id,
                character_card_id=str(character["id"]),
                connection_id=legacy_connection.id,
                platform="whatsapp",
                workspace_id="legacy-workspace",
                workspace_name="Retired WhatsApp group",
                channel_id="legacy-channel",
                channel_name="Legacy group",
                thread_id="",
                thread_name="",
                participation_mode="mention_and_reply",
                memory_scope="channel_isolated",
                version_label="Legacy",
                sticker_count=0,
                status="paused",
            )
        )
        session.commit()

    connections = client.get("/api/connections")
    assert connections.status_code == 200
    assert connections.json()[0]["platform"] == "whatsapp"
    deployments = client.get("/api/deployments")
    assert deployments.status_code == 200
    assert deployments.json()[0]["platform"] == "whatsapp"

    rejected_deployment = client.post(
        "/api/deployments",
        json=deployment_payload(
            character_id=character["id"],
            connection_id=legacy_connection.id,
            workspace_id="legacy-workspace",
            channel_id="new-channel",
            channel_name="New legacy group",
        ),
    )
    assert rejected_deployment.status_code == 422
    assert "Only Discord deployments can be created" in rejected_deployment.json()["detail"]

    assert client.delete(f"/api/deployments/{legacy_deployment_id}").status_code == 204
    assert client.delete(f"/api/connections/{legacy_connection.id}").status_code == 204


def test_deployment_page_filters_and_reports_global_counts(tmp_path: Path) -> None:
    client = TestClient(create_app(settings(tmp_path / "deployment-pagination.db")))
    login(client)
    connection = client.post(
        "/api/connections",
        json={
            "platform": "discord",
            "display_name": "Pagination Discord",
            "connection_mode": "managed",
            "external_account_id": "bot-pagination",
            "status": "connected",
            "metadata": {},
        },
    ).json()
    for index in range(5):
        character = create_character(client)
        created = client.post(
            "/api/deployments",
            json={
                "character_card_id": character["id"],
                "connection_id": connection["id"],
                "workspace_id": "guild-pagination",
                "workspace_name": "Pagination Guild",
                "channel_id": f"channel-{index}",
                "channel_name": f"#channel-{index}",
                "thread_id": "",
                "thread_name": "",
                "participation_mode": "mention_and_reply",
                "memory_scope": "channel_isolated",
                "version_label": "Current",
                "sticker_count": 0,
                "status": "active" if index < 3 else "paused",
            },
        )
        assert created.status_code == 201, created.text

    first = client.get(
        "/api/deployments/page",
        params={"page": 1, "page_size": 2},
    )
    assert first.status_code == 200, first.text
    payload = first.json()
    assert payload["total"] == 5
    assert payload["pages"] == 3
    assert len(payload["items"]) == 2
    assert payload["active"] == 3
    assert payload["paused"] == 2
    assert payload["attention"] == 0

    paused = client.get(
        "/api/deployments/page",
        params={"page_size": 10, "status": "paused"},
    )
    assert paused.status_code == 200
    assert paused.json()["total"] == 2
    assert all(item["status"] == "paused" for item in paused.json()["items"])
