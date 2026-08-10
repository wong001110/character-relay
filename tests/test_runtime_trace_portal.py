from pathlib import Path

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr

from echo_masque.api import create_app
from echo_masque.config import Settings
from echo_masque.orchestration.trace import RuntimeTraceEvent

SUPER_EMAIL = "runtime-trace-super@example.com"
SUPER_PASSWORD = "RuntimeTraceSuper2026!"
ADMIN_EMAIL = "runtime-trace-admin@example.com"
ADMIN_PASSWORD = "RuntimeTraceAdmin2026!"


def settings(path: Path) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{path}",
        legacy_local_user_enabled=False,
        bootstrap_admin_email=SUPER_EMAIL,
        bootstrap_admin_password=SecretStr(SUPER_PASSWORD),
        bootstrap_admin_display_name="Runtime Trace Super Admin",
        credential_encryption_keys=SecretStr(Fernet.generate_key().decode("ascii")),
    )


def login(client: TestClient, email: str, password: str) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200, response.text


def seed_runtime_trace(app: object) -> None:
    repository = app.state.durable_runtime_repository
    common = {
        "trace_id": "runtime-trace-1",
        "graph_run_id": "runtime-run-1",
        "graph_name": "character_turn",
        "operation_id": "runtime-operation-1",
        "owner_id": "owner-1",
        "deployment_id": "deployment-ann",
        "character_card_id": "card-ann",
    }
    repository.emit(
        RuntimeTraceEvent(
            **common,
            node_name="turn_model",
            node_kind="agentic",
            status="completed",
            changed_keys=("model_status",),
            metadata=(("next", "smart_output"),),
        )
    )
    repository.emit(
        RuntimeTraceEvent(
            **common,
            node_name="turn_authority",
            node_kind="authority",
            status="completed",
            changed_keys=("authority_status",),
            metadata=(("action", "reply"),),
        )
    )


def test_runtime_trace_explorer_is_super_admin_only(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "runtime-trace-portal.db"))
    seed_runtime_trace(app)

    super_client = TestClient(app)
    login(super_client, SUPER_EMAIL, SUPER_PASSWORD)

    access = super_client.get("/api/admin/runtime-traces/access")
    assert access.status_code == 200
    assert access.json() == {"allowed": True}

    page = super_client.get(
        "/api/admin/runtime-traces/page",
        params={"operation_id": "runtime-operation-1"},
    )
    assert page.status_code == 200, page.text
    payload = page.json()
    assert payload["has_more"] is False
    assert payload["next_cursor"] is None
    assert len(payload["items"]) == 1
    summary = payload["items"][0]
    assert summary["graph_run_id"] == "runtime-run-1"
    assert summary["graph_name"] == "character_turn"
    assert summary["status"] == "completed"
    assert summary["operation_id"] == "runtime-operation-1"
    assert summary["event_count"] == 2
    assert "messages" not in summary
    assert "prompt" not in summary
    assert "tool_result" not in summary

    detail = super_client.get("/api/admin/runtime-traces/runtime-run-1")
    assert detail.status_code == 200, detail.text
    detail_payload = detail.json()
    assert [item["node_name"] for item in detail_payload["events"]] == [
        "turn_model",
        "turn_authority",
    ]
    assert detail_payload["events"][0]["metadata"] == [["next", "smart_output"]]

    app.state.auth_repository.create_user(
        email=ADMIN_EMAIL,
        display_name="Regular Admin",
        password_hash=app.state.auth_service.passwords.hash(ADMIN_PASSWORD),
        role="admin",
    )
    regular_admin = TestClient(app)
    login(regular_admin, ADMIN_EMAIL, ADMIN_PASSWORD)
    denied = regular_admin.get("/api/admin/runtime-traces/page")
    assert denied.status_code == 403
    denied_access = regular_admin.get("/api/admin/runtime-traces/access")
    assert denied_access.status_code == 403

    cleared = super_client.delete("/api/admin/runtime-traces")
    assert cleared.status_code == 200
    assert cleared.json() == {"deleted_count": 1}
    assert super_client.get("/api/admin/runtime-traces/page").json()["items"] == []
