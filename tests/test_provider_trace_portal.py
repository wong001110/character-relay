from pathlib import Path

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr

from echo_masque.api import create_app
from echo_masque.config import Settings

SUPER_EMAIL = "super-admin@example.com"
SUPER_PASSWORD = "SuperAdminTrace2026!"
ADMIN_EMAIL = "regular-admin@example.com"
ADMIN_PASSWORD = "RegularAdminTrace2026!"


def settings(path: Path) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{path}",
        legacy_local_user_enabled=False,
        bootstrap_admin_email=SUPER_EMAIL,
        bootstrap_admin_password=SecretStr(SUPER_PASSWORD),
        bootstrap_admin_display_name="Super Admin",
        credential_encryption_keys=SecretStr(Fernet.generate_key().decode("ascii")),
        provider_trace_retention_days=7,
        provider_trace_max_records=500,
    )


def login(client: TestClient, email: str, password: str) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200, response.text


def seed_trace(app: object, *, trace_id: str = "trace-001", owner_id: str = "") -> None:
    repository = app.state.provider_trace_repository
    request_event: dict[str, object] = {
        "event": "provider.request",
        "trace_id": trace_id,
        "endpoint": "https://api.deepseek.com/v1/chat/completions",
        "model": "deepseek-v4-flash",
        "temperature": 0.4,
        "trace_mode": "content",
        "messages": [
            {"role": "system", "content": "You are Ning."},
            {"role": "user", "content": "Are you there?"},
        ],
    }
    response_event: dict[str, object] = {
        "event": "provider.response",
        "trace_id": trace_id,
        "endpoint": "https://api.deepseek.com/v1/chat/completions",
        "request_model": "deepseek-v4-flash",
        "response_model": "deepseek-v4-flash",
        "status_code": 200,
        "latency_ms": 850,
        "input_tokens": 20,
        "output_tokens": 6,
        "finish_reason": "stop",
        "response_text": "I am here.",
        "trace_mode": "content",
    }
    if owner_id:
        request_event["owner_id"] = owner_id
        response_event["owner_id"] = owner_id
    repository.record_event(request_event)
    repository.record_event(response_event)


def test_provider_trace_portal_is_bootstrap_super_admin_only(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "provider-trace-portal.db"))
    seed_trace(app)

    super_client = TestClient(app)
    login(super_client, SUPER_EMAIL, SUPER_PASSWORD)
    access = super_client.get("/api/admin/provider-traces/access")
    assert access.status_code == 200
    assert access.json() == {"allowed": True}

    response = super_client.get("/api/admin/provider-traces")
    assert response.status_code == 200, response.text
    assert response.json() == [
        {
            "trace_id": "trace-001",
            "status": "succeeded",
            "category": "model_call",
            "tool_names": [],
            "media_input": {},
            "owner_id": "",
            "deployment_id": "",
            "character_card_id": "",
            "trace_mode": "content",
            "endpoint": "https://api.deepseek.com/v1/chat/completions",
            "request_model": "deepseek-v4-flash",
            "response_model": "deepseek-v4-flash",
            "request": {
                "event": "provider.request",
                "trace_id": "trace-001",
                "endpoint": "https://api.deepseek.com/v1/chat/completions",
                "model": "deepseek-v4-flash",
                "temperature": 0.4,
                "trace_mode": "content",
                "messages": [
                    {"role": "system", "content": "You are Ning."},
                    {"role": "user", "content": "Are you there?"},
                ],
            },
            "retries": [],
            "response": {
                "event": "provider.response",
                "trace_id": "trace-001",
                "endpoint": "https://api.deepseek.com/v1/chat/completions",
                "request_model": "deepseek-v4-flash",
                "response_model": "deepseek-v4-flash",
                "status_code": 200,
                "latency_ms": 850,
                "input_tokens": 20,
                "output_tokens": 6,
                "finish_reason": "stop",
                "response_text": "I am here.",
                "trace_mode": "content",
            },
            "error": {},
            "status_code": 200,
            "latency_ms": 850,
            "input_tokens": 20,
            "output_tokens": 6,
            "created_at": response.json()[0]["created_at"],
            "updated_at": response.json()[0]["updated_at"],
        }
    ]
    detail = super_client.get("/api/admin/provider-traces/trace-001")
    assert detail.status_code == 200
    assert detail.json()["request"]["messages"][1]["content"] == "Are you there?"

    app.state.auth_repository.create_user(
        email=ADMIN_EMAIL,
        display_name="Regular Admin",
        password_hash=app.state.auth_service.passwords.hash(ADMIN_PASSWORD),
        role="admin",
    )
    regular_admin = TestClient(app)
    login(regular_admin, ADMIN_EMAIL, ADMIN_PASSWORD)
    denied = regular_admin.get("/api/admin/provider-traces")
    assert denied.status_code == 403
    assert denied.json()["detail"] == "Super Admin access required."
    denied_access = regular_admin.get("/api/admin/provider-traces/access")
    assert denied_access.status_code == 403

    cleared = super_client.delete("/api/admin/provider-traces")
    assert cleared.status_code == 200
    assert cleared.json() == {"deleted_count": 1}
    assert super_client.get("/api/admin/provider-traces").json() == []


