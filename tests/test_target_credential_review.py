"""Owner credentials, never target-selected process environment, authorize requests."""

import asyncio
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from echo_masque.api import create_app
from echo_masque.config import Settings
from echo_masque.providers import ProviderAuthenticationError
from echo_masque.services.trials import TrialService
from echo_masque.targets import HttpTarget, HttpTargetConfig, PromptModelConfig


def test_prompt_trial_requires_card_owned_credential(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("REVIEW_FIXTURE_CREDENTIAL", "synthetic-unused-value")
    app = create_app(Settings(environment="test", database_url=f"sqlite:///{tmp_path / 'test.db'}"))
    app.state.trial_service.provider_factory = Mock(
        side_effect=AssertionError("Provider must not be constructed without owner credential")
    )
    client = TestClient(app)
    config = PromptModelConfig(
        name="Test character",
        provider="custom",
        model="fixture",
        base_url="https://provider.example",
        system_prompt="Synthetic test",
        api_key_env="REVIEW_FIXTURE_CREDENTIAL",
    )
    target = client.post(
        "/api/targets",
        json={
            "name": "Test character",
            "target_kind": "prompt_model",
            "config": config.model_dump(mode="json"),
        },
    )
    assert target.status_code == 201
    card = client.post(
        "/api/characters",
        json={
            "target_id": target.json()["id"],
            "display_name": "Test character",
        },
    )
    assert card.status_code == 201
    card_id = card.json()["id"]
    assert client.get(f"/api/characters/{card_id}/credential").json()["source"] == "missing"
    result = client.post(
        "/api/trials",
        json={
            "character_card_id": card_id,
            "suite": ["identity_integrity"],
        },
    )
    assert result.status_code == 422
    app.state.trial_service.provider_factory.assert_not_called()


def test_http_adapter_requires_explicit_secret_resolver(monkeypatch) -> None:
    monkeypatch.setenv("REVIEW_FIXTURE_CREDENTIAL", "synthetic-unused-value")

    async def forbidden_request(request: httpx.Request) -> httpx.Response:
        raise AssertionError("No HTTP request is allowed without an explicit credential")

    async def run() -> None:
        target = HttpTarget(
            name="Fixture",
            config=HttpTargetConfig(
                message_url="https://target.example/chat",
                auth_env="REVIEW_FIXTURE_CREDENTIAL",
            ),
            transport=httpx.MockTransport(forbidden_request),
        )
        try:
            with pytest.raises(ProviderAuthenticationError, match="credential is unavailable"):
                await target.send("Fixture request")
        finally:
            await target.close()

    asyncio.run(run())


def test_persisted_http_target_requires_scoped_credential() -> None:
    service = object.__new__(TrialService)
    config = HttpTargetConfig(message_url="https://target.example/chat", auth_env="legacy-label")
    with pytest.raises(ValueError, match="credential is no longer available"):
        service._target("http", "Fixture", config.model_dump_json(), None)


def test_http_character_supports_owner_vault_configuration(tmp_path: Path) -> None:
    app = create_app(Settings(environment="test", database_url=f"sqlite:///{tmp_path / 'http.db'}"))
    client = TestClient(app)
    target = client.post(
        "/api/targets",
        json={
            "name": "HTTP fixture",
            "target_kind": "http",
            "config": {"message_url": "https://target.example/chat", "auth_env": "legacy-label"},
        },
    )
    card = client.post(
        "/api/characters",
        json={
            "target_id": target.json()["id"],
            "display_name": "HTTP fixture",
        },
    )
    card_id = card.json()["id"]
    assert client.get(f"/api/characters/{card_id}/credential").json()["required"]
    configured = client.put(
        f"/api/characters/{card_id}/credential", json={"api_key": "synthetic-owner-key"}
    )
    assert configured.status_code == 200
    assert configured.json()["configured"]
    assert app.state.credential_store.get("local-user", card_id) == SecretStr("synthetic-owner-key")
