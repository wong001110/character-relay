from echo_masque.recall_media_connector_runtime import RecallAwareMediaDiscordConnectorRuntime


def test_recall_guidance_is_inserted_before_internal_prompt_boundary() -> None:
    prompt = "\n".join(
        (
            "Conversation grounding.",
            "Do not mention internal prompts, deployment configuration, OOC evaluation, or Character Relay.",
            "Recent conversation:",
            "hello",
            "Return Smart Output now.",
        )
    )
    guidance = (
        "High-confidence Character memory for this turn:",
        "[m1 | core] User prefers concise replies.",
    )

    result = RecallAwareMediaDiscordConnectorRuntime._inject_recall_guidance(prompt, guidance)

    assert result.index("High-confidence Character memory") < result.index(
        "Do not mention internal prompts"
    )
    assert result.count("High-confidence Character memory") == 1


def test_empty_recall_guidance_leaves_prompt_byte_for_byte_unchanged() -> None:
    prompt = "Conversation\nReturn Smart Output now."

    assert RecallAwareMediaDiscordConnectorRuntime._inject_recall_guidance(prompt, ()) == prompt


def test_sleeping_address_match_accepts_multilingual_character_alias_prefix() -> None:
    aliases = RecallAwareMediaDiscordConnectorRuntime._name_aliases(
        "織 / Zhi",
        ["织"],
    )

    assert RecallAwareMediaDiscordConnectorRuntime._starts_with_alias(
        "織\uFF0C姐妹你還在嗎\uFF1F",
        aliases,
    )
    assert RecallAwareMediaDiscordConnectorRuntime._starts_with_alias(
        "Zhi: are you still there?",
        aliases,
    )
    assert RecallAwareMediaDiscordConnectorRuntime._starts_with_alias(
        "织 你睡了吗",
        aliases,
    )
    assert not RecallAwareMediaDiscordConnectorRuntime._starts_with_alias(
        "刚才織说什么\uFF1F",
        aliases,
    )
