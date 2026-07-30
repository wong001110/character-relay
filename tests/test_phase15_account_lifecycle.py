from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select

from echo_masque.account_lifecycle import AccountLifecycleService
from echo_masque.api import create_app
from echo_masque.auth import AuthService, InvitationError
from echo_masque.config import Settings
from echo_masque.persistence import AuthRepository, Database
from echo_masque.persistence.models import AuditEventRecord, InvitationRecord

PASSWORD = "correct horse battery staple"
ADMIN_EMAIL = "admin@example.com"


def app_settings(path: Path) -> Settings:
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


def register(client: TestClient, email: str) -> dict[str, object]:
    response = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "display_name": email.split("@", maxsplit=1)[0],
            "password": PASSWORD,
        },
    )
    assert response.status_code == 201
    return response.json()


def character_payload(name: str) -> dict[str, object]:
    return {
        "target_id": "demo-stable",
        "display_name": name,
        "subtitle": "Lifecycle test card",
        "subject_type": "companion",
        "persona_summary": "Stable identity.",
        "traits": ["stable"],
        "tags": ["lifecycle"],
        "expected_tone": "Calm",
        "forbidden_behaviors": ["identity replacement"],
        "memory_summary": "Only confirmed facts.",
        "preferred_suites": ["identity_integrity"],
        "portrait_variant": "lavender",
    }


def test_production_invitation_registration_is_atomic_and_single_use(
    tmp_path: Path,
) -> None:
    database = Database(f"sqlite:///{tmp_path / 'invitation.db'}")
    database.initialize()
    repository = AuthRepository(database)
    admin = repository.create_user(
        email=ADMIN_EMAIL,
        display_name="Admin",
        password_hash="unused",
        role="admin",
    )
    lifecycle = AccountLifecycleService(database, repository)
    invitation, code = lifecycle.create_invitation(
        actor_user_id=admin.id,
        email="invited@example.com",
        role="user",
        expires_in_days=7,
    )
    auth = AuthService(
        repository,
        Settings(
            environment="production",
            database_url="sqlite://",
            public_registration_enabled=False,
        ),
    )

    user = auth.register(
        email="invited@example.com",
        display_name="Invited User",
        password=PASSWORD,
        invitation_code=code,
    )
    assert user.role == "user"
    assert code not in (tmp_path / "invitation.db").read_text(errors="ignore")
    with database.session() as session:
        stored = session.get(InvitationRecord, invitation.id)
        assert stored is not None
        assert stored.accepted_by == user.id
        assert stored.accepted_at is not None
    with pytest.raises(InvitationError):
        auth.register(
            email="other@example.com",
            display_name="Other",
            password=PASSWORD,
            invitation_code=code,
        )


def test_admin_invitation_roles_audit_and_local_workspace_claim(tmp_path: Path) -> None:
    app = create_app(app_settings(tmp_path / "admin-lifecycle.db"))
    admin = TestClient(app)
    member = TestClient(app)
    login(admin, ADMIN_EMAIL)
    member_auth = register(member, "member@example.com")
    member_id = str(member_auth["user"]["id"])

    created = admin.post(
        "/api/admin/invitations",
        json={"email": "future@example.com", "role": "admin", "expires_in_days": 3},
    )
    assert created.status_code == 201
    code = created.json()["code"]
    invitation_id = created.json()["invitation"]["id"]
    listed = admin.get("/api/admin/invitations")
    assert listed.status_code == 200
    assert code not in listed.text
    assert admin.delete(f"/api/admin/invitations/{invitation_id}").status_code == 204

    promoted = admin.put(
        f"/api/admin/users/{member_id}/role",
        json={"role": "admin"},
    )
    assert promoted.status_code == 200
    assert promoted.json()["role"] == "admin"
    demoted = admin.put(
        f"/api/admin/users/{member_id}/role",
        json={"role": "user"},
    )
    assert demoted.status_code == 200

    app.state.repository.create_character_card(
        owner_id="local-user",
        target_id="demo-stable",
        display_name="Legacy Ann",
        subtitle="Unclaimed",
        subject_type="companion",
        persona_summary="Legacy workspace data.",
        traits=["legacy"],
        tags=["claim"],
        expected_tone="Calm",
        forbidden_behaviors=[],
        memory_summary=None,
        preferred_suites=["identity_integrity"],
        portrait_variant="lavender",
    )
    claimed = admin.post(
        "/api/admin/workspace/claim-local",
        json={"confirmation": "CLAIM LOCAL WORKSPACE"},
    )
    assert claimed.status_code == 200
    assert claimed.json()["affected"]["characters"] == 1
    assert [item["display_name"] for item in admin.get("/api/characters").json()] == [
        "Legacy Ann"
    ]
    assert admin.post(
        "/api/admin/workspace/claim-local",
        json={"confirmation": "CLAIM LOCAL WORKSPACE"},
    ).status_code == 409

    audit = admin.get("/api/admin/audit")
    assert audit.status_code == 200
    actions = {item["action"] for item in audit.json()}
    assert "invitation.created" in actions
    assert "invitation.revoked" in actions
    assert "account.role_changed" in actions
    assert "workspace.local_claimed" in actions


def test_account_export_and_deletion_remove_sessions_credentials_and_workspace(
    tmp_path: Path,
) -> None:
    app = create_app(app_settings(tmp_path / "account-delete.db"))
    user = TestClient(app)
    auth = register(user, "delete@example.com")
    user_id = str(auth["user"]["id"])
    created = user.post("/api/characters", json=character_payload("Delete Ann"))
    assert created.status_code == 201

    exported = user.get("/api/account/export")
    assert exported.status_code == 200
    assert exported.json()["owner_id"] == user_id
    assert [item["display_name"] for item in exported.json()["character_cards"]] == [
        "Delete Ann"
    ]

    wrong = user.request(
        "DELETE",
        "/api/account",
        json={"email": "delete@example.com", "confirmation": "DELETE"},
    )
    assert wrong.status_code == 422
    deleted = user.request(
        "DELETE",
        "/api/account",
        json={
            "email": "delete@example.com",
            "confirmation": "DELETE MY ACCOUNT",
        },
    )
    assert deleted.status_code == 200
    assert deleted.json()["affected"]["characters"] == 1
    assert user.get("/api/auth/me").status_code == 401

    with app.state.database.session() as session:
        stored_user = app.state.auth_repository.get_user(user_id)
        assert stored_user is not None
        assert stored_user.is_active is False
        actions = set(
            session.scalars(
                select(AuditEventRecord.action).where(
                    AuditEventRecord.actor_user_id == user_id
                )
            )
        )
    assert "workspace.exported" in actions
    assert "account.deleted" in actions
    assert app.state.workspace_repository.counts(user_id)["characters"] == 0
