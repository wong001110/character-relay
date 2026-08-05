from pathlib import Path

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr

from echo_masque.api import create_app
from echo_masque.api.connector_schemas import DiscordConnectorReplyView
from echo_masque.config import Settings

ADMIN_EMAIL = "logs-admin@example.com"
ADMIN_PASSWORD = "ConnectorLogsAdmin2026!"
CONNECTOR_SECRET = "connector-log-secret"


def settings(path: Path) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{path}",
        legacy_local_user_enabled=False,
        bootstrap_admin_email=ADMIN_EMAIL,
        bootstrap_admin_password=SecretStr(ADMIN_PASSWORD),
        bootstrap_admin_display_name="Logs Admin",
        credential_encryption_keys=SecretStr(Fernet.generate_key().decode("ascii")),
        connector_shared_secret=SecretStr(CONNECTOR_SECRET),
    )


def login(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200, response.text


def test_connector_events_are_visible_without_message_content(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "deployment-logs.db"))
    client = TestClient(app)
    login(client)

    character = client.post(
        "/api/characters",
        json={
            "target_id": "demo-stable",
            "display_name": "Ann",
            "subtitle": "Connector logs fixture",
            "subject_type": "companion",
            "persona_summary": "A concise Discord character.",
            "traits": ["calm"],
            "tags": ["discord"],
            "expected_tone": "Concise.",
            "forbidden_behaviors": ["invent private memories"],
            "memory_summary": "Use supplied context only.",
            "preferred_suites": ["identity_integrity"],
            "portrait_variant": "lavender",
        },
    ).json()
    connection = client.post(
        "/api/connections",
        json={
            "platform": "discord",
            "display_name": "Discord Connector",
            "connection_mode": "managed",
            "external_account_id": "",
            "status": "connected",
            "metadata": {},
        },
    ).json()
    deployment = client.post(
        "/api/deployments",
        json={
            "character_card_id": character["id"],
            "connection_id": connection["id"],
            "workspace_id": "guild-logs",
            "workspace_name": "Logs Guild",
            "channel_id": "channel-logs",
            "channel_name": "logs-room",
            "thread_id": "",
            "thread_name": "",
            "participation_mode": "mention_and_reply",
            "memory_scope": "channel_isolated",
            "version_label": "Current",
            "sticker_count": 0,
            "status": "active",
        },
    ).json()
    identity = client.put(
        f"/api/deployment-identities/{deployment['id']}",
        json={
            "mode": "webhook",
            "display_name": "Ann",
            "avatar_url": None,
            "address_aliases": ["Ann"],
        },
    )
    assert identity.status_code == 200, identity.text
    assert identity.json()["webhook_status"] == "pending"
    assert deployment["status"] == "active"

    headers = {"Authorization": f"Bearer {CONNECTOR_SECRET}"}
    synced = client.get(
        "/api/connectors/discord/deployments",
        params={"connection_id": connection["id"]},
        headers=headers,
    )
    assert synced.status_code == 200, synced.text

    async def respond(_payload: object) -> DiscordConnectorReplyView:
        return DiscordConnectorReplyView(
            action="reply",
            reason="model_reply",
            deployment_id=deployment["id"],
            character_display_name="Ann",
            text="A safe generated reply.",
            reply_to_message_id="message-logs",
            latency_ms=42,
            input_tokens=12,
            output_tokens=8,
        )

    app.state.discord_connector_runtime.respond = respond
    private_text = "PRIVATE MESSAGE CONTENT MUST NOT BE STORED"
    processed = client.post(
        "/api/connectors/discord/messages",
        headers=headers,
        json={
            "connection_id": connection["id"],
            "deployment_id": deployment["id"],
            "message_id": "message-logs",
            "guild_id": "guild-logs",
            "guild_name": "Logs Guild",
            "channel_id": "channel-logs",
            "channel_name": "logs-room",
            "category_id": "",
            "thread_id": "",
            "thread_name": "",
            "author_id": "user-logs",
            "author_display_name": "Tester",
            "text": private_text,
            "mentioned_bot": True,
            "replied_to_bot": False,
            "smart_candidate": False,
            "author_is_bot": False,
            "stickers": [],
            "available_characters": [],
            "recent_messages": [],
            "interaction_session_id": "",
            "interaction_type": "",
            "interaction_intensity": "",
            "interaction_round": 0,
            "interaction_total_rounds": 0,
            "interaction_position": 0,
            "interaction_participant_count": 0,
            "interaction_target_user_id": "",
            "interaction_target_display_name": "",
        },
    )
    assert processed.status_code == 200, processed.text

    response = client.get(
        "/api/deployment-logs",
        params={
            "connection_id": connection["id"],
            "deployment_id": deployment["id"],
            "limit": 100,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    event_types = {item["event_type"] for item in payload}
    assert "deployment_sync" in event_types
    assert "runtime_message_received" in event_types
    assert "runtime_reply" in event_types
    assert private_text not in response.text
