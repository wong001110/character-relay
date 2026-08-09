from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr

from echo_masque.api import create_app
from echo_masque.config import Settings

EMAIL = "scheduler-admin@example.com"
PASSWORD = "SchedulerPortal2026!"


def settings(path: Path) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{path}",
        legacy_local_user_enabled=False,
        bootstrap_admin_email=EMAIL,
        bootstrap_admin_password=SecretStr(PASSWORD),
        credential_encryption_keys=SecretStr(Fernet.generate_key().decode("ascii")),
    )


def login(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
    )
    assert response.status_code == 200, response.text


def create_deployment(client: TestClient) -> str:
    character = client.post(
        "/api/characters/prompt-model",
        json={
            "display_name": "Reminder Character",
            "subtitle": "Scheduler test",
            "subject_type": "assistant",
            "persona_summary": "Creates reminders when requested.",
            "traits": ["reliable"],
            "tags": ["scheduler"],
            "expected_tone": "Concise.",
            "forbidden_behaviors": [],
            "memory_summary": None,
            "preferred_suites": ["identity_integrity"],
            "portrait_variant": "mint",
            "provider": "deepseek",
            "base_url": "https://api.deepseek.com",
            "model": "deepseek-v4-flash",
            "system_prompt": "You are a reminder test character.",
            "temperature": 0.2,
            "api_key": "test-provider-key",
        },
    )
    assert character.status_code == 201, character.text
    connection = client.post(
        "/api/connections",
        json={
            "platform": "discord",
            "display_name": "Scheduler Discord",
            "connection_mode": "managed",
            "external_account_id": "scheduler-bot",
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
            "workspace_id": "guild-scheduler",
            "workspace_name": "Scheduler Guild",
            "channel_id": "channel-scheduler",
            "channel_name": "reminders",
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
    return str(deployment.json()["id"])


def test_scheduler_portal_lists_and_cancels_real_reminder(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "scheduler-portal.db"))
    client = TestClient(app)
    login(client)
    deployment_id = create_deployment(client)
    user = app.state.auth_repository.get_user_by_email(EMAIL)
    assert user is not None

    record = app.state.scheduled_reminder_repository.create(
        owner_id=user.id,
        deployment_id=deployment_id,
        channel_id="channel-scheduler",
        thread_id="",
        target_user_id="discord-user-1",
        reminder_text="Time to join the meeting.",
        scheduled_at=datetime.now(UTC) + timedelta(hours=1),
    )

    listed = client.get("/api/scheduler/reminders", params={"status": "pending"})
    assert listed.status_code == 200, listed.text
    payload = listed.json()
    assert len(payload["items"]) == 1
    item = payload["items"][0]
    assert item["id"] == record.id
    assert item["deployment_id"] == deployment_id
    assert item["character_name"] == "Reminder Character"
    assert item["channel_name"] == "reminders"
    assert item["status"] == "pending"
    assert item["reminder_text"] == "Time to join the meeting."

    cancelled = client.delete(f"/api/scheduler/reminders/{record.id}")
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"

    cancelled_list = client.get(
        "/api/scheduler/reminders",
        params={"status": "cancelled"},
    )
    assert cancelled_list.status_code == 200, cancelled_list.text
    assert [item["id"] for item in cancelled_list.json()["items"]] == [record.id]
