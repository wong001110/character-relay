from pathlib import Path

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr

from echo_masque.api import create_app
from echo_masque.config import Settings

SUPER_EMAIL = "super@example.com"
SUPER_PASSWORD = "SuperAdminPassword2026!"
USER_PASSWORD = "ClaimingUserPassword2026!"


def settings(path: Path) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{path}",
        legacy_local_user_enabled=False,
        public_registration_enabled=True,
        bootstrap_admin_email=SUPER_EMAIL,
        bootstrap_admin_password=SecretStr(SUPER_PASSWORD),
        bootstrap_admin_display_name="Super Admin",
        credential_encryption_keys=SecretStr(Fernet.generate_key().decode("ascii")),
    )


def login(client: TestClient, email: str, password: str) -> None:
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text


def create_character(client: TestClient) -> dict[str, object]:
    response = client.post(
        "/api/characters/prompt-model",
        json={
            "display_name": "Claimed Character",
            "subtitle": "Shared Bot deployment test",
            "subject_type": "companion",
            "persona_summary": "A character owned by the claiming account.",
            "traits": ["calm"],
            "tags": ["claim"],
            "expected_tone": "Concise.",
            "forbidden_behaviors": ["Invent private facts"],
            "memory_summary": "Remember only confirmed details.",
            "preferred_suites": ["identity_integrity"],
            "portrait_variant": "lavender",
            "provider": "deepseek",
            "base_url": "https://api.deepseek.com",
            "model": "deepseek-v4-flash",
            "system_prompt": "You are a claimed character.",
            "temperature": 0.4,
            "api_key": "test-key",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_user_claims_exact_superadmin_server_without_catalog_leak(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "claims.db"))
    super_client = TestClient(app)
    login(super_client, SUPER_EMAIL, SUPER_PASSWORD)

    connection_response = super_client.post(
        "/api/connections",
        json={
            "platform": "discord",
            "display_name": "Managed Discord Bot",
            "connection_mode": "managed",
            "external_account_id": "bot-1",
            "status": "connected",
            "metadata": {},
        },
    )
    assert connection_response.status_code == 201, connection_response.text
    connection_id = connection_response.json()["id"]

    app.state.deployment_repository.sync_discord_server_catalog(
        connection_id=connection_id,
        servers=[
            (
                "111111111111111111",
                "Claimed Guild",
                [
                    {
                        "id": "333333333333333333",
                        "name": "general",
                        "category_id": "",
                        "category_name": "",
                        "type": "text",
                    }
                ],
            ),
            ("222222222222222222", "Hidden Guild", []),
        ],
    )
    app.state.expression_repository.sync_server_resources(
        connection_id=connection_id,
        guild_id="111111111111111111",
        emojis=[
            {
                "emoji_id": "444444444444444444",
                "name": "peek",
                "description": "curious peek",
                "tags": ["curious"],
                "format_type": "emoji",
                "asset_url": "https://cdn.example/peek.png",
                "animated": False,
                "available": True,
            }
        ],
        stickers=[],
    )

    app.state.auth_service.register(
        email="user@example.com",
        display_name="Claiming User",
        password=USER_PASSWORD,
    )
    user_client = TestClient(app)
    login(user_client, "user@example.com", USER_PASSWORD)

    assert user_client.get("/api/discord/server-catalog").json() == []
    assert user_client.get("/api/connections").json() == []

    claim = user_client.post(
        "/api/discord/server-profiles/claim",
        json={
            "guild_id": "111111111111111111",
            "name": "My Character Server",
        },
    )
    assert claim.status_code == 201, claim.text
    profile = claim.json()
    assert profile["guild_name"] == "Claimed Guild"
    assert profile["name"] == "My Character Server"

    catalog = user_client.get("/api/discord/server-catalog")
    assert catalog.status_code == 200
    assert [item["guild_id"] for item in catalog.json()] == ["111111111111111111"]

    connections = user_client.get("/api/connections").json()
    assert len(connections) == 1
    assert connections[0]["id"] == connection_id
    assert connections[0]["external_account_id"] == ""
    assert connections[0]["metadata"]["shared_connection"] is True

    expressions = user_client.get(
        "/api/discord/expression-dictionary",
        params={
            "connection_id": connection_id,
            "guild_id": "111111111111111111",
        },
    )
    assert expressions.status_code == 200, expressions.text
    assert [item["name"] for item in expressions.json()] == ["peek"]

    character = create_character(user_client)
    deployment = user_client.post(
        "/api/deployments",
        json={
            "character_card_id": character["id"],
            "connection_id": connection_id,
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
            "status": "paused",
        },
    )
    assert deployment.status_code == 201, deployment.text
    assert deployment.json()["server_profile_id"] == profile["id"]

    app.state.auth_service.register(
        email="other@example.com",
        display_name="Other User",
        password=USER_PASSWORD,
    )
    other_client = TestClient(app)
    login(other_client, "other@example.com", USER_PASSWORD)
    duplicate_claim = other_client.post(
        "/api/discord/server-profiles/claim",
        json={"guild_id": "111111111111111111", "name": "Other"},
    )
    assert duplicate_claim.status_code == 409
