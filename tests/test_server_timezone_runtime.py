import asyncio
import json
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from echo_masque.api.connector_schemas import DiscordInboundMessage
from echo_masque.context_layer import ContextOrchestrator
from echo_masque.persistence import Database, DeploymentRepository, KnowledgeRepository, Repository
from echo_masque.persistence.server_runtime_repository import ServerRuntimeRepository
from echo_masque.providers import ChatToolCall, ChatToolFunctionCall
from echo_masque.server_time import activate_server_timezone
from echo_masque.server_time_tools import ServerAwareToolRegistry
from echo_masque.tool_runtime import ToolExecutionContext
from echo_masque.persistence.scheduled_reminder_repository import ScheduledReminderRepository


def call(name: str, arguments: dict[str, object]) -> ChatToolCall:
    return ChatToolCall(
        id=f"call-{name}",
        function=ChatToolFunctionCall(name=name, arguments=json.dumps(arguments)),
    )


def seeded_database() -> tuple[Database, str, str]:
    database = Database("sqlite:///:memory:")
    database.initialize()
    repository = Repository(database)
    repository.seed_demo_targets()
    card = repository.create_character_card(
        owner_id="owner-1",
        target_id="demo-stable",
        display_name="Ann",
        subtitle="Timezone test",
        subject_type="companion",
        persona_summary="A test character.",
        traits=[],
        tags=[],
        expected_tone=None,
        forbidden_behaviors=[],
        memory_summary=None,
        preferred_suites=[],
        portrait_variant="lavender",
    )
    deployments = DeploymentRepository(database)
    connection = deployments.create_connection(
        owner_id="owner-1",
        platform="discord",
        display_name="Discord",
        connection_mode="managed",
        external_account_id="bot",
        status="connected",
        metadata={},
    )
    profile = deployments.create_server_profile(
        owner_id="owner-1",
        connection_id=connection.id,
        name="Malaysia Server",
        guild_id="guild-1",
        guild_name="Guild",
        excluded_channel_ids=[],
        excluded_category_ids=[],
        thread_policy="inherit_parent",
    )
    deployments.create_deployment(
        owner_id="owner-1",
        character_card_id=card.id,
        connection_id=connection.id,
        server_profile_id=profile.id,
        workspace_id="guild-1",
        workspace_name="Guild",
        channel_id="",
        channel_name="",
        thread_id="",
        thread_name="",
        participation_mode="smart",
        memory_scope="server_shared",
        version_label="Current",
        sticker_count=0,
        status="active",
    )
    ServerRuntimeRepository(database).set_timezone(
        profile_id=profile.id,
        owner_id="owner-1",
        timezone="Asia/Kuala_Lumpur",
    )
    return database, connection.id, card.id


def test_context_prompt_uses_server_timezone() -> None:
    database, connection_id, card_id = seeded_database()
    deployment = DeploymentRepository(database).list_deployments("owner-1")[0]
    orchestrator = ContextOrchestrator(KnowledgeRepository(database))
    payload = DiscordInboundMessage(
        connection_id=connection_id,
        deployment_id=deployment.id,
        message_id="message-1",
        guild_id="guild-1",
        guild_name="Guild",
        channel_id="channel-1",
        channel_name="general",
        author_id="user-1",
        author_display_name="Juen",
        text="What time is dinner?",
        mentioned_bot=True,
        recent_messages=[],
    )

    context = orchestrator.build(
        payload=payload,
        deployment=deployment,
        character_name="Ann",
    )
    guidance = "\n".join(context.knowledge_prompt_guidance())

    assert card_id == deployment.character_card_id
    assert "Default timezone: Asia/Kuala_Lumpur" in guidance
    assert "+08:00" in guidance
    assert "Interpret dates and times without an explicit timezone" in guidance


def test_current_time_defaults_to_server_timezone() -> None:
    activate_server_timezone("Asia/Kuala_Lumpur")
    registry = ServerAwareToolRegistry()
    result = asyncio.run(
        registry.execute(
            call("utility_current_time", {}),
            enabled_tool_ids=("utility.current_time",),
            context=ToolExecutionContext(
                owner_id="owner-1",
                deployment_id="deployment-1",
                character_card_id="character-1",
                platform="discord",
            ),
        )
    )
    payload = json.loads(result.content)

    assert result.trace.status == "completed"
    assert payload["timezone"] == "Asia/Kuala_Lumpur"
    assert payload["utc_offset"] == "+08:00"


def test_naive_reminder_time_is_interpreted_in_server_timezone() -> None:
    database, connection_id, card_id = seeded_database()
    deployment = DeploymentRepository(database).list_deployments("owner-1")[0]
    reminders = ScheduledReminderRepository(database)
    registry = ServerAwareToolRegistry(reminder_repository=reminders)
    activate_server_timezone("Asia/Kuala_Lumpur")
    local_target = (datetime.now(ZoneInfo("Asia/Kuala_Lumpur")) + timedelta(hours=2)).replace(
        microsecond=0
    )
    naive_local = local_target.replace(tzinfo=None).isoformat(timespec="seconds")

    result = asyncio.run(
        registry.execute(
            call(
                "scheduler_remind",
                {
                    "reminder_text": "Check the build.",
                    "scheduled_at": naive_local,
                    "mention_user": False,
                },
            ),
            enabled_tool_ids=("scheduler.remind",),
            context=ToolExecutionContext(
                owner_id="owner-1",
                deployment_id=deployment.id,
                character_card_id=card_id,
                platform="discord",
                connection_id=connection_id,
                guild_id="guild-1",
                channel_id="channel-1",
            ),
        )
    )
    payload = json.loads(result.content)
    stored = reminders.list_for_deployment(
        owner_id="owner-1",
        deployment_id=deployment.id,
    )[0]
    stored_utc = stored.scheduled_at
    if stored_utc.tzinfo is None:
        stored_utc = stored_utc.replace(tzinfo=UTC)

    assert result.trace.status == "completed"
    assert payload["timezone"] == "Asia/Kuala_Lumpur"
    assert payload["scheduled_at"].endswith("+08:00")
    assert abs((stored_utc - local_target.astimezone(UTC)).total_seconds()) < 1
