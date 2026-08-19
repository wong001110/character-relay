import asyncio
import json
from pathlib import Path
from unittest.mock import Mock

import httpx
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select

from echo_masque.api import create_app
from echo_masque.config import Settings
from echo_masque.persistence.deployment_presence_notice_models import (
    DeploymentPresenceNoticeRecord,
)
from echo_masque.scheduled_reminder_service import ScheduledReminderDeliveryService

ADMIN_EMAIL = "sleep-admin@example.com"
ADMIN_PASSWORD = "SleepAdmin2026!"
CONNECTOR_SECRET = "sleep-connector-secret"


def settings(path: Path) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{path}",
        legacy_local_user_enabled=False,
        bootstrap_admin_email=ADMIN_EMAIL,
        bootstrap_admin_password=SecretStr(ADMIN_PASSWORD),
        bootstrap_admin_display_name="Sleep Admin",
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


def seed(client: TestClient) -> tuple[dict[str, object], dict[str, object]]:
    login(client)
    character = client.post(
        "/api/characters",
        json={
            "target_id": "demo-stable",
            "display_name": "Ann",
            "subtitle": "Sleep fixture",
            "subject_type": "companion",
            "persona_summary": "Ann is concise.",
            "traits": ["calm"],
            "tags": ["sleep"],
            "expected_tone": "Concise.",
            "forbidden_behaviors": ["invent memories"],
            "memory_summary": "Use supplied context.",
            "preferred_suites": ["identity_integrity"],
            "portrait_variant": "lavender",
        },
    )
    assert character.status_code == 201, character.text
    connection = client.post(
        "/api/connections",
        json={
            "platform": "discord",
            "display_name": "Sleep Discord",
            "connection_mode": "managed",
            "external_account_id": "sleep-bot",
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
            "workspace_id": "guild-sleep",
            "workspace_name": "Sleep Guild",
            "channel_id": "channel-sleep",
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
    assert deployment.status_code == 201, deployment.text
    return connection.json(), deployment.json()


def inbound(
    connection: dict[str, object],
    deployment: dict[str, object],
    *,
    message_id: str,
    mentioned_bot: bool,
    replied_to_bot: bool = False,
    text: str = "Are you there?",
) -> dict[str, object]:
    return {
        "connection_id": connection["id"],
        "deployment_id": deployment["id"],
        "message_id": message_id,
        "guild_id": "guild-sleep",
        "guild_name": "Sleep Guild",
        "channel_id": "channel-sleep",
        "channel_name": "general",
        "thread_id": "",
        "thread_name": "",
        "author_id": "user-1",
        "author_display_name": "Juen",
        "text": text,
        "mentioned_bot": mentioned_bot,
        "replied_to_bot": replied_to_bot,
        "smart_candidate": False,
        "recent_messages": [],
    }


def notice_count(app: object) -> int:
    database = app.state.database  # type: ignore[attr-defined]
    with database.session() as session:
        return len(list(session.scalars(select(DeploymentPresenceNoticeRecord))))


def test_sleeping_is_hard_runtime_gate_and_only_explicit_address_queues_notice(
    tmp_path: Path,
) -> None:
    app = create_app(settings(tmp_path / "sleep-policy.db"))
    client = TestClient(app)
    connection, deployment = seed(client)

    sleeping = client.put(
        f"/api/deployments/{deployment['id']}/presence",
        json={"state": "sleeping", "reason": "night rhythm"},
    )
    assert sleeping.status_code == 200, sleeping.text

    # If a sleeping request crosses Presence authority and starts resolving a Character target,
    # the test fails immediately. This proves the hard gate precedes model/tool setup.
    runtime = app.state.discord_connector_runtime
    runtime._target = Mock(side_effect=AssertionError("sleeping Character target must not resolve"))

    ambient = client.post(
        "/api/connectors/discord/messages",
        headers=connector_headers(),
        json=inbound(
            connection,
            deployment,
            message_id="ambient-1",
            mentioned_bot=False,
        ),
    )
    assert ambient.status_code == 200, ambient.text
    assert ambient.json()["action"] == "silent"
    assert ambient.json()["reason"] == "deployment_presence_sleeping"
    assert notice_count(app) == 0

    explicit_name = client.post(
        "/api/connectors/discord/messages",
        headers=connector_headers(),
        json=inbound(
            connection,
            deployment,
            message_id="explicit-name-1",
            mentioned_bot=False,
            text="Ann, are you there?",
        ),
    )
    assert explicit_name.status_code == 200, explicit_name.text
    assert explicit_name.json()["action"] == "silent"
    assert explicit_name.json()["reason"] == "deployment_presence_sleeping"
    assert notice_count(app) == 1

    # A second explicit source message inside the notice cooldown must not queue another notice.
    repeated = client.post(
        "/api/connectors/discord/messages",
        headers=connector_headers(),
        json=inbound(
            connection,
            deployment,
            message_id="explicit-2",
            mentioned_bot=True,
        ),
    )
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["reason"] == "deployment_presence_sleeping"
    assert notice_count(app) == 1


def test_sleeping_reply_queues_notice_and_delivery_uses_real_bot_identity(
    tmp_path: Path,
) -> None:
    app = create_app(settings(tmp_path / "sleep-bot-notice.db"))
    client = TestClient(app)
    connection, deployment = seed(client)
    assert (
        client.put(
            f"/api/deployments/{deployment['id']}/presence",
            json={"state": "sleeping"},
        ).status_code
        == 200
    )

    response = client.post(
        "/api/connectors/discord/messages",
        headers=connector_headers(),
        json=inbound(
            connection,
            deployment,
            message_id="reply-source-1",
            mentioned_bot=False,
            replied_to_bot=True,
        ),
    )
    assert response.status_code == 200, response.text
    assert response.json()["reason"] == "deployment_presence_sleeping"
    assert notice_count(app) == 1

    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"id": "system-notice-message"})

    delivery = ScheduledReminderDeliveryService(
        app.state.scheduled_reminder_repository,
        app.state.deployment_repository,
        app.state.discord_identity_repository,
        app.state.credential_store,
        discord_bot_token=SecretStr("real-discord-bot-token"),
        http_transport=httpx.MockTransport(handler),
    )
    delivered = asyncio.run(delivery.deliver_due_once())
    assert delivered == 1
    assert len(requests) == 1
    request = requests[0]
    assert request.url.path == "/api/v10/channels/channel-sleep/messages"
    assert request.headers["authorization"] == "Bot real-discord-bot-token"
    payload = json.loads(request.content.decode("utf-8"))
    assert payload["content"] == "🌙 Ann 当前正在睡觉。"
    assert payload["allowed_mentions"] == {"parse": []}
    assert payload["message_reference"] == {
        "message_id": "reply-source-1",
        "fail_if_not_exists": False,
    }
