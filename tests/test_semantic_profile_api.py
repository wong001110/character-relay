from pathlib import Path

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr

from echo_masque.api import create_app
from echo_masque.config import Settings

ADMIN_EMAIL = "semantic-admin@example.com"
ADMIN_PASSWORD = "CharacterRelaySemantic2026!"


class FakeSemanticEncoder:
    model_name = "fake-multilingual-e5"
    dimension = 3

    def __init__(self) -> None:
        self.passage_calls = 0
        self.query_calls = 0

    def embed_passage(self, text: str) -> list[float]:
        self.passage_calls += 1
        normalized = text.casefold()
        if "support" in normalized:
            return [0.0, 1.0, 0.0]
        return [1.0, 0.0, 0.0]

    def embed_query(self, text: str) -> list[float]:
        self.query_calls += 1
        return [1.0, 0.0, 0.0]


def settings(path: Path) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{path}",
        legacy_local_user_enabled=False,
        bootstrap_admin_email=ADMIN_EMAIL,
        bootstrap_admin_password=SecretStr(ADMIN_PASSWORD),
        bootstrap_admin_display_name="Semantic Admin",
        credential_encryption_keys=SecretStr(Fernet.generate_key().decode("ascii")),
        semantic_participation_enabled=True,
        semantic_embedding_model="fake-multilingual-e5",
        semantic_embedding_dimension=3,
    )


def login(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200, response.text


def create_character(client: TestClient) -> dict[str, object]:
    response = client.post(
        "/api/characters/prompt-model",
        json={
            "display_name": "Zhi",
            "subtitle": "AI Product Producer",
            "subject_type": "custom",
            "persona_summary": "Turns ambiguous ideas into practical AI product workflows.",
            "traits": ["structured", "curious"],
            "tags": ["workflow", "product building"],
            "expected_tone": "Practical and concise.",
            "forbidden_behaviors": ["invent private memories"],
            "memory_summary": "Private memory should not enter participation semantics.",
            "preferred_suites": ["identity_integrity"],
            "portrait_variant": "lavender",
            "provider": "deepseek",
            "base_url": "https://api.deepseek.com",
            "model": "deepseek-v4-flash",
            "system_prompt": "You are Zhi.",
            "temperature": 0.4,
            "api_key": "test-provider-key",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_semantic_profile_is_optional_inspectable_and_refreshes_after_opt_in(
    tmp_path: Path,
) -> None:
    app = create_app(settings(tmp_path / "semantic-profile.db"))
    encoder = FakeSemanticEncoder()
    app.state.semantic_participation_service.replace_encoder_for_test(encoder)
    client = TestClient(app)
    login(client)

    card = create_character(client)
    card_id = str(card["id"])

    # Saving a Character Card alone must not create an embedding or load the model.
    assert encoder.passage_calls == 0
    initial = client.get(f"/api/smart-participation/semantic-profile/{card_id}")
    assert initial.status_code == 200, initial.text
    assert initial.json()["status"] == "not_created"
    assert initial.json()["created"] is False
    assert initial.json()["embedding_bytes"] == 0
    assert "Private memory" not in initial.json()["semantic_text"]
    assert encoder.passage_calls == 0

    # The user can explicitly opt in without creating any Deployment.
    created = client.post(f"/api/smart-participation/semantic-profile/{card_id}")
    assert created.status_code == 200, created.text
    payload = created.json()
    assert payload["status"] == "ready"
    assert payload["created"] is True
    assert payload["rebuilt"] is True
    assert payload["model_name"] == encoder.model_name
    assert payload["dimension"] == 3
    assert payload["embedding_bytes"] == 12
    assert encoder.passage_calls == 1

    current = client.get(f"/api/smart-participation/semantic-profile/{card_id}")
    assert current.status_code == 200, current.text
    assert current.json()["status"] == "ready"
    assert current.json()["rebuilt"] is False
    assert encoder.passage_calls == 1

    # Once a card has opted in, semantic edits keep its persisted profile current.
    updated = client.put(
        f"/api/characters/{card_id}",
        json={
            "display_name": "Zhi",
            "subtitle": "Companion",
            "subject_type": "custom",
            "persona_summary": "Offers practical support when someone feels overwhelmed.",
            "traits": ["supportive", "structured"],
            "tags": ["support"],
            "expected_tone": "Gentle and practical.",
            "forbidden_behaviors": [],
            "memory_summary": None,
            "preferred_suites": ["identity_integrity"],
            "portrait_variant": "lavender",
        },
    )
    assert updated.status_code == 200, updated.text
    assert encoder.passage_calls == 2

    refreshed = client.get(f"/api/smart-participation/semantic-profile/{card_id}")
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["status"] == "ready"
    assert refreshed.json()["embedding_bytes"] == 12
