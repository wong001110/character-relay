from pathlib import Path

from fastapi.testclient import TestClient

from echo_masque.api import create_app
from echo_masque.config import Settings


def test_health(tmp_path: Path) -> None:
    database_path = tmp_path / "health.db"
    app = create_app(
        Settings(environment="test", database_url=f"sqlite:///{database_path}")
    )
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "Echo Masque"
    assert payload["version"] == "0.1.0"
    assert payload["status"] == "ok"
    assert payload["environment"] == "test"
    assert payload["storage"]["database_kind"] == "sqlite"
    assert payload["storage"]["database_path"] == str(database_path.resolve())
    assert payload["storage"]["persistent_required"] is False
    assert payload["storage"]["mount_ready"] is True
    assert payload["storage"]["storage_instance_id"]
