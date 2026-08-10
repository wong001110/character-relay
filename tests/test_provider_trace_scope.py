from pathlib import Path
from typing import Any

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr

from echo_masque.api import create_app
from echo_masque.api.provider_trace_schemas import ProviderTraceSummary
from echo_masque.config import Settings
from echo_masque.providers import OpenAICompatibleProvider

EMAIL = "trace-scope-admin@example.com"
PASSWORD = "TraceScopeAdmin2026!"
CONNECTOR_SECRET = "trace-scope-connector-secret"


def settings(path: Path, *, langgraph_mode: str = "off") -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{path}",
        legacy_local_user_enabled=False,
        bootstrap_admin_email=EMAIL,
        bootstrap_admin_password=SecretStr(PASSWORD),
        credential_encryption_keys=SecretStr(Fernet.generate_key().decode("ascii")),
        connector_shared_secret=SecretStr(CONNECTOR_SECRET),
        langgraph_mode=langgraph_mode,  # type: ignore[arg-type]
    )


def login(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
    )
    assert response.status_code == 200, response.text


@pytest.mark.parametrize("langgraph_mode", ["off", "character_turn"])
def test_discord_provider_traces_inherit_deployment_account_scope(
    tmp_path: Path,
    langgraph_mode: str,
) -> None:
    app = create_app(
        settings(
            tmp_path / f"provider-trace-scope-{langgraph_mode}.db",
            langgraph_mode=langgraph_mode,
        )
    )
    client = TestClient(app)
    login(client)

    character = client.post(
        "/api/characters/prompt-model",
        json={
            "display_name": "Scoped Mia",
            "subtitle": "Trace scope fixture",
            "subject_type": "assistant",
            "persona_summary": "A concise Discord assistant.",
            "traits": ["concise"],
            "tags": ["trace"],
            "expected_tone": "Short.",
            "forbidden_behaviors": [],
            "memory_summary": None,
            "preferred_suites": ["identity_integrity"],
            "portrait_variant": "mint",
            "provider": "deepseek",
            "base_url": "https://api.deepseek.com",
            "model": "deepseek-v4-flash",
            "system_prompt": "You are Mia.",
            "temperature": 0.2,
            "api_key": "test-provider-key",
        },
    )
    assert character.status_code == 201, character.text

    connection = client.post(
        "/api/connections",
        json={
            "platform": "discord",
            "display_name": "Trace Discord",
            "connection_mode": "managed",
            "external_account_id": "trace-bot",
            "status": "connected",
            "metadata": {},
        },
    )
    assert connection.status_code == 201, connection.text

    deployment = client.post(
        "/api/deployments",
        json={
            "character_card_id": character.json()["id"],
            "connection_id": connection.json()["id"],
            "workspace_id": "guild-trace",
            "workspace_name": "Trace Guild",
            "channel_id": "channel-trace",
            "channel_name": "trace-room",
            "thread_id": "",
            "thread_name": "",
            "participation_mode": "mention_and_reply",
            "memory_scope": "channel_isolated",
            "version_label": "Current",
            "sticker_count": 0,
            "status": "active",
        },
    )
    assert deployment.status_code == 201, deployment.text

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "deepseek-v4-flash",
                "choices": [
                    {
                        "message": {"content": "Hello from Mia."},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 4},
            },
        )

    def provider_factory(_base_url: str, api_key: SecretStr) -> OpenAICompatibleProvider:
        return OpenAICompatibleProvider(
            base_url="https://api.deepseek.com",
            api_key=api_key,
            transport=httpx.MockTransport(handler),
            max_retries=0,
        )

    app.state.discord_connector_runtime.provider_factory = provider_factory

    inbound: dict[str, Any] = {
        "connection_id": connection.json()["id"],
        "deployment_id": deployment.json()["id"],
        "message_id": "message-trace-1",
        "guild_id": "guild-trace",
        "guild_name": "Trace Guild",
        "channel_id": "channel-trace",
        "channel_name": "trace-room",
        "category_id": "",
        "thread_id": "",
        "thread_name": "",
        "author_id": "user-trace",
        "author_display_name": "Juen",
        "text": "Mia, hello",
        "mentioned_bot": True,
        "replied_to_bot": False,
        "smart_candidate": False,
        "recent_messages": [
            {
                "message_id": "message-trace-1",
                "author_id": "user-trace",
                "author_display_name": "Juen",
                "text": "Mia, hello",
                "is_bot": False,
            }
        ],
    }
    response = client.post(
        "/api/connectors/discord/messages",
        json=inbound,
        headers={"Authorization": f"Bearer {CONNECTOR_SECRET}"},
    )
    assert response.status_code == 200, response.text

    user = app.state.auth_repository.get_user_by_email(EMAIL)
    assert user is not None
    traces = app.state.provider_trace_repository.list_traces(owner_id=user.id, limit=20)
    assert traces
    summaries = [ProviderTraceSummary.from_record(item) for item in traces]
    assert all(item.owner_id == user.id for item in summaries)
    assert all(item.deployment_id == deployment.json()["id"] for item in summaries)
    assert all(item.character_card_id == character.json()["id"] for item in summaries)
