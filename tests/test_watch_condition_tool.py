import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

from echo_masque.persistence import (
    ConditionWatchRepository,
    Database,
    ScheduledReminderRepository,
)
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord
from echo_masque.persistence.models import CharacterCardRecord, TargetRecord
from echo_masque.providers import ChatToolCall, ChatToolFunctionCall
from echo_masque.server_time_tools import ServerAwareToolRegistry
from echo_masque.tool_runtime import ToolExecutionContext


def seed(path: Path) -> tuple[Database, ConditionWatchRepository]:
    database = Database(f"sqlite:///{path}")
    database.initialize()
    with database.session() as session:
        session.add(TargetRecord(id="target", name="Target", target_kind="prompt_model"))
        session.add(
            CharacterCardRecord(
                id="character",
                owner_id="owner",
                target_id="target",
                display_name="Character",
            )
        )
        session.add(
            CharacterDeploymentRecord(
                id="deployment",
                owner_id="owner",
                character_card_id="character",
                connection_id="connection",
                platform="discord",
                workspace_id="guild",
                workspace_name="Guild",
                channel_id="channel",
                channel_name="general",
                status="active",
            )
        )
        session.commit()
    return database, ConditionWatchRepository(database)


def tool_call(arguments: dict[str, object]) -> ChatToolCall:
    return ChatToolCall(
        id="watch-call",
        function=ChatToolFunctionCall(
            name="watch_condition",
            arguments=json.dumps(arguments),
        ),
    )


def context(*, bot: bool = False) -> ToolExecutionContext:
    return ToolExecutionContext(
        owner_id="owner",
        deployment_id="deployment",
        character_card_id="character",
        platform="discord",
        connection_id="connection",
        guild_id="guild",
        channel_id="channel",
        initiator_is_bot=bot,
        initiator_user_id="member-1",
        trigger_text="Tell me when the release is available.",
    )


def test_watch_condition_persists_bounded_deployment_scoped_watch(tmp_path: Path) -> None:
    database, watches = seed(tmp_path / "watch-tool.db")
    registry = ServerAwareToolRegistry(
        reminder_repository=ScheduledReminderRepository(database),
        condition_watch_repository=watches,
        condition_watch_enabled=True,
    )

    result = asyncio.run(
        registry.execute(
            tool_call(
                {
                    "condition_text": "The release is available",
                    "notification_text": "The release is available now.",
                    "check_interval_seconds": 300,
                    "expires_in_seconds": 3600,
                    "max_attempts": 99,
                    "mention_user": True,
                }
            ),
            enabled_tool_ids=("watch.condition",),
            context=context(),
        )
    )

    assert result.trace.status == "completed"
    payload = json.loads(result.content)
    stored = watches.get(owner_id="owner", watch_id=payload["watch_id"])
    assert stored is not None
    assert stored.deployment_id == "deployment"
    assert stored.target_user_id == "member-1"
    assert stored.status == "active"
    assert stored.check_interval_seconds == 300
    # One-hour expiry with a five-minute cadence permits at most 12 checks.
    assert stored.max_attempts == 12
    assert stored.next_check_at > datetime.now(UTC)


def test_watch_condition_rejects_autonomous_bot_creation(tmp_path: Path) -> None:
    database, watches = seed(tmp_path / "watch-bot.db")
    registry = ServerAwareToolRegistry(
        reminder_repository=ScheduledReminderRepository(database),
        condition_watch_repository=watches,
        condition_watch_enabled=True,
    )

    result = asyncio.run(
        registry.execute(
            tool_call(
                {
                    "condition_text": "Something changes",
                    "notification_text": "It changed.",
                }
            ),
            enabled_tool_ids=("watch.condition",),
            context=context(bot=True),
        )
    )

    assert result.trace.status == "rejected"
    assert watches.list_for_deployment(
        owner_id="owner",
        deployment_id="deployment",
        include_finished=True,
    ) == []
