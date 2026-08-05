from pathlib import Path

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr

from echo_masque.api import create_app
from echo_masque.config import Settings

ADMIN_EMAIL = "server-workspace@example.com"
ADMIN_PASSWORD = "ServerWorkspace2026!"
SECRET = "server-workspace-connector-secret"


def settings(path: Path) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{path}",
        legacy_local_user_enabled=False,
        bootstrap_admin_email=ADMIN_EMAIL,
        bootstrap_admin_password=SecretStr(ADMIN_PASSWORD),
        bootstrap_admin_display_name="Server Workspace Admin",
        credential_encryption_keys=SecretStr(Fernet.generate_key().decode("ascii")),
        connector_shared_secret=SecretStr(SECRET),
    )


def login(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200, response.text


def connector_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {SECRET}"}


def create_character(client: TestClient, name: str) -> dict[str, object]:
    response = client.post(
        "/api/characters",
        json={
            "target_id": "demo-stable",
            "display_name": name,
            "subtitle": "Server workspace fixture",
            "subject_type": "companion",
            "persona_summary": f"{name} is concise.",
            "traits": ["witty"],
            "tags": ["discord"],
            "expected_tone": "Concise.",
            "forbidden_behaviors": ["invent memories"],
            "memory_summary": "Use supplied context.",
            "preferred_suites": ["identity_integrity"],
            "portrait_variant": "lavender",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def seed_server(
    client: TestClient,
) -> tuple[dict[str, object], dict[str, object], list[dict[str, object]]]:
    login(client)
    connection = client.post(
        "/api/connections",
        json={
            "platform": "discord",
            "display_name": "Managed Discord",
            "connection_mode": "managed",
            "external_account_id": "bot-1",
            "status": "connected",
            "metadata": {},
        },
    ).json()
    catalog = client.put(
        "/api/connectors/discord/server-catalog",
        headers=connector_headers(),
        json={
            "connection_id": connection["id"],
            "servers": [
                {
                    "guild_id": "guild-1",
                    "guild_name": "Guild One",
                    "channels": [
                        {
                            "id": "channel-1",
                            "name": "general",
                            "category_id": "category-1",
                            "category_name": "Community",
                            "type": "text",
                        }
                    ],
                    "stickers": [
                        {
                            "sticker_id": "sticker-1",
                            "name": "side_eye_cat",
                            "description": "A doubtful cat",
                            "tags": ["doubt"],
                            "format_type": "png",
                            "asset_url": "https://cdn.discordapp.com/stickers/sticker-1.png",
                        }
                    ],
                }
            ],
        },
    )
    assert catalog.status_code == 204, catalog.text
    profile_response = client.post(
        "/api/discord/server-profiles",
        json={
            "connection_id": connection["id"],
            "name": "Guild One",
            "guild_id": "guild-1",
            "guild_name": "Guild One",
            "excluded_channel_ids": [],
            "excluded_category_ids": [],
            "thread_policy": "inherit_parent",
        },
    )
    assert profile_response.status_code == 201, profile_response.text
    profile = profile_response.json()
    deployments: list[dict[str, object]] = []
    for name in ("Ann", "Ning"):
        character = create_character(client, name)
        deployment = client.post(
            "/api/deployments",
            json={
                "character_card_id": character["id"],
                "connection_id": connection["id"],
                "server_profile_id": profile["id"],
                "workspace_id": "",
                "workspace_name": "",
                "channel_id": "",
                "channel_name": "",
                "thread_id": "",
                "thread_name": "",
                "excluded_channel_ids": [],
                "excluded_category_ids": [],
                "participation_mode": "mention_and_reply",
                "memory_scope": "channel_isolated",
                "version_label": "Current",
                "sticker_count": 0,
                "status": "active",
            },
        )
        assert deployment.status_code == 201, deployment.text
        deployments.append(deployment.json())
    return connection, profile, deployments


def test_server_scoped_templates_apply_and_deployments_filter(tmp_path: Path) -> None:
    client = TestClient(create_app(settings(tmp_path / "server-workspace.db")))
    connection, profile, deployments = seed_server(client)
    template = client.post(
        "/api/interaction-templates",
        json={
            "server_profile_id": profile["id"],
            "name": "Ann and Ning roast",
            "participant_character_card_ids": [
                deployments[0]["character_card_id"],
                deployments[1]["character_card_id"],
            ],
            "rounds_per_trigger": 2,
            "maximum_triggers": 3,
            "cooldown_seconds": 30,
            "duration_seconds": 600,
            "intensity": "playful",
        },
    )
    assert template.status_code == 201, template.text
    assert template.json()["maximum_replies_per_trigger"] == 4

    applied = client.post(
        f"/api/interaction-templates/{template.json()['id']}/apply",
        json={
            "channel_id": "channel-1",
            "target_user_id": "user-1",
            "target_display_name": "Target",
            "status": "active",
        },
    )
    assert applied.status_code == 201, applied.text
    assert applied.json()["participant_deployment_ids"] == [
        deployments[0]["id"],
        deployments[1]["id"],
    ]
    assert applied.json()["guild_id"] == "guild-1"
    assert applied.json()["channel_name"] == "general"

    filtered = client.get(
        "/api/deployments/page",
        params={"server_profile_id": profile["id"], "page": 1, "page_size": 20},
    )
    assert filtered.status_code == 200, filtered.text
    assert filtered.json()["total"] == 2
    assert filtered.json()["active"] == 2

    sessions = client.get(
        "/api/interaction-sessions",
        params={"connection_id": connection["id"], "guild_id": "guild-1"},
    )
    assert sessions.status_code == 200
    assert len(sessions.json()) == 1


def test_guild_sticker_catalog_populates_dictionary_without_message(tmp_path: Path) -> None:
    client = TestClient(create_app(settings(tmp_path / "sticker-catalog.db")))
    connection, _, _ = seed_server(client)
    stickers = client.get(
        "/api/discord/sticker-dictionary",
        params={"connection_id": connection["id"], "guild_id": "guild-1"},
    )
    assert stickers.status_code == 200, stickers.text
    assert len(stickers.json()) == 1
    assert stickers.json()[0]["name"] == "side_eye_cat"
    assert stickers.json()[0]["semantic_source"] == "discord_metadata"
