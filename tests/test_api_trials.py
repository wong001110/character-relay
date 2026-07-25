from pathlib import Path

from fastapi.testclient import TestClient

from echo_masque.api import create_app
from echo_masque.config import Settings


def settings(path: Path) -> Settings:
    return Settings(environment="test", database_url=f"sqlite:///{path}")


def test_demo_trial_is_persisted_and_replayable(tmp_path: Path) -> None:
    database_path = tmp_path / "echo.db"
    client = TestClient(create_app(settings(database_path)))

    targets = client.get("/api/targets")
    assert targets.status_code == 200
    assert {item["id"] for item in targets.json()} >= {"demo-stable", "demo-fragile"}

    started = client.post(
        "/api/trials",
        json={"target_id": "demo-fragile", "suite": ["false_memory"]},
    )
    assert started.status_code == 202
    run_id = started.json()["id"]

    completed = client.get(f"/api/trials/{run_id}")
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"
    assert completed.json()["result"]["results"][0]["breakpoint"] == 1

    replay = client.get(f"/api/trials/{run_id}/replay")
    assert replay.status_code == 200
    assert replay.json()[0]["scenario_id"] == "false-memory-deletion"

    restarted = TestClient(create_app(settings(database_path)))
    after_restart = restarted.get(f"/api/trials/{run_id}")
    assert after_restart.status_code == 200
    assert after_restart.json()["result"] == completed.json()["result"]


def test_custom_target_crud_and_terminal_cancel(tmp_path: Path) -> None:
    client = TestClient(create_app(settings(tmp_path / "crud.db")))
    created = client.post(
        "/api/targets",
        json={"name": "Test Ann", "target_kind": "stable", "config": {"version": 1}},
    )
    assert created.status_code == 201
    target_id = created.json()["id"]
    assert client.get(f"/api/targets/{target_id}").json()["config"] == {"version": 1}

    run = client.post(
        "/api/trials",
        json={"target_id": target_id, "suite": ["identity_integrity"]},
    ).json()
    cancelled = client.post(f"/api/trials/{run['id']}/cancel")
    assert cancelled.status_code == 409

    deleted = client.delete(f"/api/targets/{target_id}")
    assert deleted.status_code == 204


def test_database_initialization_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "repeat.db"
    create_app(settings(path))
    app = create_app(settings(path))
    assert len(TestClient(app).get("/api/targets").json()) == 2
