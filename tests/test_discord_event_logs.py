from pathlib import Path

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr

from echo_masque.api import create_app
from echo_masque.config import Settings

ADMIN_EMAIL = "discord-logs-admin@example.com"
ADMIN_PASSWORD = "DiscordLogsAdmin2026!"
CONNECTOR_SECRET = "discord-event-log-secret"


def settings(path: Path) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{path}",
        legacy_local_user_enabled=False,
        bootstrap_admin_email=ADMIN_EMAIL,
        bootstrap_admin_password=SecretStr(ADMIN_PASSWORD),
        bootstrap_admin_display_name="Discord Logs Admin",
        credential_encryption_keys=SecretStr(Fernet.generate_key().decode("ascii")),
        connector_shared_secret=SecretStr(CONNECTOR_SECRET),
    )


def login(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200, response.text


def connector_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {CONNECTOR_SECRET}"}


def create_connection(client: TestClient) -> dict[str, object]:
    response = client.post(
        "/api/connections",
        json={
            "platform": "discord",
            "display_name": "Discord Connector",
            "connection_mode": "managed",
            "external_account_id": "bot-1",
            "status": "connected",
            "metadata": {},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_profile(
    client: TestClient,
    connection_id: str,
    guild_id: str,
    guild_name: str,
) -> dict[str, object]:
    response = client.post(
        "/api/discord/server-profiles",
        json={
            "connection_id": connection_id,
            "name": f"{guild_name} Profile",
            "guild_id": guild_id,
            "guild_name": guild_name,
            "excluded_channel_ids": [],
            "excluded_category_ids": [],
            "thread_policy": "inherit_parent",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def event(event_id: str, guild_id: str, guild_name: str, event_type: str) -> dict[str, object]:
    return {
        "id": event_id,
        "occurred_at": "2026-08-05T12:00:00Z",
        "level": "info",
        "event_type": event_type,
        "message": "Bot mention reached the Discord Gateway.",
        "guild_id": guild_id,
        "guild_name": guild_name,
        "channel_id": f"channel-{guild_id}",
        "channel_name": "general",
        "thread_id": "",
        "thread_name": "",
        "source_message_id": f"message-{event_id}",
        "deployment_id": "",
        "character_name": "",
        "details": {"mentioned_bot": True, "has_readable_text": True},
    }


def test_owner_can_filter_discord_events_by_server_profile(tmp_path: Path) -> None:
    client = TestClient(create_app(settings(tmp_path / "discord-events.db")))
    login(client)
    connection = create_connection(client)
    first = create_profile(client, str(connection["id"]), "guild-a", "Guild A")
    second = create_profile(client, str(connection["id"]), "guild-b", "Guild B")

    response = client.post(
        "/api/connectors/discord/events",
        headers=connector_headers(),
        json={
            "connection_id": connection["id"],
            "events": [
                event("event-a", "guild-a", "Guild A", "mention_received"),
                event("event-b", "guild-b", "Guild B", "ignored_no_deployment"),
            ],
        },
    )
    assert response.status_code == 204, response.text

    filtered = client.get(
        "/api/discord/logs",
        params={"server_profile_id": first["id"], "page_size": 50},
    )
    assert filtered.status_code == 200, filtered.text
    payload = filtered.json()
    assert payload["total"] == 1
    assert payload["items"][0]["guild_id"] == "guild-a"
    assert payload["items"][0]["event_type"] == "mention_received"

    other = client.get(
        "/api/discord/logs",
        params={"server_profile_id": second["id"], "event_type": "mention_received"},
    )
    assert other.status_code == 200, other.text
    assert other.json()["total"] == 0

    duplicate = client.post(
        "/api/connectors/discord/events",
        headers=connector_headers(),
        json={
            "connection_id": connection["id"],
            "events": [event("event-a", "guild-a", "Guild A", "mention_received")],
        },
    )
    assert duplicate.status_code == 204, duplicate.text
    all_events = client.get("/api/discord/logs", params={"page_size": 50})
    assert all_events.status_code == 200, all_events.text
    assert all_events.json()["total"] == 2


def test_connector_event_schema_rejects_message_content(tmp_path: Path) -> None:
    client = TestClient(create_app(settings(tmp_path / "discord-event-privacy.db")))
    login(client)
    connection = create_connection(client)
    unsafe = event("event-private", "guild-a", "Guild A", "mention_received")
    unsafe["text"] = "PRIVATE DISCORD MESSAGE CONTENT"

    response = client.post(
        "/api/connectors/discord/events",
        headers=connector_headers(),
        json={"connection_id": connection["id"], "events": [unsafe]},
    )
    assert response.status_code == 422, response.text
