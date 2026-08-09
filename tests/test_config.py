from typing import Any

from echo_masque.config import Settings


def test_default_settings_require_no_credentials() -> None:
    settings = Settings(environment="test")
    assert settings.environment == "test"
    assert not hasattr(settings, "api_key")


def test_discord_tool_token_uses_connector_env_name(monkeypatch: Any) -> None:
    monkeypatch.delenv("ECHO_MASQUE_DISCORD_TOOL_BOT_TOKEN", raising=False)
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "shared-discord-token")

    settings = Settings(environment="test")

    assert settings.discord_tool_bot_token is not None
    assert settings.discord_tool_bot_token.get_secret_value() == "shared-discord-token"


def test_legacy_discord_tool_token_env_remains_migration_fallback(monkeypatch: Any) -> None:
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    monkeypatch.setenv("ECHO_MASQUE_DISCORD_TOOL_BOT_TOKEN", "legacy-discord-token")

    settings = Settings(environment="test")

    assert settings.discord_tool_bot_token is not None
    assert settings.discord_tool_bot_token.get_secret_value() == "legacy-discord-token"
