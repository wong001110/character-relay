from echo_masque.recall_media_connector_runtime import RecallAwareMediaDiscordConnectorRuntime


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
