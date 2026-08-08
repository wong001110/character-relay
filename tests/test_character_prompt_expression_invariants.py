from echo_masque.character_prompts import (
    CHARACTER_PROMPT_COMPILER_VERSION,
    CharacterPromptProfile,
    compile_character_prompt,
)


def test_compiled_prompt_forbids_visible_expression_placeholders() -> None:
    compiled = compile_character_prompt(
        "Stay in character.",
        CharacterPromptProfile(
            display_name="Mia Bell",
            persona_summary="Playful and expressive.",
        ),
    )

    assert CHARACTER_PROMPT_COMPILER_VERSION == "character-relay-compiler-v3"
    assert compiled.compiler_version == CHARACTER_PROMPT_COMPILER_VERSION
    assert "never write a textual placeholder for an expression" in compiled.compiled_system_prompt
    assert "[question-mark expression]" in compiled.compiled_system_prompt
    assert "structured output resource reference" in compiled.compiled_system_prompt
    assert "never invent a Discord resource ID" in compiled.compiled_system_prompt
    assert "proposals" in compiled.compiled_system_prompt
