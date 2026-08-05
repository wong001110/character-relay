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


def create_character(client: TestClient, name: str) -> dict[str, object]:
    response = client.post(
        "/api/characters",
        json={
            "target_id": "demo-stable",
            "display_name": name,
            "subtitle": "Discord connector fixture",
            "subject_type": "companion",
            "persona_summary": f"{name} is a calm social character.",
            "traits": ["calm"],
            "tags": ["discord"],
            "expected_tone": "Concise and gentle.",
            "forbidden_behaviors": ["invent private memories"],
            "memory_summary": "Use only supplied Discord context.",
            "preferred_suites": ["identity_integrity"],
            "portrait_variant": "lavender",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_connection(client: TestClient) -> dict[str, object]:
    response = client.post(
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
    assert response.status_code == 201, response.text
    return response.json()


def create_deployment(
    client: TestClient,
    *,
    connection: dict[str, object],
    character: dict[str, object],
    channel_id: str = "channel-001",
    channel_name: str = "companions",
) -> dict[str, object]:
    response = client.post(
        "/api/deployments",
        json={
            "character_card_id": character["id"],
            "connection_id": connection["id"],
            "workspace_id": "guild-001",
            "workspace_name": "Test Guild",
            "channel_id": channel_id,
            "channel_name": channel_name,
            "thread_id": "",
            "thread_name": "",
            "participation_mode": "mention_and_reply",
            "memory_scope": "channel_isolated",
            "version_label": "Current",
            "sticker_count": 0,
            "status": "active",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def seed_deployment(client: TestClient) -> tuple[dict[str, object], dict[str, object]]:
    login(client)
    character = create_character(client, "Ann")
    connection = create_connection(client)
    return connection, create_deployment(
        client,
        connection=connection,
        character=character,
    )


def expected_connector_deployment(
    connection: dict[str, object],
    deployment: dict[str, object],
    *,
    character_name: str = "Ann",
    webhook_status: str = "pending",
    webhook_id: str | None = None,
    webhook_token: str | None = None,
    identity_name: str | None = None,
    avatar_url: str = "",
    address_aliases: list[str] | None = None,
) -> dict[str, object]:
    return {
        "deployment_id": deployment["id"],
        "connection_id": connection["id"],
        "character_card_id": deployment["character_card_id"],
        "character_display_name": character_name,
        "workspace_id": "guild-001",
        "workspace_name": "Test Guild",
        "channel_id": "channel-001",
        "channel_name": "companions",
        "thread_id": "",
        "thread_name": "",
        "category_id": "",
        "server_profile_id": "",
        "channel_scope_mode": "exact",
        "excluded_channel_ids": [],
        "excluded_category_ids": [],
        "participation_mode": "mention_and_reply",
        "version_label": "Current",
        "status": "active",
        "identity_mode": "webhook",
        "identity_display_name": identity_name or character_name,
        "identity_avatar_url": avatar_url,
        "address_aliases": address_aliases or [],
        "webhook_status": webhook_status,
        "webhook_id": webhook_id,
        "webhook_token": webhook_token,
    }


def inbound_payload(
    connection: dict[str, object],
    deployment: dict[str, object],
    *,
    message_id: str,
    text: str,
    mentioned_bot: bool,
    replied_to_bot: bool = False,
    channel_id: str = "channel-001",
    channel_name: str = "companions",
    category_id: str = "",
) -> dict[str, object]:
    return {
        "connection_id": connection["id"],
        "deployment_id": deployment["id"],
        "message_id": message_id,
        "guild_id": "guild-001",
        "guild_name": "Test Guild",
        "channel_id": channel_id,
        "channel_name": channel_name,
        "category_id": category_id,
        "thread_id": "",
        "thread_name": "",
        "author_id": "user-001",
        "author_display_name": "Juen",
        "text": text,
        "mentioned_bot": mentioned_bot,
        "replied_to_bot": replied_to_bot,
        "smart_candidate": False,
        "recent_messages": [
            {
                "message_id": message_id,
                "author_id": "user-001",
                "author_display_name": "Juen",
                "text": text,
                "is_bot": False,
            }
        ],
    }


def test_connector_requires_shared_secret(tmp_path: Path) -> None:
    client = TestClient(create_app(settings(tmp_path / "discord-auth.db")))
    response = client.get(
        "/api/connectors/discord/deployments",
        params={"connection_id": "missing"},
        headers=connector_headers("wrong-secret"),
    )
    assert response.status_code == 401


def test_discord_webhook_identity_is_editable_and_encrypted(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "discord-webhook.db"))
    client = TestClient(app)
    connection, deployment = seed_deployment(client)

    updated_identity = client.put(
        f"/api/deployment-identities/{deployment['id']}",
        json={
            "mode": "webhook",
            "display_name": "Ann in Discord",
            "avatar_url": "https://example.com/ann.png",
            "address_aliases": ["安", "Ann"],
        },
    )
    assert updated_identity.status_code == 200, updated_identity.text
    assert updated_identity.json()["webhook_status"] == "pending"

    registration = client.put(
        "/api/connectors/discord/webhooks",
        headers=connector_headers(),
        json={
            "connection_id": connection["id"],
            "deployment_id": deployment["id"],
            "workspace_id": "guild-001",
            "channel_id": "channel-001",
            "webhook_id": "webhook-001",
            "webhook_token": "super-secret-webhook-token",
        },
    )
    assert registration.status_code == 200, registration.text
    assert registration.json()["webhook_token"] == "super-secret-webhook-token"

    listing = client.get(
        "/api/connectors/discord/deployments",
        params={"connection_id": connection["id"]},
        headers=connector_headers(),
    )
    assert listing.status_code == 200, listing.text
    assert listing.json() == [
        expected_connector_deployment(
            connection,
            deployment,
            webhook_status="active",
            webhook_id="webhook-001",
            webhook_token="super-secret-webhook-token",
            identity_name="Ann in Discord",
            avatar_url="https://example.com/ann.png",
            address_aliases=["安", "Ann"],
        )
    ]

    public_identities = client.get("/api/deployment-identities")
    assert public_identities.status_code == 200
    public_payload = public_identities.json()[0]
    assert public_payload["display_name"] == "Ann in Discord"
    assert public_payload["address_aliases"] == ["安", "Ann"]
    assert "webhook_token" not in public_payload

    credentials = app.state.auth_repository.list_credentials()
    webhook_credentials = [item for item in credentials if item.scope_kind == "discord_webhook"]
    assert len(webhook_credentials) == 1
    assert "super-secret-webhook-token" not in webhook_credentials[0].encrypted_value


def test_discord_connector_lists_routes_heartbeats_and_replies(tmp_path: Path) -> None:
    client = TestClient(create_app(settings(tmp_path / "discord-connector.db")))
    connection, deployment = seed_deployment(client)

    listing = client.get(
        "/api/connectors/discord/deployments",
        params={"connection_id": connection["id"]},
        headers=connector_headers(),
    )
    assert listing.status_code == 200, listing.text
    assert listing.json() == [expected_connector_deployment(connection, deployment)]

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
        json=inbound_payload(
            connection,
            deployment,
            message_id="message-001",
            text="The group is talking without addressing Ann.",
            mentioned_bot=False,
        ),
    )
    assert silent.status_code == 200, silent.text
    assert silent.json()["action"] == "silent"
    assert silent.json()["reason"] == "trigger_not_matched"

    reply = client.post(
        "/api/connectors/discord/messages",
        headers=connector_headers(),
        json=inbound_payload(
            connection,
            deployment,
            message_id="message-002",
            text="what do you think?",
            mentioned_bot=True,
        ),
    )
    assert reply.status_code == 200, reply.text
    payload = reply.json()
    assert payload["action"] == "reply"
    assert payload["deployment_id"] == deployment["id"]
    assert payload["character_display_name"] == "Ann"
    assert payload["reply_to_message_id"] == "message-002"
    assert payload["text"]


def test_server_profile_defaults_to_all_channels_and_applies_exclusions(
    tmp_path: Path,
) -> None:
    client = TestClient(create_app(settings(tmp_path / "discord-server-profile.db")))
    login(client)
    character = create_character(client, "Ann")
    connection = create_connection(client)

    synced = client.put(
        "/api/connectors/discord/server-catalog",
        headers=connector_headers(),
        json={
            "connection_id": connection["id"],
            "servers": [
                {
                    "guild_id": "guild-001",
                    "guild_name": "Test Guild",
                    "channels": [
                        {
                            "id": "channel-general",
                            "name": "general",
                            "category_id": "public-category",
                            "category_name": "PUBLIC",
                            "type": "text",
                        },
                        {
                            "id": "channel-design",
                            "name": "design",
                            "category_id": "public-category",
                            "category_name": "PUBLIC",
                            "type": "text",
                        },
                        {
                            "id": "channel-admin",
                            "name": "admin",
                            "category_id": "staff-category",
                            "category_name": "STAFF",
                            "type": "text",
                        },
                    ],
                }
            ],
        },
    )
    assert synced.status_code == 204, synced.text

    catalog = client.get(
        "/api/discord/server-catalog",
        params={"connection_id": connection["id"]},
    )
    assert catalog.status_code == 200, catalog.text
    assert catalog.json()[0]["guild_name"] == "Test Guild"
    assert len(catalog.json()[0]["channels"]) == 3

    profile_response = client.post(
        "/api/discord/server-profiles",
        json={
            "connection_id": connection["id"],
            "name": "Private Companion Server",
            "guild_id": "guild-001",
            "guild_name": "Test Guild",
            "excluded_channel_ids": ["channel-admin"],
            "excluded_category_ids": ["staff-category"],
            "thread_policy": "inherit_parent",
        },
    )
    assert profile_response.status_code == 201, profile_response.text
    profile = profile_response.json()

    deployment_response = client.post(
        "/api/deployments",
        json={
            "character_card_id": character["id"],
            "connection_id": connection["id"],
            "server_profile_id": profile["id"],
            "excluded_channel_ids": ["channel-design"],
            "excluded_category_ids": [],
            "participation_mode": "mention_and_reply",
            "memory_scope": "server_shared",
            "version_label": "Current",
            "sticker_count": 0,
            "status": "active",
        },
    )
    assert deployment_response.status_code == 201, deployment_response.text
    deployment = deployment_response.json()
    assert deployment["channel_scope_mode"] == "all_except"
    assert deployment["server_profile_id"] == profile["id"]
    assert deployment["workspace_id"] == "guild-001"
    assert deployment["channel_id"] == f"@server:{profile['id']}"
    assert deployment["excluded_channel_ids"] == ["channel-design"]

    connector_listing = client.get(
        "/api/connectors/discord/deployments",
        params={"connection_id": connection["id"]},
        headers=connector_headers(),
    )
    assert connector_listing.status_code == 200, connector_listing.text
    connector_deployment = connector_listing.json()[0]
    assert connector_deployment["channel_scope_mode"] == "all_except"
    assert set(connector_deployment["excluded_channel_ids"]) == {
        "channel-admin",
        "channel-design",
    }
    assert connector_deployment["excluded_category_ids"] == ["staff-category"]

    allowed = client.post(
        "/api/connectors/discord/messages",
        headers=connector_headers(),
        json=inbound_payload(
            connection,
            deployment,
            message_id="server-message-allowed",
            text="Ann, are you there?",
            mentioned_bot=True,
            channel_id="channel-general",
            channel_name="general",
            category_id="public-category",
        ),
    )
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["action"] == "reply"

    excluded = client.post(
        "/api/connectors/discord/messages",
        headers=connector_headers(),
        json=inbound_payload(
            connection,
            deployment,
            message_id="server-message-excluded",
            text="Ann, are you there?",
            mentioned_bot=True,
            channel_id="channel-design",
            channel_name="design",
            category_id="public-category",
        ),
    )
    assert excluded.status_code == 200, excluded.text
    assert excluded.json()["action"] == "silent"
    assert excluded.json()["reason"] == "no_active_deployment"

    delete_in_use = client.delete(f"/api/discord/server-profiles/{profile['id']}")
    assert delete_in_use.status_code == 409


def test_same_channel_characters_are_selected_by_exact_deployment_id(
    tmp_path: Path,
) -> None:
    client = TestClient(create_app(settings(tmp_path / "discord-multi.db")))
    connection, ann_deployment = seed_deployment(client)
    ning = create_character(client, "宁")
    ning_deployment = create_deployment(
        client,
        connection=connection,
        character=ning,
    )

    listing = client.get(
        "/api/connectors/discord/deployments",
        params={"connection_id": connection["id"]},
        headers=connector_headers(),
    )
    assert listing.status_code == 200, listing.text
    assert {item["character_display_name"] for item in listing.json()} == {"Ann", "宁"}

    response = client.post(
        "/api/connectors/discord/messages",
        headers=connector_headers(),
        json=inbound_payload(
            connection,
            ning_deployment,
            message_id="message-ning",
            text="你怎么看?",
            mentioned_bot=True,
        ),
    )
    assert response.status_code == 200, response.text
    assert response.json()["deployment_id"] == ning_deployment["id"]
    assert response.json()["character_display_name"] == "宁"
    assert response.json()["deployment_id"] != ann_deployment["id"]


def test_discord_message_route_persists_reply_character_ownership(tmp_path: Path) -> None:
    client = TestClient(create_app(settings(tmp_path / "discord-routes.db")))
    connection, deployment = seed_deployment(client)

    registered = client.put(
        "/api/connectors/discord/message-routes",
        headers=connector_headers(),
        json={
            "connection_id": connection["id"],
            "deployment_id": deployment["id"],
            "guild_id": "guild-001",
            "channel_id": "channel-001",
            "thread_id": "",
            "webhook_id": "webhook-001",
            "message_ids": ["discord-message-001", "discord-message-002"],
        },
    )
    assert registered.status_code == 204, registered.text

    lookup = client.get(
        "/api/connectors/discord/message-routes",
        headers=connector_headers(),
        params={
            "connection_id": connection["id"],
            "message_id": "discord-message-002",
        },
    )
    assert lookup.status_code == 200, lookup.text
    assert lookup.json() == {
        "route": {
            "message_id": "discord-message-002",
            "deployment_id": deployment["id"],
            "character_card_id": deployment["character_card_id"],
            "channel_id": "channel-001",
            "thread_id": "",
        }
    }

    missing = client.get(
        "/api/connectors/discord/message-routes",
        headers=connector_headers(),
        params={
            "connection_id": connection["id"],
            "message_id": "unknown-message",
        },
    )
    assert missing.status_code == 200
    assert missing.json() == {"route": None}



def test_connector_heartbeat_persists_runtime_diagnostics(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "discord-heartbeat-diagnostics.db"))
    client = TestClient(app)
    login(client)
    connection = create_connection(client)

    response = client.post(
        "/api/connectors/discord/heartbeat",
        headers=connector_headers(),
        json={
            "connection_id": connection["id"],
            "bot_user_id": "bot-123",
            "bot_display_name": "CharacterRelayBot#0001",
            "status": "connected",
            "last_error": "",
            "replica_region": "asia-southeast1-eqsg3a",
            "gateway_ready": True,
            "state_synchronized": True,
            "visible_server_count": 2,
        },
    )
    assert response.status_code == 204, response.text

    listed = client.get("/api/connections")
    assert listed.status_code == 200, listed.text
    updated = listed.json()[0]
    assert updated["status"] == "connected"
    assert updated["last_seen_at"] is not None
    assert updated["external_account_id"] == "bot-123"
    assert updated["metadata"]["connector_display_name"] == "CharacterRelayBot#0001"
    assert updated["metadata"]["replica_region"] == "asia-southeast1-eqsg3a"
    assert updated["metadata"]["gateway_ready"] is True
    assert updated["metadata"]["state_synchronized"] is True
    assert updated["metadata"]["visible_server_count"] == 2
