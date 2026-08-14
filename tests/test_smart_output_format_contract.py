from echo_masque.api.expression_schemas import ExpressionCandidate
from echo_masque.prompt_budget import BudgetSmartOutputContext
from echo_masque.targets.prompt_model import PromptModelTarget


def _context() -> BudgetSmartOutputContext:
    return BudgetSmartOutputContext(
        message_alias_to_id={"trigger": "message-1"},
        message_id_to_alias={"message-1": "trigger"},
        participant_alias_to_ref={},
        participant_ref_to_name={},
        participant_alias_descriptions=(),
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

    assert "every array item must be one separate JSON object" in guidance
    assert "inline Emoji MUST be its own content-array item" in guidance
    assert '{"text":"前面的文字 "},{"emoji":"e1"},{"text":" 后面的文字"}' in guidance
    assert "Never write an Emoji object inside a text value" in guidance


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
    assert "Do not add new reasoning, facts, or a new answer" in repaired
    assert '{"emoji":"eN"}' in repaired
    assert "Never place an Emoji or Mention JSON object inside a text string" in repaired
