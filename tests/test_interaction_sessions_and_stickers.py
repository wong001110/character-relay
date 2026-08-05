from pathlib import Path

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr

from echo_masque.api import create_app
from echo_masque.api.connector_schemas import DiscordContextMessage, DiscordInboundMessage
from echo_masque.config import Settings
from echo_masque.connector_runtime import DiscordConnectorRuntime

ADMIN_EMAIL = "interaction-admin@example.com"
ADMIN_PASSWORD = "InteractionAdmin2026!"
CONNECTOR_SECRET = "interaction-connector-secret"


def settings(path: Path) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{path}",
        legacy_local_user_enabled=False,
        bootstrap_admin_email=ADMIN_EMAIL,
        bootstrap_admin_password=SecretStr(ADMIN_PASSWORD),
        bootstrap_admin_display_name="Interaction Admin",
        credential_encryption_keys=SecretStr(Fernet.generate_key().decode("ascii")),
        connector_shared_secret=SecretStr(CONNECTOR_SECRET),
    )


def login(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200, response.text


def headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {CONNECTOR_SECRET}"}


def create_character(client: TestClient, name: str) -> dict[str, object]:
    response = client.post(
        "/api/characters",
        json={
            "target_id": "demo-stable",
            "display_name": name,
            "subtitle": "Interaction fixture",
            "subject_type": "companion",
            "persona_summary": f"{name} uses concise dry humor.",
            "traits": ["witty"],
            "tags": ["discord"],
            "expected_tone": "Playful and concise.",
            "forbidden_behaviors": ["invent private memories"],
            "memory_summary": "Use only supplied Discord context.",
            "preferred_suites": ["identity_integrity"],
            "portrait_variant": "lavender",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def seed(client: TestClient) -> tuple[dict[str, object], list[dict[str, object]]]:
    login(client)
    connection_response = client.post(
        "/api/connections",
        json={
            "platform": "discord",
            "display_name": "Managed Discord",
            "connection_mode": "managed",
            "external_account_id": "bot-1",
            "status": "connected",
            "metadata": {},
        },
    )
    assert connection_response.status_code == 201
    connection = connection_response.json()
    deployments: list[dict[str, object]] = []
    for name in ("Ann", "Ning"):
        character = create_character(client, name)
        response = client.post(
            "/api/deployments",
            json={
                "character_card_id": character["id"],
                "connection_id": connection["id"],
                "workspace_id": "guild-1",
                "workspace_name": "Guild",
                "channel_id": "channel-1",
                "channel_name": "general",
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
        deployments.append(response.json())
    return connection, deployments


def test_roast_session_claim_is_bounded_and_idempotent(tmp_path: Path) -> None:
    client = TestClient(create_app(settings(tmp_path / "interaction.db")))
    connection, deployments = seed(client)
    created = client.post(
        "/api/interaction-sessions",
        json={
            "connection_id": connection["id"],
            "guild_id": "guild-1",
            "guild_name": "Guild",
            "channel_id": "channel-1",
            "channel_name": "general",
            "category_id": "",
            "target_user_id": "user-1",
            "target_display_name": "Target",
            "participant_deployment_ids": [deployments[0]["id"], deployments[1]["id"]],
            "rounds_per_trigger": 2,
            "maximum_triggers": 1,
            "cooldown_seconds": 0,
            "duration_seconds": 600,
            "intensity": "playful",
            "status": "active",
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["maximum_replies_per_trigger"] == 4

    claim_payload = {
        "connection_id": connection["id"],
        "guild_id": "guild-1",
        "channel_id": "channel-1",
        "target_user_id": "user-1",
        "source_message_id": "message-1",
    }
    first = client.post(
        "/api/connectors/discord/interaction-sessions/claim",
        json=claim_payload,
        headers=headers(),
    )
    assert first.status_code == 200, first.text
    assert first.json()["claimed"] is True
    assert first.json()["session"]["participant_deployment_ids"] == [
        deployments[0]["id"],
        deployments[1]["id"],
    ]

    duplicate = client.post(
        "/api/connectors/discord/interaction-sessions/claim",
        json=claim_payload,
        headers=headers(),
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["claimed"] is False

    completed = client.post(
        f"/api/connectors/discord/interaction-sessions/runs/{first.json()['run_id']}",
        json={
            "connection_id": connection["id"],
            "status": "completed",
            "reply_count": 4,
            "stop_reason": "rounds_completed",
        },
        headers=headers(),
    )
    assert completed.status_code == 204
    listed = client.get("/api/interaction-sessions")
    assert listed.json()[0]["status"] == "completed"


def test_sticker_metadata_is_observed_and_manual_semantics_win(tmp_path: Path) -> None:
    client = TestClient(create_app(settings(tmp_path / "stickers.db")))
    connection, _ = seed(client)
    observation = {
        "connection_id": connection["id"],
        "guild_id": "guild-1",
        "sticker_id": "sticker-1",
        "name": "side_eye_cat",
        "description": "A cat looking doubtful",
        "tags": ["doubt", "teasing"],
        "format_type": "png",
        "asset_url": "https://cdn.discordapp.com/stickers/sticker-1.png",
    }
    observed = client.post(
        "/api/connectors/discord/stickers/resolve",
        json=observation,
        headers=headers(),
    )
    assert observed.status_code == 200, observed.text
    assert observed.json()["semantic_source"] == "discord_metadata"
    assert "doubt" in observed.json()["semantic_description"]

    manual = client.put(
        "/api/discord/sticker-dictionary",
        json={
            **observation,
            "semantic_intent": "playful_disbelief",
            "semantic_emotion": "amused",
            "semantic_description": "The user is playfully saying they do not believe the claim.",
        },
    )
    assert manual.status_code == 200, manual.text
    assert manual.json()["semantic_source"] == "manual"

    resolved_again = client.post(
        "/api/connectors/discord/stickers/resolve",
        json={**observation, "description": "Changed metadata"},
        headers=headers(),
    )
    assert resolved_again.status_code == 200
    assert resolved_again.json()["semantic_intent"] == "playful_disbelief"
    assert resolved_again.json()["semantic_source"] == "manual"


def test_social_prompt_explains_stickers_and_bounded_roast() -> None:
    sticker = {
        "sticker_id": "sticker-1",
        "name": "side_eye_cat",
        "description": "",
        "tags": ["doubt"],
        "format_type": "png",
        "asset_url": "",
        "semantic_intent": "playful_disbelief",
        "semantic_emotion": "amused",
        "semantic_description": "The member is playfully expressing disbelief.",
        "semantic_source": "manual",
        "semantic_confidence": 1.0,
    }
    payload = DiscordInboundMessage(
        connection_id="connection-1",
        deployment_id="deployment-ann",
        message_id="message-1",
        guild_id="guild-1",
        guild_name="Guild",
        channel_id="channel-1",
        channel_name="general",
        author_id="user-1",
        author_display_name="Target",
        stickers=[sticker],
        recent_messages=[
            DiscordContextMessage(
                message_id="message-1",
                author_id="user-1",
                author_display_name="Target",
                stickers=[sticker],
            )
        ],
        interaction_session_id="session-1",
        interaction_type="roast",
        interaction_intensity="playful",
        interaction_round=1,
        interaction_total_rounds=2,
        interaction_position=1,
        interaction_participant_count=2,
        interaction_target_user_id="user-1",
        interaction_target_display_name="Target",
    )
    prompt = DiscordConnectorRuntime._social_prompt(character_name="Ann", payload=payload)
    assert "playfully expressing disbelief" in prompt
    assert "Portal-configured Roast Interaction Session" in prompt
    assert "Never target identity traits" in prompt
    assert "speaker 1 of 2" in prompt
