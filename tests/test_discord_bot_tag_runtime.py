from echo_masque.api.connector_schemas import (
    DiscordContextMessage,
    DiscordInboundMessage,
)
from echo_masque.connector_runtime import DiscordConnectorRuntime


def payload(*, author_is_bot: bool) -> DiscordInboundMessage:
    return DiscordInboundMessage(
        connection_id="connection-1",
        deployment_id="deployment-ning",
        message_id="message-1",
        guild_id="guild-1",
        guild_name="Companion Guild",
        channel_id="channel-1",
        channel_name="companions",
        author_id="character:ann" if author_is_bot else "user-1",
        author_display_name="Ann" if author_is_bot else "Juen",
        text="What do you think?",
        mentioned_bot=True,
        author_is_bot=author_is_bot,
        available_characters=["Ann", "织 · Zhi"],
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


def test_social_prompt_exposes_bounded_character_tag_contract() -> None:
    prompt = DiscordConnectorRuntime._social_prompt(
        character_name="宁 · Ning",
        payload=payload(author_is_bot=True),
    )

    assert "Other active characters at this location: Ann, 织 · Zhi." in prompt
    assert "begin your reply with @" in prompt
    assert "Use character tags sparingly" in prompt
    assert "Never tag yourself" in prompt
    assert "another deployed character" in prompt
    assert "[Character: Ann | character:ann]" in prompt


def test_social_prompt_distinguishes_human_trigger_from_character_context() -> None:
    prompt = DiscordConnectorRuntime._social_prompt(
        character_name="宁 · Ning",
        payload=payload(author_is_bot=False),
    )

    assert "human Discord member" in prompt
    assert "[Member: Juen | user-1]" in prompt
