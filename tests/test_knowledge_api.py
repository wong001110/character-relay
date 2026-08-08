from pathlib import Path

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr

from echo_masque.api import create_app
from echo_masque.config import Settings

ADMIN_EMAIL = "knowledge-admin@example.com"
ADMIN_PASSWORD = "CharacterRelayKnowledge2026!"


def settings(path: Path) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{path}",
        legacy_local_user_enabled=False,
        bootstrap_admin_email=ADMIN_EMAIL,
        bootstrap_admin_password=SecretStr(ADMIN_PASSWORD),
        bootstrap_admin_display_name="Knowledge Admin",
        credential_encryption_keys=SecretStr(Fernet.generate_key().decode("ascii")),
    )


def login(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200, response.text


def create_character(client: TestClient) -> str:
    response = client.post(
        "/api/characters/stable",
        json={
            "display_name": "Ann",
            "subtitle": "RAG test character",
            "subject_type": "companion",
            "persona_summary": "A test character for scoped RAG.",
            "traits": ["calm"],
            "tags": ["rag"],
            "expected_tone": "Concise.",
            "forbidden_behaviors": ["invent facts"],
            "memory_summary": "Server knowledge stays isolated.",
            "preferred_suites": ["identity_integrity"],
            "portrait_variant": "lavender",
        },
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def test_knowledge_api_create_chunk_retrieve_and_delete(tmp_path: Path) -> None:
    client = TestClient(create_app(settings(tmp_path / "knowledge.db")))
    login(client)
    character_id = create_character(client)

    created = client.post(
        "/api/knowledge/bases",
        json={
            "name": "Guild A FAQ",
            "description": "Server-specific launch information.",
            "scope_type": "server",
            "connection_id": "connection-a",
            "guild_id": "guild-a",
            "channel_id": "",
            "thread_id": "",
            "character_card_id": character_id,
            "enabled": True,
        },
    )
    assert created.status_code == 201, created.text
    base = created.json()

    document = client.post(
        f"/api/knowledge/bases/{base['id']}/documents",
        json={
            "title": "Launch FAQ",
            "content": "The Guild A launch phrase is silver comet. Use it for the demo launch.",
        },
    )
    assert document.status_code == 201, document.text
    document_view = document.json()
    assert document_view["chunk_count"] == 1
    assert document_view["content_chars"] > 20

    retrieved = client.post(
        "/api/knowledge/retrieve",
        json={
            "query": "What is the launch phrase?",
            "connection_id": "connection-a",
            "guild_id": "guild-a",
            "channel_id": "channel-1",
            "thread_id": "",
            "character_card_id": character_id,
            "top_k": 4,
        },
    )
    assert retrieved.status_code == 200, retrieved.text
    result = retrieved.json()
    assert result["eligible_base_count"] == 1
    assert result["hits"]
    assert "silver comet" in result["hits"][0]["content"]

    wrong_guild = client.post(
        "/api/knowledge/retrieve",
        json={
            "query": "launch phrase",
            "connection_id": "connection-a",
            "guild_id": "guild-b",
            "channel_id": "channel-1",
            "thread_id": "",
            "character_card_id": character_id,
            "top_k": 4,
        },
    )
    assert wrong_guild.status_code == 200
    assert wrong_guild.json()["eligible_base_count"] == 0
    assert wrong_guild.json()["hits"] == []

    documents = client.get(f"/api/knowledge/bases/{base['id']}/documents")
    assert documents.status_code == 200
    assert [item["id"] for item in documents.json()] == [document_view["id"]]

    deleted_document = client.delete(f"/api/knowledge/documents/{document_view['id']}")
    assert deleted_document.status_code == 204
    assert client.get(f"/api/knowledge/bases/{base['id']}/documents").json() == []

    deleted_base = client.delete(f"/api/knowledge/bases/{base['id']}")
    assert deleted_base.status_code == 204
    assert client.get("/api/knowledge/bases").json() == []


def test_knowledge_api_rejects_invalid_cross_scope_fields(tmp_path: Path) -> None:
    client = TestClient(create_app(settings(tmp_path / "knowledge-scope.db")))
    login(client)

    invalid = client.post(
        "/api/knowledge/bases",
        json={
            "name": "Invalid global base",
            "description": "",
            "scope_type": "global",
            "connection_id": "connection-a",
            "guild_id": "guild-a",
            "channel_id": "",
            "thread_id": "",
            "character_card_id": "",
            "enabled": True,
        },
    )
    assert invalid.status_code == 422
