"""The Character receives meaning, not a preloaded resource catalogue or IDs."""

from echo_masque.api.connector_schemas import DiscordInboundMessage
from echo_masque.connector_runtime import DiscordConnectorRuntime
from echo_masque.smart_output import DiscordActionParticipant, SmartOutputContext


def request() -> DiscordInboundMessage:
    return DiscordInboundMessage(
        connection_id="connection-1",
        deployment_id="deployment-1",
        message_id="message-1",
        guild_id="guild-1",
        channel_id="channel-1",
        author_id="123456789012345678",
        author_display_name="Juen",
        text="What do you think?",
        mentioned_bot=True,
        mentionable_participants=[
            DiscordActionParticipant(
                ref="user:123456789012345678", display_name="Juen", kind="human"
            ),
            DiscordActionParticipant(
                ref="deployment:deployment-2", display_name="Ning", kind="character"
            ),
        ],
    )


def test_prompt_hides_ids_and_does_not_preload_resources() -> None:
    prompt = DiscordConnectorRuntime._social_prompt(character_name="Ann", payload=request())
    assert '"action":"short_message"' in prompt
    assert '"action":"react"' in prompt
    assert '"action":"sticker"' in prompt
    assert '"action":"ignore"' not in prompt
    assert "An expression is optional" in prompt
    assert "p1: Juen (human)" in prompt and "p2: Ning (character)" in prompt
    assert "123456789012345678" not in prompt and "deployment:deployment-2" not in prompt
    assert "CR_EXPRESSION" not in prompt
    assert "e1; type=" not in prompt


def test_legacy_resource_control_is_not_executed_as_a_modern_proposal() -> None:
    context = SmartOutputContext.from_payload(request(), character_name="Ann")
    output, reason = context.parse_and_resolve(
        '[[CR_EXPRESSION {"action":"reaction","resource_key":"emoji:123"}]]'
    )
    assert output is None and reason == "missing_smart_output_control"
    output, reason = context.parse_and_resolve(
        '[[CR_OUTPUT {"action":"react","target":"trigger","emoji":"e1"}]]'
    )
    assert output is None and reason == "invalid_smart_output_control"
