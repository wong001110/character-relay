from pathlib import Path

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select

from echo_masque.api import create_app
from echo_masque.auth import SYSTEM_RUNTIME_USER_ID
from echo_masque.config import Settings
from echo_masque.credentials import CredentialVault
from echo_masque.persistence.models import AuditEventRecord

ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "correct horse battery staple"


def settings(path: Path, keys: str) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{path}",
        legacy_local_user_enabled=False,
        public_registration_enabled=True,
        bootstrap_admin_email=ADMIN_EMAIL,
        bootstrap_admin_password=SecretStr(ADMIN_PASSWORD),
        credential_encryption_keys=SecretStr(keys),
    )


def login_admin(client: TestClient) -> dict[str, object]:
    response = client.post(
        "/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200
    assert response.json()["user"]["role"] == "admin"
    return response.json()


def enable_runtime(client: TestClient) -> None:
    current = client.get("/api/admin/runtime")
    assert current.status_code == 200
    config = current.json()["config"]
    config["adaptive"]["enabled"] = True
    config["judge"]["enabled"] = True
    config["default_judge_mode"] = "hybrid"
    updated = client.put("/api/admin/runtime", json=config)
    assert updated.status_code == 200


def test_admin_role_and_runtime_credentials_use_encrypted_vault(tmp_path: Path) -> None:
    database_path = tmp_path / "admin-vault.db"
    key = Fernet.generate_key().decode("ascii")
    resolved = settings(database_path, key)
    app = create_app(resolved)
    admin = TestClient(app)
    member = TestClient(app)
    login_admin(admin)

    registered = member.post(
        "/api/auth/register",
        json={
            "email": "member@example.com",
            "display_name": "Member",
            "password": ADMIN_PASSWORD,
        },
    )
    assert registered.status_code == 201
    assert member.get("/api/admin/runtime").status_code == 403
    assert member.get(
        "/api/admin/runtime",
        headers={"X-Echo-Admin": "ignored-in-session-mode"},
    ).status_code == 403

    enable_runtime(admin)
    adaptive_secret = "adaptive-secret-never-store-in-plaintext"
    judge_secret = "judge-secret-never-store-in-plaintext"
    adaptive = admin.put(
        "/api/admin/runtime/credentials/adaptive",
        json={"api_key": adaptive_secret},
    )
    judge = admin.put(
        "/api/admin/runtime/credentials/judge",
        json={"api_key": judge_secret},
    )
    assert adaptive.status_code == 200
    assert judge.status_code == 200
    status = judge.json()["status"]
    assert status["adaptive"]["credential_source"] == "vault"
    assert status["judge"]["credential_source"] == "vault"
    assert status["adaptive"]["configured"] is True
    assert status["judge"]["configured"] is True

    repository = app.state.auth_repository
    for kind, secret in (("adaptive", adaptive_secret), ("judge", judge_secret)):
        record = repository.get_credential(
            owner_id=SYSTEM_RUNTIME_USER_ID,
            scope_kind=CredentialVault.runtime_scope_kind,
            scope_id=kind,
        )
        assert record is not None
        assert secret not in record.encrypted_value
        assert secret.encode("utf-8") not in database_path.read_bytes()

    restarted = TestClient(create_app(resolved))
    login_admin(restarted)
    persisted = restarted.get("/api/admin/runtime")
    assert persisted.status_code == 200
    assert persisted.json()["status"]["adaptive"]["credential_source"] == "vault"
    assert persisted.json()["status"]["judge"]["credential_source"] == "vault"
    assert persisted.json()["status"]["adaptive"]["configured"] is True
    assert persisted.json()["status"]["judge"]["configured"] is True

    with restarted.app.state.database.session() as session:
        actions = set(session.scalars(select(AuditEventRecord.action)))
    assert "admin_runtime.updated" in actions
    assert "credential.configured" in actions


def test_vault_rotation_reencrypts_runtime_credentials_for_new_primary_key(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "rotation.db"
    old_key = Fernet.generate_key().decode("ascii")
    new_key = Fernet.generate_key().decode("ascii")

    first = TestClient(create_app(settings(database_path, old_key)))
    login_admin(first)
    enable_runtime(first)
    configured = first.put(
        "/api/admin/runtime/credentials/adaptive",
        json={"api_key": "runtime-key-for-rotation"},
    )
    assert configured.status_code == 200
    old_record = first.app.state.auth_repository.get_credential(
        owner_id=SYSTEM_RUNTIME_USER_ID,
        scope_kind=CredentialVault.runtime_scope_kind,
        scope_id="adaptive",
    )
    assert old_record is not None
    old_version = old_record.key_version
    old_ciphertext = old_record.encrypted_value

    transition = TestClient(create_app(settings(database_path, f"{new_key},{old_key}")))
    login_admin(transition)
    rotated = transition.post("/api/admin/credentials/rotate")
    assert rotated.status_code == 200
    assert rotated.json()["rotated_count"] >= 1
    assert rotated.json()["key_version"] != old_version

    new_record = transition.app.state.auth_repository.get_credential(
        owner_id=SYSTEM_RUNTIME_USER_ID,
        scope_kind=CredentialVault.runtime_scope_kind,
        scope_id="adaptive",
    )
    assert new_record is not None
    assert new_record.key_version == rotated.json()["key_version"]
    assert new_record.encrypted_value != old_ciphertext

    final = TestClient(create_app(settings(database_path, new_key)))
    login_admin(final)
    status = final.get("/api/admin/runtime").json()["status"]
    assert status["adaptive"]["credential_source"] == "vault"
    assert status["adaptive"]["configured"] is True
