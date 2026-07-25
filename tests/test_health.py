from fastapi.testclient import TestClient

from echo_masque.api import create_app
from echo_masque.config import Settings


def test_health_endpoint_returns_resolved_settings() -> None:
    app = create_app(
        Settings(
            app_name="Echo Masque Test",
            app_version="9.9.9",
            environment="test",
        )
    )

    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "name": "Echo Masque Test",
        "version": "9.9.9",
        "status": "ok",
        "environment": "test",
    }
