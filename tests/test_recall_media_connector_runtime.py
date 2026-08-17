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
