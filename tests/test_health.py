from fastapi.testclient import TestClient

from echo_masque.api import create_app
from echo_masque.config import Settings


def test_health() -> None:
    app = create_app(Settings(environment="test"))
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "name": "Echo Masque",
        "version": "0.1.0",
        "status": "ok",
        "environment": "test",
    }
