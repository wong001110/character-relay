import asyncio
import json
from pathlib import Path

from echo_masque.api.connector_schemas import DiscordInboundMessage
from echo_masque.character_invite_runtime import current_character_invite_proposal
from echo_masque.persistence import (
    ConditionWatchRepository,
    Database,
    ScheduledReminderRepository,
)
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord
from echo_masque.providers import ChatToolCall, ChatToolFunctionCall
from echo_masque.server_time_tools import ServerAwareToolRegistry
from echo_masque.smart_output import (
    SmartMentionPart,
    SmartOutputContext,
    SmartOutputProposal,
    SmartTextPart,
)
from echo_masque.tool_runtime import ToolExecutionContext


def seed(path: Path, *, candidate_mode: str = "smart") -> Database:
    database = Database(f"sqlite:///{path}")
    database.initialize()
    with database.session() as session:
        session.add(
            CharacterDeploymentRecord(
                id="inviter",
                owner_id="owner",
                character_card_id="character-inviter",
                connection_id="connection",
                platform="discord",
                workspace_id="guild",
                workspace_name="Guild",
                channel_id="channel",
                channel_name="general",
                participation_mode="smart",
                status="active",
            )
        )
        session.add(
            CharacterDeploymentRecord(
                id="candidate",
                owner_id="owner",
                character_card_id="character-candidate",
                connection_id="connection",
                platform="discord",
                workspace_id="guild",
                workspace_name="Guild",
                channel_id="channel",
                channel_name="general",
                participation_mode=candidate_mode,
                status="active",
            )
        )
        session.commit()
    return database


def inbound(*, author_is_bot: bool = False) -> DiscordInboundMessage:
    return DiscordInboundMessage(
        connection_id="connection",
        deployment_id="inviter",
        message_id="message-1",
        guild_id="guild",
        guild_name="Guild",
        channel_id="channel",
        channel_name="general",
        category_id="",
        thread_id="",
        thread_name="",
        author_id="member-1",
        author_display_name="Member",
        text="Can Selena help with this?",
        mentioned_bot=True,
        replied_to_bot=False,
        smart_candidate=True,
        author_is_bot=author_is_bot,
        available_characters=["Inviter", "Selena"],
        mentionable_participants=[
            {
                "ref": "deployment:candidate",
                "display_name": "Selena",
                "kind": "character",
            }
        ],
    )


def execution_context(*, author_is_bot: bool = False) -> ToolExecutionContext:
    return ToolExecutionContext(
        owner_id="owner",
        deployment_id="inviter",
        character_card_id="character-inviter",
        platform="discord",
        connection_id="connection",
        guild_id="guild",
        channel_id="channel",
        trigger_text="Can Selena help with this?",
        initiator_is_bot=author_is_bot,
        initiator_user_id="member-1",
    )


def invite_call(alias: str = "p1") -> ChatToolCall:
    return ChatToolCall(
        id="invite-call",
        function=ChatToolFunctionCall(
            name="character_invite",
            arguments=json.dumps(
                {
                    "participant_alias": alias,
                    "reason": "Selena knows this area better.",
                }
            ),
        ),
    )


def registry(database: Database) -> ServerAwareToolRegistry:
    return ServerAwareToolRegistry(
        reminder_repository=ScheduledReminderRepository(database),
        condition_watch_repository=ConditionWatchRepository(database),
        condition_watch_enabled=True,
    )


def test_character_invite_records_safe_prompt_local_proposal(tmp_path: Path) -> None:
    database = seed(tmp_path / "invite.db")
    smart_context = SmartOutputContext.from_payload(inbound(), character_name="Inviter")
    assert smart_context.participant_alias_to_ref == {"p1": "deployment:candidate"}

    result = asyncio.run(
        registry(database).execute(
            invite_call(),
            enabled_tool_ids=("character.invite",),
            context=execution_context(),
        )
    )

    assert result.trace.status == "completed"
    content = json.loads(result.content)
    assert content["proposal_status"] == "pending_runtime_validation"
    assert content["participant_alias"] == "p1"
    assert content["participant_name"] == "Selena"
    assert "candidate" not in result.content

    proposal = current_character_invite_proposal()
    assert proposal is not None
    assert proposal.candidate_deployment_id == "candidate"
    assert proposal.candidate_character_card_id == "character-candidate"


def test_character_invite_is_materialized_as_one_runtime_character_mention(
    tmp_path: Path,
) -> None:
    database = seed(tmp_path / "materialize.db")
    smart_context = SmartOutputContext.from_payload(inbound(), character_name="Inviter")
    result = asyncio.run(
        registry(database).execute(
            invite_call(),
            enabled_tool_ids=("character.invite",),
            context=execution_context(),
        )
    )
    assert result.trace.status == "completed"

    output, reason = smart_context.resolve(
        SmartOutputProposal(
            action="message",
            content=[SmartTextPart(text="I will ask her to weigh in.")],
        ),
        [],
    )
    assert reason == "ok"
    assert output is not None
    mentions = [
        part.mention
        for part in output.content
        if isinstance(part, SmartMentionPart)
    ]
    assert mentions == ["deployment:candidate"]
    assert smart_context.legacy_visible_text(output).endswith("@Selena")


def test_character_invite_rejects_bot_continuation_and_non_smart_candidate(
    tmp_path: Path,
) -> None:
    bot_database = seed(tmp_path / "invite-bot.db")
    SmartOutputContext.from_payload(
        inbound(author_is_bot=True),
        character_name="Inviter",
    )
    bot_result = asyncio.run(
        registry(bot_database).execute(
            invite_call(),
            enabled_tool_ids=("character.invite",),
            context=execution_context(author_is_bot=True),
        )
    )
    assert bot_result.trace.status == "rejected"

    non_smart_database = seed(
        tmp_path / "invite-non-smart.db",
        candidate_mode="mention_and_reply",
    )
    SmartOutputContext.from_payload(inbound(), character_name="Inviter")
    non_smart_result = asyncio.run(
        registry(non_smart_database).execute(
            invite_call(),
            enabled_tool_ids=("character.invite",),
            context=execution_context(),
        )
    )
    assert non_smart_result.trace.status == "rejected"


def test_character_invite_does_not_expand_conflicting_character_mentions(
    tmp_path: Path,
) -> None:
    database = seed(tmp_path / "invite-conflict.db")
    payload = inbound()
    payload.mentionable_participants.append(
        {
            "ref": "deployment:other",
            "display_name": "Other",
            "kind": "character",
        }
    )
    smart_context = SmartOutputContext.from_payload(payload, character_name="Inviter")
    result = asyncio.run(
        registry(database).execute(
            invite_call("p1"),
            enabled_tool_ids=("character.invite",),
            context=execution_context(),
        )
    )
    assert result.trace.status == "completed"

    output, reason = smart_context.resolve(
        SmartOutputProposal(
            action="message",
            content=[
                SmartTextPart(text="Other should see this."),
                SmartMentionPart(mention="p2"),
            ],
        ),
        [],
    )
    assert reason == "ok"
    assert output is not None
    mentions = [
        part.mention
        for part in output.content
        if isinstance(part, SmartMentionPart)
    ]
    assert mentions == ["deployment:other"]