def test_provider_trace_cursor_pagination_uses_summary_payload(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "provider-trace-pagination.db"))
    repository = app.state.provider_trace_repository
    for index in range(1, 6):
        repository.record_event(
            {
                "event": "provider.request",
                "trace_id": f"trace-{index:03d}",
                "endpoint": "https://api.deepseek.com/v1/chat/completions",
                "model": "deepseek-v4-flash",
                "trace_mode": "metadata",
            }
        )
    client = TestClient(app)
    login(client, SUPER_EMAIL, SUPER_PASSWORD)

    first = client.get("/api/admin/provider-traces/page", params={"limit": 2})
    assert first.status_code == 200, first.text
    first_payload = first.json()
    assert len(first_payload["items"]) == 2
    assert first_payload["has_more"] is True
    assert "request" not in first_payload["items"][0]
    assert "response" not in first_payload["items"][0]

    second = client.get(
        "/api/admin/provider-traces/page",
        params={"limit": 2, "cursor": first_payload["next_cursor"]},
    )
    assert second.status_code == 200, second.text
    first_ids = {item["trace_id"] for item in first_payload["items"]}
    second_ids = {item["trace_id"] for item in second.json()["items"]}
    assert first_ids.isdisjoint(second_ids)

    invalid = client.get(
        "/api/admin/provider-traces/page",
        params={"cursor": "not-a-valid-cursor"},
    )
    assert invalid.status_code == 422


def test_provider_trace_category_and_owner_filters_are_server_side(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "provider-trace-category.db"))
    repository = app.state.provider_trace_repository
    super_user = app.state.auth_repository.get_user_by_email(SUPER_EMAIL)
    assert super_user is not None

    seed_trace(app, trace_id="trace-other", owner_id="other-owner")
    repository.record_event(
        {
            "event": "provider.request",
            "trace_id": "trace-tool",
            "endpoint": "https://api.deepseek.com/v1/chat/completions",
            "model": "deepseek-v4-flash",
            "trace_mode": "summary",
            "owner_id": super_user.id,
            "deployment_id": "deployment-1",
            "character_card_id": "character-1",
            "message_roles": ["system", "user"],
            "available_tool_names": ["scheduler_remind"],
            "latest_message": {"role": "user", "content": "Remind me in ten minutes."},
        }
    )
    repository.record_event(
        {
            "event": "provider.response",
            "trace_id": "trace-tool",
            "endpoint": "https://api.deepseek.com/v1/chat/completions",
            "response_model": "deepseek-v4-flash",
            "status_code": 200,
            "tool_call_names": ["scheduler_remind"],
            "trace_mode": "summary",
            "owner_id": super_user.id,
            "deployment_id": "deployment-1",
            "character_card_id": "character-1",
        }
    )

    client = TestClient(app)
    login(client, SUPER_EMAIL, SUPER_PASSWORD)
    response = client.get(
        "/api/admin/provider-traces/page",
        params={
            "category": "tool_calling",
            "owner_id": super_user.id,
            "limit": 50,
        },
    )
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert [item["trace_id"] for item in items] == ["trace-tool"]
    assert items[0]["category"] == "tool_calling"
    assert items[0]["tool_names"] == ["scheduler_remind"]
    assert items[0]["owner_id"] == super_user.id
    assert items[0]["deployment_id"] == "deployment-1"
    assert items[0]["character_card_id"] == "character-1"

    cleared = client.delete(
        "/api/admin/provider-traces",
        params={"owner_id": super_user.id},
    )
    assert cleared.status_code == 200
    assert cleared.json() == {"deleted_count": 1}
    remaining = client.get("/api/admin/provider-traces/page").json()["items"]
    assert [item["trace_id"] for item in remaining] == ["trace-other"]
