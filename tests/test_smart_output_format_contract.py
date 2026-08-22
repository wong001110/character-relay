from echo_masque.api.expression_schemas import ExpressionCandidate
from echo_masque.smart_output import SmartOutputContext
from echo_masque.targets.prompt_model import PromptModelTarget


def _context(*, admitted: bool = False) -> SmartOutputContext:
    return SmartOutputContext(
        message_alias_to_id={"trigger": "message-1"},
        message_id_to_alias={"message-1": "trigger"},
        participant_alias_to_ref={},
        participant_ref_to_name={},
        participant_alias_descriptions=(),
        participation_required=admitted,
    )


def _emoji() -> ExpressionCandidate:
    return ExpressionCandidate(
        resource_key="emoji:plead",
        resource_type="emoji",
        resource_id="plead",
        name="plead",
        animated=False,
        available=True,
        enabled=True,
        allowed_actions=["inline", "reaction"],
        semantic_intent="pleading",
        semantic_emotion="nervous",
        semantic_description="tearful pleading reaction",
        semantic_source="manual",
        semantic_confidence=1.0,
        asset_url="https://cdn.example.test/plead.png",
        format_type="png",
        score=0.9,
    )


def test_compact_smart_output_prompt_requires_separate_inline_emoji_items() -> None:
    guidance = "\n".join(_context().prompt_guidance([_emoji()]))

    assert "Each item must contain exactly one of: text, emoji, mention" in guidance
    assert "custom Server Emoji in message content must use an Emoji alias" in guidance
    assert '{"text":"这句我不同意。 "},{"emoji":"e1"}' in guidance
    assert "Do not emit reasoning" in guidance


def test_compact_admitted_prompt_removes_ignore_and_offers_short_message() -> None:
    guidance = "\n".join(_context(admitted=True).prompt_guidance([]))

    assert "Available actions: message, short_message." in guidance
    assert "already admitted" in guidance
    assert "Silence/ignore is not an available action" in guidance
    assert '"action":"ignore"' not in guidance
    assert '"action":"short_message"' in guidance


def test_format_retry_is_compact_and_explicitly_forbids_rewriting_answer() -> None:
    original = "\n".join(
        (
            "FULL CHARACTER PROMPT",
            "Return Smart Output now.",
            "Your previous Smart Output was rejected (invalid_smart_output_control).",
            "Regenerate once. Return exactly one valid [[CR_OUTPUT {...}]] line and nothing else.",
        )
    )

    repaired = PromptModelTarget._compact_format_repair(original)

    assert "FULL CHARACTER PROMPT" not in repaired
    assert "Formatting repair only" in repaired
    assert "do not add reasoning, facts, or a new answer" in repaired
    assert '{"emoji":"eN"}' in repaired
    assert "Never place an Emoji or Mention JSON object inside a text string" in repaired
    assert len(repaired) < 500
