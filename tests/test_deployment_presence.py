from pathlib import Path

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr

from echo_masque.api import create_app
from echo_masque.config import Settings

ADMIN_EMAIL = "presence-admin@example.com"
ADMIN_PASSWORD = "PresenceAdmin2026!"


def settings(path: Path) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{path}",
        legacy_local_user_enabled=False,
        bootstrap_admin_email=ADMIN_EMAIL,
        bootstrap_admin_password=SecretStr(ADMIN_PASSWORD),
        bootstrap_admin_display_name="Presence Admin",
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
        "/api/characters",
        json={
            "target_id": "demo-stable",
            "display_name": "Ann",
            "subtitle": "Presence fixture",
            "subject_type": "companion",
            "persona_summary": "Ann is concise.",
            "traits": ["calm"],
            "tags": ["presence"],
            "expected_tone": "Concise.",
            "forbidden_behaviors": ["invent memories"],
            "memory_summary": "Use supplied context.",
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
            "display_name": "Presence Discord",
            "connection_mode": "managed",
            "external_account_id": "presence-bot",
            "status": "connected",
            "metadata": {},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_deployment(
    client: TestClient,
    *,
    character_id: object,
    connection_id: object,
    guild_id: str,
) -> dict[str, object]:
    response = client.post(
        "/api/deployments",
        json={
            "character_card_id": character_id,
            "connection_id": connection_id,
            "workspace_id": guild_id,
            "workspace_name": guild_id,
            "channel_id": f"channel-{guild_id}",
            "channel_name": "#general",
            "thread_id": "",
            "thread_name": "",
            "participation_mode": "smart",
            "memory_scope": "server_shared",
            "version_label": "Current",
            "sticker_count": 0,
            "status": "active",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def has_explicit_timezone(value: str) -> bool:
    return value.endswith("Z") or value.endswith("+00:00")


def test_presence_defaults_to_idle_and_is_scoped_per_deployment(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "presence.db"))
    client = TestClient(app)
    login(client)
    character = create_character(client)
    connection = create_connection(client)
    server_a = create_deployment(
        client,
        character_id=character["id"],
        connection_id=connection["id"],
        guild_id="guild-a",
    )
    server_b = create_deployment(
        client,
        character_id=character["id"],
        connection_id=connection["id"],
        guild_id="guild-b",
    )

    initial = client.get(f"/api/deployments/{server_a['id']}/presence")
    assert initial.status_code == 200, initial.text
    assert initial.json()["state"] == "idle"
    assert initial.json()["persisted"] is False
    assert initial.json()["available_for_character_runtime"] is True
    assert has_explicit_timezone(initial.json()["started_at"])

    sleeping = client.put(
        f"/api/deployments/{server_a['id']}/presence",
        json={
            "state": "sleeping",
            "reason": "manual acceptance test",
            "expected_end_at": "2026-08-20T06:55:00+08:00",
        },
    )
    assert sleeping.status_code == 200, sleeping.text
    assert sleeping.json()["state"] == "sleeping"
    assert sleeping.json()["persisted"] is True
    assert sleeping.json()["available_for_character_runtime"] is False
    assert sleeping.json()["discovery_allowed"] is False
    assert has_explicit_timezone(sleeping.json()["started_at"])
    assert has_explicit_timezone(sleeping.json()["expected_end_at"])

    independent = client.get(f"/api/deployments/{server_b['id']}/presence")
    assert independent.status_code == 200
    assert independent.json()["state"] == "idle"
    assert independent.json()["persisted"] is False


def test_rhythm_api_serializes_schedule_instants_with_timezone(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "presence-rhythm-api.db"))
    client = TestClient(app)
    login(client)
    character = create_character(client)
    connection = create_connection(client)
    deployment = create_deployment(
        client,
        character_id=character["id"],
        connection_id=connection["id"],
        guild_id="guild-rhythm",
    )

    response = client.put(
        f"/api/deployments/{deployment['id']}/presence/rhythm",
        json={
            "enabled": True,
            "preferred_sleep_start_minute": 0,
            "sleep_duration_min_minutes": 360,
            "sleep_duration_max_minutes": 480,
            "variation_minutes": 45,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["schedule_timezone"] == "Asia/Kuala_Lumpur"
    assert has_explicit_timezone(payload["scheduled_sleep_at"])
    assert has_explicit_timezone(payload["scheduled_wake_at"])
    assert has_explicit_timezone(payload["next_transition_at"])


def test_browsing_presence_requires_activity_type_and_deletion_cleans_state(
    tmp_path: Path,
) -> None:
    app = create_app(settings(tmp_path / "presence-cleanup.db"))
    client = TestClient(app)
    login(client)
    character = create_character(client)
    connection = create_connection(client)
    deployment = create_deployment(
        client,
        character_id=character["id"],
        connection_id=connection["id"],
        guild_id="guild-a",
    )

    invalid = client.put(
        f"/api/deployments/{deployment['id']}/presence",
        json={"state": "browsing"},
    )
    assert invalid.status_code == 422

    browsing = client.put(
        f"/api/deployments/{deployment['id']}/presence",
        json={"state": "browsing", "activity_type": "youtube"},
    )
    assert browsing.status_code == 200, browsing.text
    assert browsing.json()["state"] == "browsing"
    assert browsing.json()["activity_type"] == "youtube"
    assert browsing.json()["discovery_allowed"] is True

    deleted = client.delete(f"/api/deployments/{deployment['id']}")
    assert deleted.status_code == 204, deleted.text
    with app.state.database.engine.connect() as raw:
        remaining = raw.exec_driver_sql(
            "SELECT COUNT(*) FROM deployment_presence WHERE deployment_id = ?",
            (deployment["id"],),
        ).scalar_one()
    assert remaining == 0
