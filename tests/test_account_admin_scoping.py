from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select

from echo_masque.api import create_app
from echo_masque.config import Settings
from echo_masque.persistence.models import InvitationRecord, UserRecord

PASSWORD = "AccountScope2026!"
SUPER_EMAIL = "scope-super@example.com"


def settings(path: Path) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{path}",
        legacy_local_user_enabled=False,
        public_registration_enabled=True,
        bootstrap_admin_email=SUPER_EMAIL,
        bootstrap_admin_password=SecretStr(PASSWORD),
        credential_encryption_keys=SecretStr(Fernet.generate_key().decode("ascii")),
        request_limit_per_minute=1000,
    )


def login(client: TestClient, email: str = SUPER_EMAIL) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": email, "password": PASSWORD},
    )
    assert response.status_code == 200, response.text


def invite_register(
    app: FastAPI,
    admin: TestClient,
    member: TestClient,
    *,
    email: str,
) -> str:
    invitation = admin.post(
        "/api/admin/invitations",
        json={"email": email, "role": "user", "expires_in_days": 1},
    )
    assert invitation.status_code == 201, invitation.text
    invitation_payload = invitation.json()
    registered = member.post(
        "/api/auth/register",
        json={
            "email": email,
            "display_name": email.split("@", maxsplit=1)[0],
            "password": PASSWORD,
            "invitation_code": invitation_payload["code"],
        },
    )
    assert registered.status_code == 201, registered.text
    user_id = str(registered.json()["user"]["id"])

    # Test environments allow public registration, so the invitation code is not consumed
    # by AuthService. Mirror production's invitation-required state explicitly so synthetic
    # cleanup is validated against the same durable identity proof used by live Phase 15.
    with app.state.database.session() as session:
        record = session.get(
            InvitationRecord,
            str(invitation_payload["invitation"]["id"]),
        )
        assert record is not None
        record.accepted_by = user_id
        record.accepted_at = datetime.now(UTC)
        session.commit()
    return user_id


def soft_delete(client: TestClient, email: str) -> None:
    response = client.request(
        "DELETE",
        "/api/account",
        json={"email": email, "confirmation": "DELETE MY ACCOUNT"},
    )
    assert response.status_code == 200, response.text


def test_account_security_paginates_and_searches_active_users(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "latest-users.db"))
    admin = TestClient(app)
    login(admin)
    now = datetime.now(UTC)

    created_ids: list[str] = []
    for index in range(25):
        record = app.state.auth_repository.create_user(
            email=f"member-{index}@example.com",
            display_name=f"Member {index}",
            password_hash="unused",
            role="user",
        )
        created_ids.append(record.id)
        with app.state.database.session() as session:
            stored = session.get(UserRecord, record.id)
            assert stored is not None
            stored.created_at = now + timedelta(seconds=index)
            session.commit()

    deleted = app.state.auth_repository.create_user(
        email="inactive@example.com",
        display_name="Deleted User",
        password_hash="unused",
        role="user",
    )
    with app.state.database.session() as session:
        stored = session.get(UserRecord, deleted.id)
        assert stored is not None
        stored.is_active = False
        stored.created_at = now + timedelta(minutes=5)
        session.commit()

    response = admin.get("/api/admin/users")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["page"] == 1
    assert payload["page_size"] == 20
    assert payload["total"] == 26
    assert payload["pages"] == 2
    assert len(payload["items"]) == 20
    assert all(item["is_active"] is True for item in payload["items"])
    assert deleted.id not in {item["id"] for item in payload["items"]}
    assert [item["id"] for item in payload["items"]] == list(
        reversed(created_ids[-20:])
    )

    second_page = admin.get(
        "/api/admin/users",
        params={"page": 2, "page_size": 20},
    )
    assert second_page.status_code == 200, second_page.text
    assert second_page.json()["page"] == 2
    assert len(second_page.json()["items"]) == 6

    searched = admin.get(
        "/api/admin/users",
        params={"search": "MEMBER 7", "page_size": 20},
    )
    assert searched.status_code == 200, searched.text
    assert searched.json()["total"] == 1
    assert [item["id"] for item in searched.json()["items"]] == [created_ids[7]]

    literal_wildcard = admin.get(
        "/api/admin/users",
        params={"search": "%", "page_size": 20},
    )
    assert literal_wildcard.status_code == 200, literal_wildcard.text
    assert literal_wildcard.json()["total"] == 0


