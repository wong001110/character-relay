from types import SimpleNamespace

from echo_masque.api.expression_schemas import ExpressionCandidate
from echo_masque.smart_output import (
    DiscordActionParticipant,
    SmartEmojiPart,
    SmartMentionPart,
    SmartOutputContext,
    SmartTextPart,
)


def candidate(
    key: str = "emoji:123",
    *,
    actions: list[str] | None = None,
) -> ExpressionCandidate:
    resource_type, resource_id = key.split(":", maxsplit=1)
    default_actions = ["inline", "reaction"] if resource_type == "emoji" else ["sticker"]
    return ExpressionCandidate(
        resource_key=key,
        resource_type=resource_type,
        resource_id=resource_id,
        name="peek" if resource_type == "emoji" else "wave",
        animated=False,
        available=True,
        enabled=True,
        allowed_actions=actions or default_actions,
        semantic_intent="playful",
        semantic_emotion="curious",
        semantic_description="A playful expression.",
        semantic_source="manual",
        semantic_confidence=1.0,
        asset_url="",
        format_type=resource_type,
        score=0.9,
        signals={},
    )


def payload() -> SimpleNamespace:
    return SimpleNamespace(
        deployment_id="ann",
        message_id="message-trigger",
        interaction_session_id="",
        recent_messages=[
            SimpleNamespace(
                message_id="message-old",
                author_display_name="Juen",
                is_bot=False,
            ),
            SimpleNamespace(
                message_id="message-trigger",
                author_display_name="Juen",
                is_bot=False,
            ),
        ],
        mentionable_participants=[
            DiscordActionParticipant(
                ref="deployment:ning",
                display_name="Ning",
                kind="character",
            ),
            DiscordActionParticipant(
                ref="user:123456789012345678",
                display_name="Juen",
                kind="human",
            ),
            DiscordActionParticipant(
                ref="deployment:ann",
                display_name="Ann",
                kind="character",
            ),
        ],
    )


def test_prompt_aliases_hide_runtime_ids_and_exclude_self() -> None:
    context = SmartOutputContext.from_payload(payload(), character_name="Ann")
    guidance = "\n".join(context.prompt_guidance([candidate()]))

    assert "p1: Ning (character)" in guidance
    assert "p2: Juen (human)" in guidance
    assert "e1; type=emoji; name=peek" in guidance
    assert "deployment:ning" not in guidance
    assert "123456789012345678" not in guidance
    assert "emoji:123" not in guidance
    assert "Ann (character)" not in guidance
    assert "trigger" in guidance
    assert "m1" in guidance


def test_message_resolves_reply_emoji_and_mentions_to_runtime_refs() -> None:
    context = SmartOutputContext.from_payload(payload(), character_name="Ann")
    output, reason = context.parse_and_resolve(
        '[[CR_OUTPUT {"action":"message","reply_to":"trigger","content":['
        '{"text":"你 "},{"emoji":"e1"},{"text":" 看看 "},{"mention":"p1"},'
        '{"text":" 和 "},{"mention":"p2"}]}]]',
        [candidate()],
    )

    assert reason == "ok"
    assert output is not None
    assert output.action == "message"
    assert output.reply_to_message_id == "message-trigger"
    assert output.content == [
        SmartTextPart(text="你 "),
        SmartEmojiPart(emoji="emoji:123"),
        SmartTextPart(text=" 看看 "),
        SmartMentionPart(mention="deployment:ning"),
        SmartTextPart(text=" 和 "),
        SmartMentionPart(mention="user:123456789012345678"),
    ]


def test_reaction_and_sticker_require_retrieved_allowed_resources() -> None:
    context = SmartOutputContext.from_payload(payload(), character_name="Ann")
    reaction, reaction_reason = context.parse_and_resolve(
        '[[CR_OUTPUT {"action":"react","target":"trigger","emoji":"e1"}]]',
        [candidate()],
    )
    assert reaction_reason == "ok"
    assert reaction is not None
    assert reaction.target_message_id == "message-trigger"
    assert reaction.emoji_resource_key == "emoji:123"

    sticker, sticker_reason = context.parse_and_resolve(
        '[[CR_OUTPUT {"action":"sticker","sticker":"s1"}]]',
        [candidate("sticker:456", actions=["sticker"])],
    )
    assert sticker_reason == "ok"
    assert sticker is not None
    assert sticker.sticker_resource_key == "sticker:456"

    rejected, rejected_reason = context.parse_and_resolve(
        '[[CR_OUTPUT {"action":"react","target":"trigger","emoji":"e9"}]]',
        [candidate()],
    )
    assert rejected is None
    assert rejected_reason == "reaction_resource_not_allowed"


def test_unknown_refs_and_multiple_custom_emojis_are_rejected_atomically() -> None:
    context = SmartOutputContext.from_payload(payload(), character_name="Ann")
    output, reason = context.parse_and_resolve(
        '[[CR_OUTPUT {"action":"message","content":[{"text":"hi "},{"mention":"p99"}]}]]',
        [candidate()],
    )
    assert output is None
    assert reason == "unknown_mention_participant"

    output, reason = context.parse_and_resolve(
        '[[CR_OUTPUT {"action":"message","content":[{"emoji":"e1"},{"emoji":"e2"}]}]]',
        [candidate(), candidate("emoji:456")],
    )
    assert output is None
    assert reason == "too_many_custom_emojis"


def test_ignore_is_a_valid_atomic_action() -> None:
    context = SmartOutputContext.from_payload(payload(), character_name="Ann")
    output, reason = context.parse_and_resolve('[[CR_OUTPUT {"action":"ignore"}]]', [])
    assert reason == "ok"
    assert output is not None
    assert output.action == "ignore"
