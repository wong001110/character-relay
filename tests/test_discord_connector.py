from pathlib import Path

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr

from echo_masque.api import create_app
from echo_masque.config import Settings

ADMIN_EMAIL = "discord-admin@example.com"
ADMIN_PASSWORD = "DiscordConnectorAdmin2026!"
CONNECTOR_SECRET = "discord-connector-shared-secret"


def settings(path: Path) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{path}",
        legacy_local_user_enabled=False,
        bootstrap_admin_email=ADMIN_EMAIL,
        bootstrap_admin_password=SecretStr(ADMIN_PASSWORD),
        bootstrap_admin_display_name="Discord Admin",
        credential_encryption_keys=SecretStr(Fernet.generate_key().decode("ascii")),
        connector_shared_secret=SecretStr(CONNECTOR_SECRET),
    )


def login(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200, response.text


def connector_headers(secret: str = CONNECTOR_SECRET) -> dict[str, str]:
    return {"Authorization": f"Bearer {secret}"}


def seed_deployment(client: TestClient) -> tuple[dict[str, object], dict[str, object]]:
    login(client)
    character_response = client.post(
        "/api/characters",
        json={
            "target_id": "demo-stable",
            "display_name": "Ann",
            "subtitle": "Discord connector fixture",
            "subject_type": "companion",
            "persona_summary": "A calm social character.",
            "traits": ["calm"],
            "tags": ["discord"],
            "expected_tone": "Concise and gentle.",
            "forbidden_behaviors": ["invent private memories"],
            "memory_summary": "Use only supplied Discord context.",
            "preferred_suites": ["identity_integrity"],
            "portrait_variant": "lavender",
        },
    )
    assert character_response.status_code == 201, character_response.text
    character = character_response.json()

    connection_response = client.post(
        "/api/connections",
        json={
            "platform": "discord",
            "display_name": "Character Relay Discord",
            "connection_mode": "managed",
            "external_account_id": "",
            "status": "disconnected",
            "metadata": {},
        },
    )
    assert connection_response.status_code == 201, connection_response.text
    connection = connection_response.json()

    deployment_response = client.post(
        "/api/deployments",
        json={
            "character_card_id": character["id"],
            "connection_id": connection["id"],
            "workspace_id": "guild-001",
            "workspace_name": "Test Guild",
            "channel_id": "channel-001",
            "channel_name": "ann-room",
            "thread_id": "",
            "thread_name": "",
            "participation_mode": "mention_and_reply",
            "memory_scope": "channel_isolated",
            "version_label": "Current",
            "sticker_count": 0,
            "status": "active",
        },
    )
    assert deployment_response.status_code == 201, deployment_response.text
    return connection, deployment_response.json()


def test_connector_requires_shared_secret(tmp_path: Path) -> None:
    client = TestClient(create_app(settings(tmp_path / "discord-auth.db")))
    response = client.get(
        "/api/connectors/discord/deployments",
        params={"connection_id": "missing"},
        headers=connector_headers("wrong-secret"),
    )
    assert response.status_code == 401


def test_discord_connector_lists_routes_heartbeats_and_replies(tmp_path: Path) -> None:
    client = TestClient(create_app(settings(tmp_path / "discord-connector.db")))
    connection, deployment = seed_deployment(client)

    listing = client.get(
        "/api/connectors/discord/deployments",
        params={"connection_id": connection["id"]},
        headers=connector_headers(),
    )
    assert listing.status_code == 200, listing.text
    assert listing.json() == [
        {
            "deployment_id": deployment["id"],
            "connection_id": connection["id"],
            "character_card_id": deployment["character_card_id"],
            "character_display_name": "Ann",
            "workspace_id": "guild-001",
            "workspace_name": "Test Guild",
            "channel_id": "channel-001",
            "channel_name": "ann-room",
            "thread_id": "",
            "thread_name": "",
            "participation_mode": "mention_and_reply",
            "version_label": "Current",
            "status": "active",
        }
    ]

    heartbeat = client.post(
        "/api/connectors/discord/heartbeat",
        headers=connector_headers(),
        json={
            "connection_id": connection["id"],
            "bot_user_id": "bot-001",
            "bot_display_name": "Character Relay#0001",
            "status": "connected",
            "last_error": "",
        },
    )
    assert heartbeat.status_code == 204, heartbeat.text

    silent = client.post(
        "/api/connectors/discord/messages",
        headers=connector_headers(),
        json={
            "connection_id": connection["id"],
            "message_id": "message-001",
            "guild_id": "guild-001",
            "guild_name": "Test Guild",
            "channel_id": "channel-001",
            "channel_name": "ann-room",
            "thread_id": "",
            "thread_name": "",
            "author_id": "user-001",
            "author_display_name": "Juen",
            "text": "The group is talking without addressing Ann.",
            "mentioned_bot": False,
            "replied_to_bot": False,
            "smart_candidate": False,
            "recent_messages": [],
        },
    )
    assert silent.status_code == 200, silent.text
    assert silent.json()["action"] == "silent"
    assert silent.json()["reason"] == "trigger_not_matched"

    reply = client.post(
        "/api/connectors/discord/messages",
        headers=connector_headers(),
        json={
            "connection_id": connection["id"],
            "message_id": "message-002",
            "guild_id": "guild-001",
            "guild_name": "Test Guild",
            "channel_id": "channel-001",
            "channel_name": "ann-room",
            "thread_id": "",
            "thread_name": "",
            "author_id": "user-001",
            "author_display_name": "Juen",
            "text": "Ann, what do you think?",
            "mentioned_bot": True,
            "replied_to_bot": False,
            "smart_candidate": False,
            "recent_messages": [
                {
                    "message_id": "message-002",
                    "author_id": "user-001",
                    "author_display_name": "Juen",
                    "text": "Ann, what do you think?",
                    "is_bot": False,
                }
            ],
        },
    )
    assert reply.status_code == 200, reply.text
    payload = reply.json()
    assert payload["action"] == "reply"
    assert payload["deployment_id"] == deployment["id"]
    assert payload["character_display_name"] == "Ann"
    assert payload["reply_to_message_id"] == "message-002"
    assert payload["text"]
