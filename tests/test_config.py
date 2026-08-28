from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from echo_masque.config import Settings
from echo_masque.knowledge_object_storage import (
    FilesystemKnowledgeObjectStorage,
    ObjectStorageError,
    ObjectStorageUnavailable,
    object_storage_from_settings,
)


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


def test_knowledge_object_storage_defaults_to_unconfigured_private_r2_boundary() -> None:
    storage = object_storage_from_settings(Settings(environment="test"))

    with pytest.raises(ObjectStorageUnavailable, match="not configured"):
        storage.put_private(
            object_key="knowledge-fabric/source/aa/hash",
            content=b"source",
            content_type="text/plain",
            metadata={},
        )


def test_knowledge_object_storage_uses_only_explicit_private_filesystem_roots(
    tmp_path: Path,
) -> None:
    storage = object_storage_from_settings(
        Settings(
            environment="test",
            knowledge_object_storage_provider="local_filesystem",
            knowledge_object_storage_filesystem_path=str(tmp_path / "private-artifacts"),
        )
    )

    assert isinstance(storage, FilesystemKnowledgeObjectStorage)
    stored = storage.put_private(
        object_key="knowledge-fabric/source/aa/hash",
        content=b"source",
        content_type="text/plain",
        metadata={"source-id": "source"},
    )
    assert stored.provider == "local_filesystem"
    assert storage.get_private(object_key=stored.object_key) == b"source"
    assert storage.delete_private(object_key=stored.object_key)
    assert not storage.delete_private(object_key=stored.object_key)

    with pytest.raises(ObjectStorageError, match="object key is invalid"):
        storage.put_private(
            object_key="../outside",
            content=b"source",
            content_type="text/plain",
            metadata={},
        )


def test_knowledge_object_storage_filesystem_root_must_be_absolute() -> None:
    with pytest.raises(ValidationError, match="must be absolute"):
        Settings(
            environment="test",
            knowledge_object_storage_provider="local_filesystem",
            knowledge_object_storage_filesystem_path="relative/private-artifacts",
        )


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://account.r2.cloudflarestorage.com",
        "https://key:secret@account.r2.cloudflarestorage.com",
        "https://account.r2.cloudflarestorage.com?token=secret",
    ],
)
def test_knowledge_object_storage_endpoint_rejects_credentials_and_non_https(endpoint: str) -> None:
    with pytest.raises(ValidationError, match="credential-free HTTPS"):
        Settings(environment="test", knowledge_object_storage_endpoint=endpoint)
