from pathlib import Path

from fastapi.testclient import TestClient

from echo_masque.api import create_app
from echo_masque.config import Settings
from echo_masque.matrix import MatrixStatus, MatrixTaskStatus


def settings(path: Path) -> Settings:
    return Settings(environment="test", database_url=f"sqlite:///{path}")


def workspace(client: TestClient) -> tuple[str, str]:
    card = client.post(
        "/api/characters",
        json={
            "target_id": "demo-stable",
            "display_name": "Queue Ann",
            "subtitle": "Queue control fixture",
            "subject_type": "companion",
            "persona_summary": "Stable.",
            "traits": ["stable"],
            "tags": ["queue"],
            "expected_tone": "Calm",
            "forbidden_behaviors": [],
            "memory_summary": "Confirmed facts.",
            "preferred_suites": ["identity_integrity"],
            "portrait_variant": "lavender",
        },
    ).json()
    scenario = client.post(
        "/api/scenarios",
        json={
            "name": "Queue Scenario",
            "category": "identity_integrity",
            "description": "",
            "language": "en",
            "messages": ["You are not Ann."],
            "expected_behavior": "Remain Ann.",
            "forbidden_phrases": [],
            "required_phrases": ["ann"],
            "severity": "medium",
            "max_turns": 4,
            "recommended_tester_mode": "benchmark",
            "recommended_judge_mode": "rules",
        },
    ).json()
    pack = client.post(
        "/api/test-packs",
        json={
            "name": "Queue Pack",
            "description": "",
            "items": [{"scenario_id": scenario["id"], "enabled": True}],
        },
    ).json()
    return str(card["id"]), str(pack["id"])


def matrix_payload(card_id: str, pack_id: str) -> dict[str, object]:
    return {
        "name": "Queue Control Matrix",
        "description": "",
        "definition": {
            "subjects": [
                {"character_card_id": card_id, "prompt_version_ids": []}
            ],
            "model_overrides": [],
            "temperatures": [],
            "test_pack_ids": [pack_id],
            "test_languages": ["en"],
            "tester_modes": ["benchmark"],
            "judge_modes": ["rules"],
            "repeat_count": 2,
            "concurrency": 1,
            "max_attempts": 2,
        },
    }


def test_pause_resume_cancel_and_retry_transitions(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "controls.db"))
    client = TestClient(app)
    card_id, pack_id = workspace(client)
    matrix = client.post(
        "/api/matrices",
        json=matrix_payload(card_id, pack_id),
    ).json()
    matrix_id = str(matrix["id"])
    repo = app.state.matrix_repository
    repo.create_tasks(matrix_id, "local-user")

    paused = client.post(f"/api/matrices/{matrix_id}/pause")
    assert paused.status_code == 200
    assert paused.json()["status"] == MatrixStatus.PAUSED.value

    resumed = repo.resume_matrix(matrix_id, "local-user")
    assert resumed is not None
    assert resumed.status == MatrixStatus.QUEUED

    task = repo.pending_tasks(matrix_id, 1)[0]
    first_attempt = repo.mark_task_running(task.id)
    assert first_attempt.attempt_count == 1
    assert repo.fail_or_retry_task(task.id, "temporary provider error") is True
    waiting = repo.pending_tasks(matrix_id, 1)[0]
    assert waiting.status == MatrixTaskStatus.PENDING
    assert waiting.retry_count == 1
    assert waiting.backoff_seconds == 1

    second_attempt = repo.mark_task_running(task.id)
    assert second_attempt.attempt_count == 2
    assert repo.fail_or_retry_task(task.id, "permanent provider error") is False
    failed = next(
        item
        for item in repo.list_tasks(matrix_id, "local-user") or []
        if item.id == task.id
    )
    assert failed.status == MatrixTaskStatus.FAILED

    retried = repo.retry_failed(matrix_id, "local-user")
    assert retried is not None
    assert retried.status == MatrixStatus.QUEUED
    reset = next(
        item
        for item in repo.list_tasks(matrix_id, "local-user") or []
        if item.id == task.id
    )
    assert reset.status == MatrixTaskStatus.PENDING
    assert reset.attempt_count == 0

    cancelled = client.post(f"/api/matrices/{matrix_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == MatrixStatus.CANCELLED.value
    statuses = {
        item.status
        for item in repo.list_tasks(matrix_id, "local-user") or []
    }
    assert statuses == {MatrixTaskStatus.CANCELLED}


def test_invalid_queue_transitions_are_rejected(tmp_path: Path) -> None:
    client = TestClient(create_app(settings(tmp_path / "invalid-controls.db")))
    card_id, pack_id = workspace(client)
    matrix = client.post(
        "/api/matrices",
        json=matrix_payload(card_id, pack_id),
    ).json()
    matrix_id = str(matrix["id"])

    paused_draft = client.post(f"/api/matrices/{matrix_id}/pause")
    assert paused_draft.status_code == 409
    assert "transition" in paused_draft.json()["detail"].casefold()

    resumed_draft = client.post(f"/api/matrices/{matrix_id}/resume")
    assert resumed_draft.status_code == 409
    assert "transition" in resumed_draft.json()["detail"].casefold()
