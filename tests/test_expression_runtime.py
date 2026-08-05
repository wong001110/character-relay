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
    assert invalid_text == "Reply\n[[CR_EXPRESSION not-json]]"
    assert invalid.action == "none"
