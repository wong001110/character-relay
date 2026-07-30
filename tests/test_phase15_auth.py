from pathlib import Path

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr

from echo_masque.api import create_app
from echo_masque.config import Settings


def settings(path: Path, key: str) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{path}",
        legacy_local_user_enabled=False,
        credential_encryption_keys=SecretStr(key),
    )


def register(client: TestClient, email: str) -> dict[str, object]:
    response = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "display_name": email.split("@", maxsplit=1)[0],
            "password": "correct horse battery staple",
        },
    )
    assert response.status_code == 201
    return response.json()


def character_payload(
    name: str, target_id: str = "demo-stable"
) -> dict[str, object]:
    return {
        "target_id": target_id,
        "display_name": name,
        "subtitle": "Phase 15 isolation target",
        "subject_type": "companion",
        "persona_summary": "A private test character.",
        "traits": ["private"],
        "tags": ["phase15"],
        "expected_tone": "Calm",
        "forbidden_behaviors": ["cross-user leakage"],
        "memory_summary": "Private workspace only.",
        "preferred_suites": ["identity_integrity"],
        "portrait_variant": "lavender",
    }


def prompt_payload(secret: str) -> dict[str, object]:
    return {
        **character_payload("Encrypted Ann"),
        "provider": "deepseek",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-v4-flash",
        "system_prompt": "You are Encrypted Ann.",
        "temperature": 0.3,
        "api_key": secret,
    }


def test_authenticated_character_library_ignores_spoofed_owner_header(tmp_path: Path) -> None:
    key = Fernet.generate_key().decode("ascii")
    app = create_app(settings(tmp_path / "isolation.db", key))
    alice = TestClient(app)
    bob = TestClient(app)

    alice_auth = register(alice, "alice@example.com")
    bob_auth = register(bob, "bob@example.com")
    assert alice_auth["user"]["id"] != bob_auth["user"]["id"]

    target_response = alice.post(
        "/api/targets",
        json={"name": "Alice Target", "target_kind": "stable", "config": {}},
    )
    assert target_response.status_code == 201
    alice_target = target_response.json()

    created = alice.post(
        "/api/characters",
        headers={"X-Echo-User": str(bob_auth["user"]["id"])},
        json=character_payload("Alice Ann", str(alice_target["id"])),
    )
    assert created.status_code == 201
    card = created.json()
    assert card["owner_id"] == alice_auth["user"]["id"]

    assert bob.get("/api/characters").json() == []
    assert bob.get(f"/api/characters/{card['id']}").status_code == 404

    alice_targets = alice.get("/api/targets").json()
    bob_targets = bob.get("/api/targets").json()
    alice_target_ids = {item["id"] for item in alice_targets}
    bob_target_ids = {item["id"] for item in bob_targets}
    assert card["target_id"] in alice_target_ids
    assert card["target_id"] not in bob_target_ids
    assert bob.get(f"/api/targets/{card['target_id']}").status_code == 404

    anonymous = TestClient(app)
    assert anonymous.get("/api/characters").status_code == 401


def test_session_can_be_listed_and_revoked(tmp_path: Path) -> None:
    key = Fernet.generate_key().decode("ascii")
    client = TestClient(create_app(settings(tmp_path / "sessions.db", key)))
    register(client, "session@example.com")

    sessions = client.get("/api/auth/sessions")
    assert sessions.status_code == 200
    current = next(item for item in sessions.json() if item["current"])

    revoked = client.delete(f"/api/auth/sessions/{current['id']}")
    assert revoked.status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_provider_credential_is_encrypted_and_survives_restart(tmp_path: Path) -> None:
    database_path = tmp_path / "vault.db"
    key = Fernet.generate_key().decode("ascii")
    resolved = settings(database_path, key)
    first = TestClient(create_app(resolved))
    auth = register(first, "vault@example.com")
    secret = "provider-secret-that-must-never-enter-sqlite"

    created = first.post("/api/characters/prompt-model", json=prompt_payload(secret))
    assert created.status_code == 201
    card = created.json()
    record = first.app.state.auth_repository.get_credential(
        owner_id=str(auth["user"]["id"]),
        scope_kind="character_provider",
        scope_id=str(card["id"]),
    )
    assert record is not None
    assert secret not in record.encrypted_value
    assert secret.encode("utf-8") not in database_path.read_bytes()

    restarted = TestClient(create_app(resolved))
    login = restarted.post(
        "/api/auth/login",
        json={
            "email": "vault@example.com",
            "password": "correct horse battery staple",
        },
    )
    assert login.status_code == 200
    status_response = restarted.get(f"/api/characters/{card['id']}/credential")
    assert status_response.json() == {
        "required": True,
        "configured": True,
        "source": "memory",
    }
