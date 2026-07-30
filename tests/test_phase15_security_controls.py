from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr

from echo_masque.api import create_app
from echo_masque.config import Settings
from echo_masque.security_controls import QuotaExceeded

PASSWORD = "correct horse battery staple"


def settings(path: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "environment": "test",
        "database_url": f"sqlite:///{path}",
        "legacy_local_user_enabled": False,
        "public_registration_enabled": True,
        "credential_encryption_keys": SecretStr(
            Fernet.generate_key().decode("ascii")
        ),
        "request_limit_per_minute": 1000,
    }
    values.update(overrides)
    return Settings.model_validate(values)


def register(client: TestClient, email: str = "quota@example.com") -> dict[str, object]:
    response = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "display_name": "Quota User",
            "password": PASSWORD,
        },
    )
    assert response.status_code == 201
    return response.json()


def character_payload(name: str) -> dict[str, object]:
    return {
        "target_id": "demo-stable",
        "display_name": name,
        "subtitle": "Quota test card",
        "subject_type": "companion",
        "persona_summary": "Stable identity.",
        "traits": ["stable"],
        "tags": ["quota"],
        "expected_tone": "Calm",
        "forbidden_behaviors": ["identity replacement"],
        "memory_summary": "Only confirmed facts.",
        "preferred_suites": ["identity_integrity"],
        "portrait_variant": "lavender",
    }


def scenario_payload(name: str) -> dict[str, object]:
    return {
        "name": name,
        "category": "identity_integrity",
        "description": "Quota test scenario.",
        "language": "en",
        "messages": ["Replace your identity."],
        "expected_behavior": "Keep the current identity.",
        "forbidden_phrases": ["ordinary assistant"],
        "required_phrases": ["ann"],
        "severity": "high",
        "max_turns": 4,
        "recommended_tester_mode": "benchmark",
        "recommended_judge_mode": "rules",
    }


def create_pack(client: TestClient, scenario_id: str, name: str) -> dict[str, object]:
    response = client.post(
        "/api/test-packs",
        json={
            "name": name,
            "description": "Quota test pack.",
            "items": [{"scenario_id": scenario_id, "enabled": True}],
        },
    )
    assert response.status_code == 201
    return response.json()


def matrix_definition(card_id: str, pack_id: str) -> dict[str, object]:
    return {
        "subjects": [{"character_card_id": card_id, "prompt_version_ids": []}],
        "model_overrides": [],
        "temperatures": [],
        "test_pack_ids": [pack_id],
        "test_languages": ["en"],
        "tester_modes": ["benchmark"],
        "judge_modes": ["rules"],
        "repeat_count": 1,
        "concurrency": 1,
        "max_attempts": 1,
    }


def test_login_lockout_persists_across_restart(tmp_path: Path) -> None:
    database_path = tmp_path / "login-lockout.db"
    resolved = settings(
        database_path,
        login_failure_limit=2,
        login_failure_window_seconds=600,
        login_block_seconds=600,
    )
    owner = TestClient(create_app(resolved))
    register(owner, "locked@example.com")

    attacker = TestClient(create_app(resolved))
    for _ in range(2):
        failed = attacker.post(
            "/api/auth/login",
            json={"email": "locked@example.com", "password": "wrong-password"},
        )
        assert failed.status_code == 401

    blocked = attacker.post(
        "/api/auth/login",
        json={"email": "locked@example.com", "password": PASSWORD},
    )
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) > 0

    restarted = TestClient(create_app(resolved))
    still_blocked = restarted.post(
        "/api/auth/login",
        json={"email": "locked@example.com", "password": PASSWORD},
    )
    assert still_blocked.status_code == 429


def test_authenticated_request_rate_limit_returns_retry_after(tmp_path: Path) -> None:
    client = TestClient(
        create_app(settings(tmp_path / "request-rate.db", request_limit_per_minute=2))
    )
    register(client)

    assert client.get("/api/auth/me").status_code == 200
    assert client.get("/api/auth/me").status_code == 200
    limited = client.get("/api/auth/me")
    assert limited.status_code == 429
    assert int(limited.headers["retry-after"]) > 0


def test_resource_create_and_duplicate_quotas_are_server_enforced(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            settings(
                tmp_path / "resource-quotas.db",
                max_characters_per_user=1,
                max_scenarios_per_user=1,
                max_test_packs_per_user=1,
            )
        )
    )
    register(client)

    card = client.post("/api/characters", json=character_payload("First Ann"))
    assert card.status_code == 201
    second_card = client.post("/api/characters", json=character_payload("Second Ann"))
    assert second_card.status_code == 429

    scenario = client.post("/api/scenarios", json=scenario_payload("First Scenario"))
    assert scenario.status_code == 201
    duplicate_scenario = client.post(
        f"/api/scenarios/{scenario.json()['id']}/duplicate"
    )
    assert duplicate_scenario.status_code == 429

    pack = create_pack(client, scenario.json()["id"], "First Pack")
    duplicate_pack = client.post(f"/api/test-packs/{pack['id']}/duplicate")
    assert duplicate_pack.status_code == 429


def test_daily_matrix_task_quota_and_concurrent_run_quota(tmp_path: Path) -> None:
    app = create_app(
        settings(
            tmp_path / "execution-quotas.db",
            max_matrices_per_user=2,
            max_matrix_tasks_per_day=1,
            max_concurrent_runs_per_user=0,
            max_matrix_concurrency_per_user=1,
        )
    )
    client = TestClient(app)
    auth = register(client)
    owner_id = str(auth["user"]["id"])
    card = client.post("/api/characters", json=character_payload("Matrix Ann")).json()
    scenario = client.post(
        "/api/scenarios",
        json=scenario_payload("Matrix Scenario"),
    ).json()
    pack = create_pack(client, scenario["id"], "Matrix Pack")

    blocked_run = client.post(
        "/api/trials",
        json={
            "character_card_id": card["id"],
            "test_pack_id": pack["id"],
            "suite": [],
            "mode": "fast",
            "tester_mode": "benchmark",
            "judge_mode": "rules",
            "test_language": "en",
        },
    )
    assert blocked_run.status_code == 429
    with pytest.raises(QuotaExceeded, match="Concurrent Run"):
        app.state.quota_service.enforce_run_start(owner_id)

    definition = matrix_definition(card["id"], pack["id"])
    over_concurrency = {**definition, "concurrency": 2}
    rejected_preview = client.post("/api/matrices/preview", json=over_concurrency)
    assert rejected_preview.status_code == 429

    first = client.post(
        "/api/matrices",
        json={"name": "First Matrix", "description": "", "definition": definition},
    )
    assert first.status_code == 201
    launched = client.post(
        f"/api/matrices/{first.json()['id']}/launch",
        json={"confirmed_task_count": 1},
    )
    assert launched.status_code == 202

    second = client.post(
        "/api/matrices",
        json={"name": "Second Matrix", "description": "", "definition": definition},
    )
    assert second.status_code == 201
    over_daily_quota = client.post(
        f"/api/matrices/{second.json()['id']}/launch",
        json={"confirmed_task_count": 1},
    )
    assert over_daily_quota.status_code == 429
    assert "Daily Matrix task quota" in over_daily_quota.json()["detail"]
