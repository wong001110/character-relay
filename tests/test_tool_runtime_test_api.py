from pathlib import Path

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr

from echo_masque.api import create_app
from echo_masque.config import Settings

SUPER_EMAIL = "tool-super@example.com"
SUPER_PASSWORD = "ToolSuper2026!"
ADMIN_EMAIL = "tool-admin@example.com"
ADMIN_PASSWORD = "ToolAdmin2026!"


def settings(path: Path) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{path}",
        legacy_local_user_enabled=False,
        bootstrap_admin_email=SUPER_EMAIL,
        bootstrap_admin_password=SecretStr(SUPER_PASSWORD),
        bootstrap_admin_display_name="Tool Super Admin",
        credential_encryption_keys=SecretStr(Fernet.generate_key().decode("ascii")),
    )


def login(client: TestClient, email: str, password: str) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200, response.text


def seed_deployment(app: object) -> tuple[str, str]:
    owner = app.state.auth_repository.get_user_by_email(SUPER_EMAIL)
    assert owner is not None
    card = app.state.repository.create_character_card(
        owner_id=owner.id,
        target_id="demo-stable",
        display_name="Tool Tester",
        subtitle="Runtime diagnostic",
        subject_type="companion",
        persona_summary="Tool test character.",
        traits=[],
        tags=[],
        expected_tone=None,
        forbidden_behaviors=[],
        memory_summary=None,
        preferred_suites=[],
        portrait_variant="lavender",
    )
    connection = app.state.deployment_repository.create_connection(
        owner_id=owner.id,
        platform="discord",
        display_name="Tool Test Discord",
        connection_mode="managed",
        external_account_id="tool-test-bot",
        status="connected",
        metadata={},
    )
    deployment = app.state.deployment_repository.create_deployment(
        owner_id=owner.id,
        character_card_id=card.id,
        connection_id=connection.id,
        workspace_id="guild-tool-test",
        workspace_name="Tool Test Guild",
        channel_id="channel-tool-test",
        channel_name="general",
        thread_id="",
        thread_name="",
        participation_mode="mention_only",
        memory_scope="channel_isolated",
        version_label="Current",
        sticker_count=0,
        status="active",
    )
    app.state.deployment_tool_repository.set_enabled_tools(
        deployment_id=deployment.id,
        owner_id=owner.id,
        enabled_tools=["utility.calculator", "scheduler.remind"],
    )
    return owner.id, deployment.id


def test_super_admin_can_execute_real_runtime_tool_and_side_effect_requires_confirmation(
    tmp_path: Path,
) -> None:
    app = create_app(settings(tmp_path / "tool-test.db"))
    owner_id, deployment_id = seed_deployment(app)
    client = TestClient(app)
    login(client, SUPER_EMAIL, SUPER_PASSWORD)

    deployments = client.get("/api/tools/test/deployments")
    assert deployments.status_code == 200, deployments.text
    selected = next(
        item for item in deployments.json() if item["deployment_id"] == deployment_id
    )
    assert selected["owner_id"] == owner_id
    assert selected["timezone"] == "Asia/Kuala_Lumpur"
    assert selected["enabled_tools"] == ["utility.calculator", "scheduler.remind"]

    calculator = client.post(
        "/api/tools/test/execute",
        json={
            "deployment_id": deployment_id,
            "tool_id": "utility.calculator",
            "arguments": {"expression": "5 * 7"},
            "guild_id": "guild-tool-test",
            "channel_id": "channel-tool-test",
            "thread_id": "",
            "message_id": "",
            "initiator_user_id": "",
            "trigger_text": "manual calculator test",
            "confirm_side_effect": False,
        },
    )
    assert calculator.status_code == 200, calculator.text
    payload = calculator.json()
    assert payload["status"] == "completed"
    assert payload["tool_id"] == "utility.calculator"
    assert payload["timezone"] == "Asia/Kuala_Lumpur"
    assert payload["result"]["ok"] is True
    assert payload["result"]["result"] == 35

    blocked = client.post(
        "/api/tools/test/execute",
        json={
            "deployment_id": deployment_id,
            "tool_id": "scheduler.remind",
            "arguments": {
                "reminder_text": "Manual Tool Calling test reminder",
                "delay_seconds": 60,
                "mention_user": False,
            },
            "guild_id": "guild-tool-test",
            "channel_id": "channel-tool-test",
            "thread_id": "",
            "message_id": "",
            "initiator_user_id": "",
            "trigger_text": "manual reminder test",
            "confirm_side_effect": False,
        },
    )
    assert blocked.status_code == 409
    assert "Explicit confirmation" in blocked.json()["detail"]

    confirmed = client.post(
        "/api/tools/test/execute",
        json={
            "deployment_id": deployment_id,
            "tool_id": "scheduler.remind",
            "arguments": {
                "reminder_text": "Manual Tool Calling test reminder",
                "delay_seconds": 60,
                "mention_user": False,
            },
            "guild_id": "guild-tool-test",
            "channel_id": "channel-tool-test",
            "thread_id": "",
            "message_id": "",
            "initiator_user_id": "",
            "trigger_text": "manual reminder test",
            "confirm_side_effect": True,
        },
    )
    assert confirmed.status_code == 200, confirmed.text
    confirmed_payload = confirmed.json()
    assert confirmed_payload["status"] == "completed"
    assert confirmed_payload["result"]["ok"] is True
    assert confirmed_payload["result"]["timezone"] == "Asia/Kuala_Lumpur"

    reminders = app.state.scheduled_reminder_repository.list_for_deployment(
        owner_id=owner_id,
        deployment_id=deployment_id,
    )
    assert len(reminders) == 1
    assert reminders[0].reminder_text == "Manual Tool Calling test reminder"


def test_tool_runtime_tester_is_super_admin_only(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "tool-test-access.db"))
    seed_deployment(app)
    app.state.auth_repository.create_user(
        email=ADMIN_EMAIL,
        display_name="Regular Admin",
        password_hash=app.state.auth_service.passwords.hash(ADMIN_PASSWORD),
        role="admin",
    )
    client = TestClient(app)
    login(client, ADMIN_EMAIL, ADMIN_PASSWORD)

    denied = client.get("/api/tools/test/deployments")
    assert denied.status_code == 403
    assert denied.json()["detail"] == "Super Admin access required."
