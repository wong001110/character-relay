from types import SimpleNamespace

from echo_masque.smart_output import (
    DiscordActionParticipant,
    SmartMentionPart,
    SmartOutputContext,
    SmartTextPart,
)


def payload(*, admitted: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        deployment_id="ann",
        message_id="message-trigger",
        runtime_target_message_id="",
        runtime_selection_origin="",
        interaction_session_id="",
        mentioned_bot=False,
        replied_to_bot=False,
        smart_candidate=admitted,
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
    guidance = "\n".join(context.prompt_guidance())

    assert "p1: Ning (character)" in guidance
    assert "p2: Juen (human)" in guidance
    assert "e1; type=emoji; name=peek" not in guidance
    assert "deployment:ning" not in guidance
    assert "123456789012345678" not in guidance
    assert "emoji:123" not in guidance
    assert "Ann (character)" not in guidance
    assert "trigger" in guidance
    assert "m1" in guidance


def test_message_resolves_mentions_but_leaves_expression_intent_for_runtime() -> None:
    context = SmartOutputContext.from_payload(payload(), character_name="Ann")
    output, reason = context.parse_and_resolve(
        '[[CR_OUTPUT {"action":"message","reply_to":"trigger","content":['
        '{"text":"你 "},{"text":" 看看 "},{"mention":"p1"},'
        '{"text":" 和 "},{"mention":"p2"}],"expression":'
        '{"kind":"emoji","intent":"tease","emotion":"amused"}}]]'
    )

    assert reason == "ok"
    assert output is not None
    assert output.action == "message"
    assert output.message_style == "normal"
    assert output.reply_to_message_id == "message-trigger"
    assert output.expression_resource is None
    assert output.expression_intent.intent == "tease"
    assert output.content == [
        SmartTextPart(text="你 "),
        SmartTextPart(text=" 看看 "),
        SmartMentionPart(mention="deployment:ning"),
        SmartTextPart(text=" 和 "),
        SmartMentionPart(mention="user:123456789012345678"),
    ]


def test_short_message_normalizes_to_message_with_short_style() -> None:
    context = SmartOutputContext.from_payload(payload(admitted=True), character_name="Ann")
    output, reason = context.parse_and_resolve(
        '[[CR_OUTPUT {"action":"short_message","content":[{"text":"ha?"}]}]]'
    )

    assert reason == "ok"
    assert output is not None
    assert output.action == "message"
    assert output.message_style == "short"
    assert output.content == [SmartTextPart(text="ha?")]


def test_short_message_rejects_long_text() -> None:
    context = SmartOutputContext.from_payload(payload(admitted=True), character_name="Ann")
    output, reason = context.parse_and_resolve(
        '[[CR_OUTPUT {"action":"short_message","content":[{"text":"' + ("a" * 281) + '"}]}]]'
    )

    assert output is None
    assert reason == "short_message_too_long"


def test_reaction_and_sticker_emit_only_intent_never_resource_authority() -> None:
    context = SmartOutputContext.from_payload(payload(), character_name="Ann")
    reaction, reason = context.parse_and_resolve(
        '[[CR_OUTPUT {"action":"react","target":"trigger",'
        '"expression":{"kind":"emoji","intent":"agree"}}]]'
    )
    assert reason == "ok"
    assert reaction is not None
    assert reaction.target_message_id == "message-trigger"
    assert not reaction.emoji_resource_key
    assert reaction.expression_intent.intent == "agree"
    sticker, reason = context.parse_and_resolve(
        '[[CR_OUTPUT {"action":"sticker","expression":{"kind":"sticker","intent":"thanks"}}]]'
    )
    assert reason == "ok" and sticker is not None
    assert not sticker.sticker_resource_key
    assert sticker.expression_intent.kind == "sticker"
    for extra in ('"emoji":"e1"', '"expression":{"kind":"emoji","intent":" "}'):
        output, reason = context.parse_and_resolve(
            '[[CR_OUTPUT {"action":"react","target":"trigger",' + extra + "}]]"
        )
        assert output is None and reason == "invalid_smart_output_control"


def test_direct_expression_needs_text_fallback_but_not_preloaded_catalogue() -> None:
    request = payload()
    request.mentioned_bot = True
    context = SmartOutputContext.from_payload(request, character_name="Ann")
    output, reason = context.parse_and_resolve(
        '[[CR_OUTPUT {"action":"react","target":"trigger",'
        '"expression":{"kind":"emoji","intent":"agree"}}]]'
    )
    assert output is None and reason == "direct_expression_requires_text_fallback"
    output, reason = context.parse_and_resolve(
        '[[CR_OUTPUT {"action":"react","target":"trigger",'
        '"expression":{"kind":"emoji","intent":"agree"},"fallback_text":"同意。"}]]'
    )
    assert reason == "ok" and output.fallback_text == "同意。"


def test_unknown_refs_and_multiple_custom_emojis_are_rejected_atomically() -> None:
    context = SmartOutputContext.from_payload(payload(), character_name="Ann")
    output, reason = context.parse_and_resolve(
        '[[CR_OUTPUT {"action":"message","content":[{"text":"hi "},{"mention":"p99"}]}]]'
    )
    assert output is None
    assert reason == "unknown_mention_participant"

    output, reason = context.parse_and_resolve(
        '[[CR_OUTPUT {"action":"message","content":[{"emoji":"e1"},{"emoji":"e2"}]}]]'
    )
    assert output is None
    assert reason == "invalid_smart_output_control"


def test_ignore_remains_valid_for_non_admitted_legacy_context() -> None:
    context = SmartOutputContext.from_payload(payload(), character_name="Ann")
    output, reason = context.parse_and_resolve('[[CR_OUTPUT {"action":"ignore"}]]')
    assert reason == "ok"
    assert output is not None
    assert output.action == "ignore"


def test_proactive_smart_candidate_can_choose_ignore() -> None:
    context = SmartOutputContext.from_payload(payload(admitted=True), character_name="Ann")
    guidance = "\n".join(context.prompt_guidance())

    assert context.proactive_candidate is True
    assert context.participation_required is False
    assert "not an obligation to speak" in guidance
    assert '"action":"ignore"' in guidance

    output, reason = context.parse_and_resolve('[[CR_OUTPUT {"action":"ignore"}]]')
    assert reason == "ok"
    assert output is not None
    assert output.action == "ignore"


def test_explicit_mention_and_reply_still_require_visible_action() -> None:
    mentioned = payload(admitted=True)
    mentioned.mentioned_bot = True
    replied = payload(admitted=True)
    replied.replied_to_bot = True

    mentioned_context = SmartOutputContext.from_payload(mentioned, character_name="Ann")
    replied_context = SmartOutputContext.from_payload(replied, character_name="Ann")

    assert mentioned_context.participation_required is True
    assert replied_context.participation_required is True
    for context in (mentioned_context, replied_context):
        guidance = "\n".join(context.prompt_guidance())
        assert "do not ignore it" in guidance
        assert '"action":"ignore"' not in guidance
        output, reason = context.parse_and_resolve('[[CR_OUTPUT {"action":"ignore"}]]')
        assert output is None
        assert reason == "admitted_turn_requires_visible_action"


def test_interaction_session_still_requires_visible_action() -> None:
    active = payload(admitted=True)
    active.interaction_session_id = "session-1"
    context = SmartOutputContext.from_payload(active, character_name="Ann")

    assert context.participation_required is True


def test_terminal_control_recovers_provider_prose_and_one_missing_bracket() -> None:
    context = SmartOutputContext.from_payload(payload(), character_name="Ann")
    raw = (
        "I found some useful results. Let me share a concise summary.\n\n"
        '[[CR_OUTPUT {"action":"message","reply_to":"trigger","content":'
        '[{"text":"I found several current AI developments worth noting."}]}]'
    )

    output, reason = context.parse_and_resolve(raw)

    assert reason == "ok"
    assert output is not None
    assert output.action == "message"
    assert output.reply_to_message_id == "message-trigger"
    assert output.content == [
        SmartTextPart(text="I found several current AI developments worth noting.")
    ]


def test_terminal_control_recovery_rejects_trailing_prose() -> None:
    context = SmartOutputContext.from_payload(payload(), character_name="Ann")
    raw = '[[CR_OUTPUT {"action":"message","content":[{"text":"hello"}]}]] extra text'

    output, reason = context.parse_and_resolve(raw)

    assert output is None
    assert reason == "missing_smart_output_control"
