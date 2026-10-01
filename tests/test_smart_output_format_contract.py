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


def test_prompt_uses_optional_intent_not_resource_aliases() -> None:
    guidance = "\n".join(_context().prompt_guidance())
    assert "An expression is optional" in guidance
    assert "Never invent aliases or resource IDs" in guidance
    assert '"expression":{"kind":"emoji","intent":"tease"' in guidance
    assert '"emoji":"e1"' not in guidance
    assert "without explanations or reasoning" in guidance


def test_direct_response_requires_visible_action_with_text_fallback() -> None:
    guidance = "\n".join(_context(admitted=True).prompt_guidance())
    assert '"action":"ignore"' not in guidance
    assert '"action":"short_message"' in guidance
    assert "fallback_text" in guidance
    output, reason = _context(admitted=True).parse_and_resolve('[[CR_OUTPUT {"action":"ignore"}]]')
    assert output is None and reason == "admitted_turn_requires_visible_action"


def test_format_retry_is_compact_and_forbids_rewriting_or_resource_authority() -> None:
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
    assert '"emoji":"eN"' not in repaired
    assert "Never invent resource IDs" in repaired
    assert "fallback_text" in repaired
    assert len(repaired) < 500
