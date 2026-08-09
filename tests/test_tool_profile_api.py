from pathlib import Path

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr

from echo_masque.api import create_app
from echo_masque.config import Settings

ADMIN_EMAIL = "tool-admin@example.com"
ADMIN_PASSWORD = "CharacterRelayTools2026!"


def settings(path: Path) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{path}",
        legacy_local_user_enabled=False,
        bootstrap_admin_email=ADMIN_EMAIL,
        bootstrap_admin_password=SecretStr(ADMIN_PASSWORD),
        bootstrap_admin_display_name="Tool Admin",
        credential_encryption_keys=SecretStr(Fernet.generate_key().decode("ascii")),
    )


def login(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200, response.text


def create_deployment(client: TestClient) -> str:
    character = client.post(
        "/api/characters/prompt-model",
        json={
            "display_name": "Tool Tester",
            "subtitle": "Utility tool test character",
            "subject_type": "assistant",
            "persona_summary": "Uses assigned tools only when useful.",
            "traits": ["precise"],
            "tags": ["tools"],
            "expected_tone": "Concise.",
            "forbidden_behaviors": [],
            "memory_summary": None,
            "preferred_suites": ["identity_integrity"],
            "portrait_variant": "mint",
            "provider": "deepseek",
            "base_url": "https://api.deepseek.com",
            "model": "deepseek-v4-flash",
            "system_prompt": "You are a precise tool test character.",
            "temperature": 0.2,
            "api_key": "test-provider-key",
        },
    )
    assert character.status_code == 201, character.text
    connection = client.post(
        "/api/connections",
        json={
            "platform": "discord",
            "display_name": "Tool Discord",
            "connection_mode": "managed",
            "external_account_id": "tool-bot",
            "status": "connected",
            "metadata": {},
        },
    )
    assert connection.status_code == 201, connection.text
    deployment = client.post(
        "/api/deployments",
        json={
            "character_card_id": character.json()["id"],
            "connection_id": connection.json()["id"],
            "server_profile_id": "",
            "workspace_id": "guild-tools",
            "workspace_name": "Tool Guild",
            "channel_id": "channel-tools",
            "channel_name": "tool-room",
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
    return str(deployment.json()["id"])


def test_tool_catalog_and_manual_deployment_assignment(tmp_path: Path) -> None:
    client = TestClient(create_app(settings(tmp_path / "tools.db")))
    login(client)
    deployment_id = create_deployment(client)

    catalog = client.get("/api/tools/catalog")
    assert catalog.status_code == 200, catalog.text
    items = {item["id"]: item for item in catalog.json()["items"]}
    assert set(items) == {
        "utility.calculator",
        "utility.current_time",
        "web.search",
        "web.fetch_page",
        "discord.search_messages",
        "discord.create_poll",
        "weather.get",
        "random.roll",
        "random.choose",
        "image.search",
        "scheduler.remind",
        "scheduler.list",
        "scheduler.cancel",
        "places.search",
        "file.inspect",
        "watch.condition",
    }
    for tool_id in (
        "utility.calculator",
        "utility.current_time",
        "web.search",
        "web.fetch_page",
        "weather.get",
        "random.roll",
        "random.choose",
        "image.search",
        "scheduler.remind",
        "scheduler.list",
        "scheduler.cancel",
        "places.search",
        "file.inspect",
        "watch.condition",
    ):
        assert items[tool_id]["available"] is True
    assert items["discord.search_messages"]["available"] is False
    assert items["discord.create_poll"]["available"] is False

    initial = client.get(f"/api/deployments/{deployment_id}/tools")
    assert initial.status_code == 200, initial.text
    assert initial.json()["enabled_tools"] == []

    enabled = [
        "utility.calculator",
        "web.search",
        "weather.get",
        "random.choose",
        "scheduler.remind",
        "places.search",
        "file.inspect",
        "watch.condition",
    ]
    saved = client.put(
        f"/api/deployments/{deployment_id}/tools",
        json={"enabled_tools": enabled},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["enabled_tools"] == enabled

    reread = client.get(f"/api/deployments/{deployment_id}/tools")
    assert reread.status_code == 200, reread.text
    assert reread.json() == saved.json()

    unavailable = client.put(
        f"/api/deployments/{deployment_id}/tools",
        json={"enabled_tools": ["discord.search_messages"]},
    )
    assert unavailable.status_code == 422, unavailable.text
    assert "DISCORD_TOOL_BOT_TOKEN" in unavailable.text

    unknown = client.put(
        f"/api/deployments/{deployment_id}/tools",
        json={"enabled_tools": ["unknown.tool"]},
    )
    assert unknown.status_code == 422, unknown.text
