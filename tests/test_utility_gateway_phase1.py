import json
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError

from echo_masque.admin_runtime import (
    RUNTIME_DEFAULTS_VERSION,
    UtilityGatewayProfile,
    UtilityProviderMember,
)
from echo_masque.api import create_app
from echo_masque.auth import SYSTEM_RUNTIME_USER_ID
from echo_masque.config import Settings
from echo_masque.credentials import CredentialVault

ADMIN_EMAIL = "utility-admin@example.com"
ADMIN_PASSWORD = "correct horse battery staple"


def settings(path: Path) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{path}",
        legacy_local_user_enabled=False,
        public_registration_enabled=True,
        bootstrap_admin_email=ADMIN_EMAIL,
        bootstrap_admin_password=SecretStr(ADMIN_PASSWORD),
        credential_encryption_keys=SecretStr(Fernet.generate_key().decode("ascii")),
    )


def login_admin(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200


def utility_member(member_id: str = "groq_free") -> dict[str, object]:
    return {
        "id": member_id,
        "name": "Groq free",
        "enabled": True,
        "provider": "groq",
        "base_url": "https://api.groq.com/openai",
        "model": "example-free-model",
        "capabilities": ["semantic_judge", "memory_intelligence"],
        "free_only": True,
        "priority": 20,
    }


def test_utility_gateway_rejects_duplicate_members_and_non_free_pool_members() -> None:
    member = UtilityProviderMember.model_validate(utility_member())

    with pytest.raises(ValidationError):
        UtilityGatewayProfile(members=(member, member))

    with pytest.raises(ValidationError):
        UtilityGatewayProfile(
            members=(member.model_copy(update={"id": "paid_member", "free_only": False}),)
        )


def test_admin_can_manage_utility_credentials_without_secret_echo(tmp_path: Path) -> None:
    database_path = tmp_path / "utility-gateway.db"
    app = create_app(settings(database_path))

    with TestClient(app) as client:
        registered = client.post(
            "/api/auth/register",
            json={
                "email": "utility-member@example.com",
                "display_name": "Member",
                "password": ADMIN_PASSWORD,
            },
        )
        assert registered.status_code == 201
        assert client.get("/api/admin/runtime/utility-credentials").status_code == 403

        login_admin(client)
        current = client.get("/api/admin/runtime")
        assert current.status_code == 200
        config = current.json()["config"]
        config["utility_gateway"]["members"] = [utility_member()]
        saved = client.put("/api/admin/runtime", json=config)
        assert saved.status_code == 200

        initial_status = client.get("/api/admin/runtime/utility-credentials")
        assert initial_status.status_code == 200
        assert initial_status.json() == [
            {"member_id": "groq_free", "configured": False, "source": "missing"}
        ]

        assert client.put(
            "/api/admin/runtime/utility-credentials/missing_member",
            json={"api_key": "not-used"},
        ).status_code == 404

        secret = "utility-secret-never-return-to-browser"
        configured = client.put(
            "/api/admin/runtime/utility-credentials/groq_free",
            json={"api_key": secret},
        )
        assert configured.status_code == 200
        assert configured.json() == {
            "member_id": "groq_free",
            "configured": True,
            "source": "vault",
        }
        assert secret not in configured.text
        assert secret not in client.get("/api/admin/runtime").text

        record = app.state.auth_repository.get_credential(
            owner_id=SYSTEM_RUNTIME_USER_ID,
            scope_kind=CredentialVault.runtime_scope_kind,
            scope_id="utility:groq_free",
        )
        assert record is not None
        assert secret not in record.encrypted_value
        assert secret.encode("utf-8") not in database_path.read_bytes()

        config = client.get("/api/admin/runtime").json()["config"]
        config["utility_gateway"]["members"] = []
        removed = client.put("/api/admin/runtime", json=config)
        assert removed.status_code == 200
        assert client.get("/api/admin/runtime/utility-credentials").json() == []
        assert app.state.auth_repository.get_credential(
            owner_id=SYSTEM_RUNTIME_USER_ID,
            scope_kind=CredentialVault.runtime_scope_kind,
            scope_id="utility:groq_free",
        ) is None


def test_runtime_migrates_pre_gateway_config_to_disabled_gateway(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "runtime-migration.db"))
    service = app.state.runtime_service
    current = service.config().model_dump(mode="json")
    current.pop("utility_gateway", None)
    current["defaults_version"] = RUNTIME_DEFAULTS_VERSION - 1
    service.repository.save_admin_runtime(current)

    migrated = service.config()
    assert migrated.defaults_version == RUNTIME_DEFAULTS_VERSION
    assert migrated.utility_gateway.enabled is False
    assert migrated.utility_gateway.members == ()

    stored = service.repository.get_admin_runtime()
    assert stored is not None
    stored_json = json.loads(stored.config_json)
    assert stored_json["defaults_version"] == RUNTIME_DEFAULTS_VERSION
    assert stored_json["utility_gateway"]["enabled"] is False


def test_runtime_migrates_retired_participation_tiebreak_capability(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "runtime-retired-capability.db"))
    service = app.state.runtime_service
    current = service.config().model_dump(mode="json")
    current["utility_gateway"] = {
        "enabled": True,
        "routing_strategy": "best_available",
        "members": [
            {
                "id": "mixed",
                "name": "Mixed",
                "enabled": True,
                "provider": "openrouter",
                "base_url": "https://offline.invalid",
                "model": "offline-model",
                "capabilities": ["semantic_judge", "participation_tiebreak"],
                "free_only": True,
                "priority": 1,
            },
            {
                "id": "retired-only",
                "name": "Retired",
                "enabled": True,
                "provider": "openrouter",
                "base_url": "https://offline.invalid",
                "model": "offline-model",
                "capabilities": ["participation_tiebreak"],
                "free_only": True,
                "priority": 2,
            },
        ],
        "paid_fallback": current["utility_gateway"]["paid_fallback"],
    }
    current["defaults_version"] = RUNTIME_DEFAULTS_VERSION - 1
    service.repository.save_admin_runtime(current)

    migrated = service.config()

    assert [member.id for member in migrated.utility_gateway.members] == ["mixed"]
    assert migrated.utility_gateway.members[0].capabilities == ("semantic_judge",)
    stored = service.repository.get_admin_runtime()
    assert stored is not None
    assert "participation_tiebreak" not in stored.config_json