def test_synthetic_test_account_is_hard_deleted_with_trace_and_invitation(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "synthetic-hard-delete.db"))
    admin = TestClient(app)
    member = TestClient(app)
    login(admin)
    email = "phase15-a-1234567890@example.invalid"
    user_id = invite_register(app, admin, member, email=email)

    app.state.provider_trace_repository.record_event(
        {
            "event": "provider.request",
            "trace_id": "synthetic-trace",
            "endpoint": "https://api.deepseek.com/v1/chat/completions",
            "model": "deepseek-v4-flash",
            "owner_id": user_id,
            "trace_mode": "summary",
        }
    )

    deleted = admin.delete(f"/api/admin/synthetic-test-users/{user_id}")
    assert deleted.status_code == 200, deleted.text
    assert deleted.json() == {"deleted_count": 1, "user_ids": [user_id]}
    assert app.state.auth_repository.get_user(user_id) is None
    assert app.state.provider_trace_repository.get_trace("synthetic-trace") is None
    with app.state.database.session() as session:
        accepted = list(
            session.scalars(
                select(InvitationRecord).where(InvitationRecord.accepted_by == user_id)
            )
        )
    assert accepted == []


def test_legacy_purge_removes_only_known_synthetic_deleted_users(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "legacy-synthetic.db"))
    admin = TestClient(app)
    synthetic = TestClient(app)
    ordinary = TestClient(app)
    login(admin)

    synthetic_email = "phase15-b-1234567891@example.invalid"
    synthetic_id = invite_register(app, admin, synthetic, email=synthetic_email)
    ordinary_email = "ordinary-delete@example.com"
    ordinary_id = invite_register(app, admin, ordinary, email=ordinary_email)
    soft_delete(synthetic, synthetic_email)
    soft_delete(ordinary, ordinary_email)

    purged = admin.delete("/api/admin/synthetic-test-users")
    assert purged.status_code == 200, purged.text
    assert synthetic_id in purged.json()["user_ids"]
    assert app.state.auth_repository.get_user(synthetic_id) is None

    ordinary_record = app.state.auth_repository.get_user(ordinary_id)
    assert ordinary_record is not None
    assert ordinary_record.is_active is False
    assert ordinary_record.display_name == "Deleted User"


def test_hard_delete_rejects_normal_accounts(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "reject-normal-hard-delete.db"))
    admin = TestClient(app)
    member = TestClient(app)
    login(admin)
    user_id = invite_register(app, admin, member, email="real-person@example.com")

    denied = admin.delete(f"/api/admin/synthetic-test-users/{user_id}")
    assert denied.status_code == 403
    assert app.state.auth_repository.get_user(user_id) is not None


def test_provider_trace_owner_filter_rejects_inactive_or_unknown_accounts(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "trace-owner-filter.db"))
    admin = TestClient(app)
    member = TestClient(app)
    login(admin)
    email = "trace-member@example.com"
    user_id = invite_register(app, admin, member, email=email)

    app.state.provider_trace_repository.record_event(
        {
            "event": "provider.request",
            "trace_id": "member-trace",
            "endpoint": "https://api.deepseek.com/v1/chat/completions",
            "model": "deepseek-v4-flash",
            "owner_id": user_id,
            "trace_mode": "summary",
        }
    )
    active = admin.get(
        "/api/admin/provider-traces/page",
        params={"owner_id": user_id},
    )
    assert active.status_code == 200, active.text
    assert [item["trace_id"] for item in active.json()["items"]] == ["member-trace"]

    soft_delete(member, email)
    inactive = admin.get(
        "/api/admin/provider-traces/page",
        params={"owner_id": user_id},
    )
    assert inactive.status_code == 422
    unknown = admin.get(
        "/api/admin/provider-traces/page",
        params={"owner_id": "does-not-exist"},
    )
    assert unknown.status_code == 422
