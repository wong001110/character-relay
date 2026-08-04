from pathlib import Path

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr

from echo_masque.api import create_app
from echo_masque.config import Settings

ADMIN_EMAIL = "pagination-admin@example.com"
ADMIN_PASSWORD = "PaginationAdmin2026!"


def settings(path: Path) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{path}",
        legacy_local_user_enabled=False,
        bootstrap_admin_email=ADMIN_EMAIL,
        bootstrap_admin_password=SecretStr(ADMIN_PASSWORD),
        bootstrap_admin_display_name="Pagination Admin",
        credential_encryption_keys=SecretStr(Fernet.generate_key().decode("ascii")),
    )


def test_audit_cursor_pagination_has_no_duplicates(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "audit-pagination.db"))
    client = TestClient(app)
    login = client.post(
        "/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert login.status_code == 200, login.text
    for index in range(5):
        app.state.auth_repository.audit(
            actor_user_id=None,
            action=f"pagination.event_{index}",
            resource_type="pagination",
            resource_id=str(index),
        )

    first = client.get("/api/admin/audit/page", params={"limit": 2})
    assert first.status_code == 200, first.text
    first_payload = first.json()
    assert len(first_payload["items"]) == 2
    assert first_payload["has_more"] is True

    second = client.get(
        "/api/admin/audit/page",
        params={"limit": 2, "cursor": first_payload["next_cursor"]},
    )
    assert second.status_code == 200, second.text
    first_ids = {item["id"] for item in first_payload["items"]}
    second_ids = {item["id"] for item in second.json()["items"]}
    assert first_ids.isdisjoint(second_ids)

    invalid = client.get(
        "/api/admin/audit/page",
        params={"cursor": "invalid"},
    )
    assert invalid.status_code == 422
