import asyncio
from pathlib import Path

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr

from echo_masque.api import create_app
from echo_masque.config import Settings
from echo_masque.providers import ChatMessage, ProviderCompletion
from echo_masque.targets import PromptModelConfig, PromptModelTarget

PASSWORD = "correct horse battery staple"
ADMIN_EMAIL = "prompt-inspector-admin@example.com"
SYSTEM_PROMPT = "You are Ann. Preserve identity and never invent shared memories."
API_KEY = "prompt-inspector-secret-key"


class NeverProvider:
    async def complete(
        self,
        *,
        messages: tuple[ChatMessage, ...],
        model: str,
        temperature: float,
    ) -> ProviderCompletion:
        raise AssertionError("Prompt inspection must not call the Provider.")


def settings(path: Path) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{path}",
        legacy_local_user_enabled=False,
        public_registration_enabled=True,
        bootstrap_admin_email=ADMIN_EMAIL,
        bootstrap_admin_password=SecretStr(PASSWORD),
        credential_encryption_keys=SecretStr(Fernet.generate_key().decode("ascii")),
        request_limit_per_minute=1000,
    )


def login(client: TestClient, email: str, password: str = PASSWORD) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200


def register(client: TestClient, email: str) -> None:
    response = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "display_name": email.split("@", maxsplit=1)[0],
            "password": PASSWORD,
        },
    )
    assert response.status_code == 201


def create_prompt_character(client: TestClient) -> dict[str, object]:
    response = client.post(
        "/api/characters/prompt-model",
        json={
            "display_name": "Ann Prompt Fixture",
            "subtitle": "Exact Runtime Prompt fixture",
            "subject_type": "companion",
            "persona_summary": "A careful identity-stable companion.",
            "traits": ["calm", "careful"],
            "tags": ["prompt-inspector"],
            "expected_tone": "Warm and precise",
            "forbidden_behaviors": ["inventing memories"],
            "memory_summary": "Only confirmed memories are valid.",
            "preferred_suites": ["identity_integrity", "false_memory"],
            "portrait_variant": "lavender",
            "provider": "deepseek",
            "base_url": "https://api.deepseek.com",
            "model": "prompt-fixture-model",
            "system_prompt": SYSTEM_PROMPT,
            "temperature": 0.35,
            "api_key": API_KEY,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_prompt_inspector_matches_the_runtime_system_message(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "prompt.db"))
    client = TestClient(app)
    login(client, ADMIN_EMAIL)
    card = create_prompt_character(client)

    response = client.get(f"/api/characters/{card['id']}/prompt")
    assert response.status_code == 200
    prompt = response.json()
    assert prompt["system_prompt"] == SYSTEM_PROMPT
    assert prompt["messages"] == [{"role": "system", "content": SYSTEM_PROMPT}]
    assert prompt["provider"] == "deepseek"
    assert prompt["model"] == "prompt-fixture-model"
    assert prompt["temperature"] == 0.35
    assert prompt["prompt_version"] == 1
    assert prompt["config_hash"]
    assert API_KEY not in response.text

    record = app.state.repository.get_target(str(card["target_id"]))
    assert record is not None
    config = PromptModelConfig.model_validate_json(record.config_json)
    runtime = PromptModelTarget(config=config, provider=NeverProvider())
    asyncio.run(runtime.reset())
    assert runtime.history == (ChatMessage(role="system", content=SYSTEM_PROMPT),)
    assert runtime.history[0].content == prompt["system_prompt"]


def test_prompt_exports_are_secret_free_and_useful(tmp_path: Path) -> None:
    client = TestClient(create_app(settings(tmp_path / "exports.db")))
    login(client, ADMIN_EMAIL)
    card = create_prompt_character(client)

    expected = {
        "text": "text/plain",
        "markdown": "text/markdown",
        "json": "application/json",
        "openai": "application/json",
    }
    for export_format, content_type in expected.items():
        response = client.get(
            f"/api/characters/{card['id']}/prompt/export",
            params={"format": export_format},
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith(content_type)
        assert "attachment; filename=" in response.headers["content-disposition"]
        assert SYSTEM_PROMPT in response.text
        assert API_KEY not in response.text
        assert "encrypted_value" not in response.text

    openai = client.get(
        f"/api/characters/{card['id']}/prompt/export",
        params={"format": "openai"},
    ).json()
    assert openai == {
        "model": "prompt-fixture-model",
        "temperature": 0.35,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}],
    }


def test_prompt_inspection_is_owner_scoped_and_rejects_non_prompt_cards(
    tmp_path: Path,
) -> None:
    app = create_app(settings(tmp_path / "ownership.db"))
    admin = TestClient(app)
    member = TestClient(app)
    login(admin, ADMIN_EMAIL)
    register(member, "prompt-member@example.com")
    card = create_prompt_character(admin)

    assert member.get(f"/api/characters/{card['id']}/prompt").status_code == 404
    assert member.get(
        f"/api/characters/{card['id']}/prompt/export",
        params={"format": "json"},
    ).status_code == 404

    stable_target = next(
        item
        for item in admin.get("/api/targets").json()
        if item["target_kind"] == "stable"
    )
    deterministic = admin.post(
        "/api/characters",
        json={
            "target_id": stable_target["id"],
            "display_name": "Deterministic Fixture",
            "subtitle": "No Provider Prompt",
            "subject_type": "custom",
            "persona_summary": "Deterministic target fixture.",
            "traits": [],
            "tags": [],
            "expected_tone": None,
            "forbidden_behaviors": [],
            "memory_summary": None,
            "preferred_suites": ["identity_integrity"],
            "portrait_variant": "mint",
        },
    )
    assert deterministic.status_code == 201
    unavailable = admin.get(
        f"/api/characters/{deterministic.json()['id']}/prompt"
    )
    assert unavailable.status_code == 409
    assert "no Provider System Prompt" in unavailable.json()["detail"]
