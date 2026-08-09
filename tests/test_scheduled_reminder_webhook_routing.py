import asyncio
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import httpx
from pydantic import SecretStr

from echo_masque.persistence import Database, DeploymentRepository, ScheduledReminderRepository
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord
from echo_masque.scheduled_reminder_service import ScheduledReminderDeliveryService


class FakeIdentityRepository:
    def __init__(self) -> None:
        self.registered: list[dict[str, Any]] = []

    def get_identity(self, deployment_id: str, owner_id: str) -> SimpleNamespace:
        assert deployment_id == "deployment-1"
        assert owner_id == "owner-1"
        return SimpleNamespace(
            mode="webhook",
            display_name="安 · Ann",
            avatar_url="https://example.invalid/ann.png",
        )

    def get_binding(
        self,
        *,
        owner_id: str,
        connection_id: str,
        channel_id: str,
    ) -> SimpleNamespace:
        assert owner_id == "owner-1"
        assert connection_id == "connection-1"
        assert channel_id == "channel-1"
        return SimpleNamespace(id="binding-1", status="active", webhook_id="webhook-1")

    def register_message_routes(self, **kwargs: Any) -> list[object]:
        self.registered.append(kwargs)
        return []


class FakeCredentialStore:
    def get_scope(self, **_: object) -> SecretStr:
        return SecretStr("webhook-token")


def database() -> Database:
    db = Database("sqlite:///:memory:")
    db.initialize()
    with db.session() as session:
        session.add(
            CharacterDeploymentRecord(
                id="deployment-1",
                owner_id="owner-1",
                character_card_id="character-1",
                connection_id="connection-1",
                platform="discord",
                workspace_id="guild-1",
                workspace_name="Guild",
                channel_id="channel-1",
                channel_name="general",
                thread_id="",
                thread_name="",
                participation_mode="smart",
                memory_scope="channel_isolated",
                version_label="Current",
                sticker_count=0,
                status="active",
            )
        )
        session.commit()
    return db


def test_webhook_reminder_registers_reply_route_after_delivery() -> None:
    db = database()
    reminders = ScheduledReminderRepository(db)
    reminders.create(
        owner_id="owner-1",
        deployment_id="deployment-1",
        connection_id="connection-1",
        platform="discord",
        channel_id="channel-1",
        thread_id="",
        target_user_id="user-1",
        reminder_text="Eleven o'clock. You asked me to remind you, so don't ignore this.",
        scheduled_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    identities = FakeIdentityRepository()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/api/v10/webhooks/webhook-1/webhook-token"
        assert request.url.params["wait"] == "true"
        body = json.loads(request.content)
        assert body["username"] == "安 · Ann"
        assert body["content"].startswith("<@user-1> ")
        assert body["allowed_mentions"] == {"parse": [], "users": ["user-1"]}
        return httpx.Response(200, json={"id": "message-webhook-1"})

    service = ScheduledReminderDeliveryService(
        reminders,
        DeploymentRepository(db),
        identities,  # type: ignore[arg-type]
        FakeCredentialStore(),  # type: ignore[arg-type]
        http_transport=httpx.MockTransport(handler),
    )

    assert asyncio.run(service.deliver_due_once()) == 1
    assert len(identities.registered) == 1
    route = identities.registered[0]
    assert route["connection_id"] == "connection-1"
    assert route["deployment_id"] == "deployment-1"
    assert route["workspace_id"] == "guild-1"
    assert route["channel_id"] == "channel-1"
    assert route["thread_id"] == ""
    assert route["webhook_id"] == "webhook-1"
    assert route["message_ids"] == ["message-webhook-1"]
