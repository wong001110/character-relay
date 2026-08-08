import asyncio
import json
from datetime import UTC, datetime, timedelta

import httpx
from pydantic import SecretStr

from echo_masque.persistence import (
    Database,
    DeploymentRepository,
    DiscordIdentityRepository,
    ScheduledReminderRepository,
)
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord
from echo_masque.providers import ChatToolCall, ChatToolFunctionCall
from echo_masque.scheduled_reminder_service import ScheduledReminderDeliveryService
from echo_masque.tool_runtime import ToolExecutionContext, ToolRegistry


def call(name: str, arguments: dict[str, object]) -> ChatToolCall:
    return ChatToolCall(
        id=f"call-{name}",
        function=ChatToolFunctionCall(
            name=name,
            arguments=json.dumps(arguments),
        ),
    )


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
                participation_mode="mention_and_reply",
                memory_scope="channel_isolated",
                version_label="Current",
                sticker_count=0,
                status="active",
            )
        )
        session.commit()
    return db


def context() -> ToolExecutionContext:
    return ToolExecutionContext(
        owner_id="owner-1",
        deployment_id="deployment-1",
        character_card_id="character-1",
        platform="discord",
        channel_id="channel-1",
        thread_id="",
        trigger_text="Remind me in five minutes.",
        initiator_is_bot=False,
        initiator_user_id="user-1",
    )


def test_scheduler_tool_create_list_cancel_is_deployment_scoped() -> None:
    db = database()
    reminders = ScheduledReminderRepository(db)
    registry = ToolRegistry(reminder_repository=reminders)
    enabled = ("scheduler.remind", "scheduler.list", "scheduler.cancel")

    created = asyncio.run(
        registry.execute(
            call(
                "scheduler_remind",
                {
                    "reminder_text": "Submit the report.",
                    "delay_seconds": 300,
                    "mention_user": True,
                },
            ),
            enabled_tool_ids=enabled,
            context=context(),
        )
    )
    created_payload = json.loads(created.content)
    assert created.trace.status == "completed"
    reminder_id = created_payload["reminder_id"]

    records = reminders.list_for_deployment(
        owner_id="owner-1",
        deployment_id="deployment-1",
    )
    assert len(records) == 1
    assert records[0].connection_id == "connection-1"
    assert records[0].platform == "discord"
    assert records[0].target_user_id == "user-1"

    listed = asyncio.run(
        registry.execute(
            call("scheduler_list", {}),
            enabled_tool_ids=enabled,
            context=context(),
        )
    )
    listed_payload = json.loads(listed.content)
    assert listed.trace.status == "completed"
    assert listed_payload["reminders"][0]["reminder_id"] == reminder_id

    cancelled = asyncio.run(
        registry.execute(
            call("scheduler_cancel", {"reminder_id": reminder_id}),
            enabled_tool_ids=enabled,
            context=context(),
        )
    )
    assert cancelled.trace.status == "completed"
    assert json.loads(cancelled.content)["status"] == "cancelled"


def test_scheduler_delivery_sends_due_bot_identity_reminder() -> None:
    db = database()
    reminders = ScheduledReminderRepository(db)
    identities = DiscordIdentityRepository(db)
    identities.upsert_identity(
        deployment_id="deployment-1",
        owner_id="owner-1",
        mode="bot",
        display_name="Reminder Character",
        avatar_url="",
    )
    record = reminders.create(
        owner_id="owner-1",
        deployment_id="deployment-1",
        channel_id="channel-1",
        thread_id="",
        target_user_id="user-1",
        reminder_text="Time to submit the report.",
        scheduled_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.method == "POST"
        assert request.url.path == "/api/v10/channels/channel-1/messages"
        assert request.headers["Authorization"] == "Bot discord-test-token"
        body = json.loads(request.content)
        assert body["content"] == "<@user-1> Time to submit the report."
        assert body["allowed_mentions"] == {"parse": [], "users": ["user-1"]}
        return httpx.Response(200, json={"id": "message-1"})

    service = ScheduledReminderDeliveryService(
        reminders,
        DeploymentRepository(db),
        identities,
        object(),  # type: ignore[arg-type]
        discord_bot_token=SecretStr("discord-test-token"),
        http_transport=httpx.MockTransport(handler),
    )
    delivered = asyncio.run(service.deliver_due_once())

    assert delivered == 1
    assert len(requests) == 1
    finished = reminders.list_for_deployment(
        owner_id="owner-1",
        deployment_id="deployment-1",
        include_finished=True,
    )
    by_id = {item.id: item for item in finished}
    assert by_id[record.id].status == "completed"
    assert by_id[record.id].delivered_at is not None
