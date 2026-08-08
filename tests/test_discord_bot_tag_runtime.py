from echo_masque.api.connector_schemas import (
    DiscordContextMessage,
    DiscordInboundMessage,
)
from echo_masque.connector_runtime import DiscordConnectorRuntime
from echo_masque.smart_output import DiscordActionParticipant


def payload(*, author_is_bot: bool) -> DiscordInboundMessage:
    mentionable = [
        DiscordActionParticipant(
            ref="deployment:deployment-ann",
            display_name="Ann",
            kind="character",
        ),
        DiscordActionParticipant(
            ref="deployment:deployment-zhi",
            display_name="织 · Zhi",
            kind="character",
        ),
    ]
    if not author_is_bot:
        mentionable.append(
            DiscordActionParticipant(
                ref="user:123456789012345678",
                display_name="Juen",
                kind="human",
            )
        )
    return DiscordInboundMessage(
        connection_id="connection-1",
        deployment_id="deployment-ning",
        message_id="message-1",
        guild_id="guild-1",
        guild_name="Companion Guild",
        channel_id="channel-1",
        channel_name="companions",
        author_id="character:ann" if author_is_bot else "123456789012345678",
        author_display_name="Ann" if author_is_bot else "Juen",
        text="What do you think?",
        mentioned_bot=True,
        author_is_bot=author_is_bot,
        available_characters=["Ann", "织 · Zhi"],
        mentionable_participants=mentionable,
        recent_messages=[
            DiscordContextMessage(
                message_id="context-1",
                author_id="character:ann",
                author_display_name="Ann",
                text="@Ning, what do you think?",
                is_bot=True,
            )
        ],
    )


def test_social_prompt_exposes_bounded_character_alias_contract() -> None:
    prompt = DiscordConnectorRuntime._social_prompt(
        character_name="宁 · Ning",
        payload=payload(author_is_bot=True),
    )

    assert "Mentionable participants:" in prompt
    assert "p1: Ann (character)" in prompt
    assert "p2: 织 · Zhi (character)" in prompt
    assert "宁 · Ning (character)" not in prompt
    assert "Never mention yourself" in prompt
    assert "another deployed character" in prompt
    assert "[context | Character: Ann]" in prompt
    assert "deployment:deployment-ann" not in prompt


def test_social_prompt_distinguishes_human_trigger_without_raw_user_id() -> None:
    prompt = DiscordConnectorRuntime._social_prompt(
        character_name="宁 · Ning",
        payload=payload(author_is_bot=False),
    )

    assert "human Discord member" in prompt
    assert "p3: Juen (human)" in prompt
    assert "[trigger | Member: Juen]" in prompt
    assert "123456789012345678" not in prompt
