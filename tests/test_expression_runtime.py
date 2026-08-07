from echo_masque.api.connector_schemas import DiscordInboundMessage
from echo_masque.api.expression_schemas import ExpressionCandidate
from echo_masque.connector_runtime import DiscordConnectorRuntime


def candidate(
    *,
    key: str = "emoji:123456789012345678",
    actions: list[str] | None = None,
) -> ExpressionCandidate:
    resource_type, resource_id = key.split(":", maxsplit=1)
    return ExpressionCandidate(
        resource_key=key,
        resource_type=resource_type,
        resource_id=resource_id,
        name="peek",
        animated=False,
        available=True,
        enabled=True,
        allowed_actions=actions or ["inline", "reaction"],
        semantic_intent="curious_peek",
        semantic_emotion="curious",
        semantic_description="A curious and playful peek.",
        semantic_source="manual",
        semantic_confidence=1.0,
        asset_url="",
        format_type="emoji",
        score=0.9,
        signals={"semantic": 0.9},
    )


def test_expression_control_is_removed_from_visible_text() -> None:
    item = candidate()
    text, decision = DiscordConnectorRuntime._parse_expression_decision(
        'I am listening.\n[[CR_EXPRESSION {"action":"reaction",'
        '"resource_key":"emoji:123456789012345678","reason":"brief acknowledgement"}]]',
        [item],
    )
    assert text == "I am listening."
    assert decision.action == "reaction"
    assert decision.resource_key == item.resource_key


def test_expression_control_rejects_unknown_or_disallowed_resource() -> None:
    item = candidate(actions=["inline"])
    text, decision = DiscordConnectorRuntime._parse_expression_decision(
        'Hello\n[[CR_EXPRESSION {"action":"reaction",'
        '"resource_key":"emoji:123456789012345678","reason":"not allowed"}]]',
        [item],
    )
    assert text == "Hello"
    assert decision.action == "none"
    assert decision.reason == "expression_candidate_not_allowed"


def test_missing_or_invalid_control_defaults_to_none() -> None:
    plain_text, plain = DiscordConnectorRuntime._parse_expression_decision("Plain reply ✨", [])
    assert plain_text == "Plain reply ✨"
    assert plain.action == "none"
    assert plain.reason == "model_omitted_expression_control"

    invalid_text, invalid = DiscordConnectorRuntime._parse_expression_decision(
        "Reply\n[[CR_EXPRESSION not-json]]",
        [],
    )
    assert invalid_text == "Reply"
    assert invalid.action == "none"
    assert invalid.reason == "invalid_expression_control"


def test_expression_prompt_explains_social_meaning_without_reaction_bias() -> None:
    emoji = candidate()
    sticker = candidate(
        key="sticker:987654321098765432",
        actions=["sticker"],
    )
    payload = DiscordInboundMessage(
        connection_id="connection-1",
        deployment_id="deployment-1",
        message_id="message-1",
        guild_id="guild-1",
        guild_name="Test Guild",
        channel_id="channel-1",
        channel_name="general",
        author_id="user-1",
        author_display_name="Juen",
        text="你能使用一个 emoji 看看吗？",
        mentioned_bot=True,
        expression_candidates=[emoji, sticker],
    )

    prompt = DiscordConnectorRuntime._social_prompt(
        character_name="Serena Vale",
        payload=payload,
    )

    inline_example = '[[CR_EXPRESSION {"action":"inline","resource_key":"emoji:123"'
    reaction_example = '[[CR_EXPRESSION {"action":"reaction","resource_key":"emoji:456"'
    sticker_example = '[[CR_EXPRESSION {"action":"sticker","resource_key":"sticker:789"'
    none_example = '[[CR_EXPRESSION {"action":"none","reason":"not needed"}]]'

    assert "Expression controls are invisible runtime behavior." in prompt
    assert "When you already have a substantive visible reply" in prompt
    assert "prefer inline" in prompt
    assert "Do not default to reaction merely because it is available" in prompt
    assert "pressing or clicking an Emoji/reaction button" in prompt
    assert "without explaining the platform mechanism" in prompt
    assert inline_example in prompt
    assert reaction_example in prompt
    assert sticker_example in prompt
    assert none_example in prompt
    assert prompt.index(inline_example) < prompt.index(reaction_example)
