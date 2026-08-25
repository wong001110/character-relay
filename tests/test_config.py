from typing import Any

from echo_masque.config import Settings


def test_default_settings_require_no_credentials() -> None:
    settings = Settings(environment="test")
    assert settings.environment == "test"
    assert not hasattr(settings, "api_key")


def test_character_relay_env_prefix_is_used(monkeypatch: Any) -> None:
    monkeypatch.setenv("CHARACTER_RELAY_LOG_LEVEL", "ERROR")

    settings = Settings(environment="test")

    assert settings.log_level == "ERROR"


def test_echo_masque_env_prefix_is_not_supported(monkeypatch: Any) -> None:
    monkeypatch.delenv("CHARACTER_RELAY_LOG_LEVEL", raising=False)
    monkeypatch.setenv("ECHO_MASQUE_LOG_LEVEL", "ERROR")

    settings = Settings(environment="test")

    assert settings.log_level == "INFO"


def test_retired_langgraph_boolean_env_does_not_enable_rollout(monkeypatch: Any) -> None:
    monkeypatch.delenv("CHARACTER_RELAY_LANGGRAPH_MODE", raising=False)
    monkeypatch.setenv("CHARACTER_RELAY_LANGGRAPH_ENABLED", "true")

    settings = Settings(environment="test")

    assert settings.langgraph_mode == "off"


def test_langgraph_mode_allows_its_configured_workflow_boundary() -> None:
    settings = Settings(environment="test", langgraph_mode="character_turn")

    assert settings.langgraph_allows("character_turn")
    assert settings.langgraph_allows("condition_watch")
    assert not settings.langgraph_allows("social_turn")


def test_discord_tool_token_uses_connector_env_name(monkeypatch: Any) -> None:
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "shared-discord-token")

    settings = Settings(environment="test")

    assert settings.discord_tool_bot_token is not None
    assert settings.discord_tool_bot_token.get_secret_value() == "shared-discord-token"
