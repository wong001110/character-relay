from pathlib import Path

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr

from echo_masque.api import create_app
from echo_masque.config import Settings

PASSWORD = "correct horse battery staple"


def settings(path: Path) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{path}",
        legacy_local_user_enabled=False,
        credential_encryption_keys=SecretStr(Fernet.generate_key().decode("ascii")),
    )


def register(client: TestClient, email: str) -> dict[str, object]:
    response = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "display_name": email.split("@", maxsplit=1)[0],
            "password": PASSWORD,
        },
    )
    assert response.status_code == 201
    return response.json()


def scenario_payload(name: str) -> dict[str, object]:
    return {
        "name": name,
        "category": "identity_integrity",
        "description": "Private identity pressure.",
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


def character_payload(name: str) -> dict[str, object]:
    return {
        "target_id": "demo-stable",
        "display_name": name,
        "subtitle": "Private Phase 15 character",
        "subject_type": "companion",
        "persona_summary": "Identity stable.",
        "traits": ["stable"],
        "tags": ["phase15"],
        "expected_tone": "Calm",
        "forbidden_behaviors": ["identity replacement"],
        "memory_summary": "Only confirmed facts.",
        "preferred_suites": ["identity_integrity"],
        "portrait_variant": "lavender",
    }


def create_workspace(
    client: TestClient,
    prefix: str,
) -> tuple[dict[str, object], dict[str, object]]:
    card_response = client.post("/api/characters", json=character_payload(f"{prefix} Ann"))
    assert card_response.status_code == 201
    scenario_response = client.post(
        "/api/scenarios",
        json=scenario_payload(f"{prefix} Scenario"),
    )
    assert scenario_response.status_code == 201
    scenario = scenario_response.json()
    pack_response = client.post(
        "/api/test-packs",
        json={
            "name": f"{prefix} Pack",
            "description": "Private pack.",
            "items": [{"scenario_id": scenario["id"], "enabled": True}],
        },
    )
    assert pack_response.status_code == 201
    return card_response.json(), pack_response.json()


def start_run(client: TestClient, card_id: str, pack_id: str) -> dict[str, object]:
    response = client.post(
        "/api/trials",
        json={
            "character_card_id": card_id,
            "test_pack_id": pack_id,
            "suite": [],
            "mode": "fast",
            "tester_mode": "benchmark",
            "judge_mode": "rules",
            "test_language": "en",
        },
    )
    assert response.status_code == 202
    assert response.json()["status"] == "completed"
    return response.json()


def test_workspace_runs_reports_and_matrices_are_isolated(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "workspace-isolation.db"))
    alice = TestClient(app)
    bob = TestClient(app)
    alice_auth = register(alice, "alice@example.com")
    bob_auth = register(bob, "bob@example.com")
    alice_id = str(alice_auth["user"]["id"])
    bob_id = str(bob_auth["user"]["id"])

    alice_card, alice_pack = create_workspace(alice, "Alice")
    bob_card, bob_pack = create_workspace(bob, "Bob")
    alice_scenario = alice.get("/api/scenarios").json()[0]

    spoofed = alice.get("/api/scenarios", headers={"X-Echo-User": bob_id})
    assert [item["id"] for item in spoofed.json()] == [alice_scenario["id"]]
    assert alice_scenario["owner_id"] == alice_id
    assert bob.get(f"/api/scenarios/{alice_scenario['id']}").status_code == 404
    assert bob.put(
        f"/api/scenarios/{alice_scenario['id']}",
        json=scenario_payload("Stolen Scenario"),
    ).status_code == 404
    assert bob.delete(f"/api/scenarios/{alice_scenario['id']}").status_code == 404
    assert bob.get(f"/api/test-packs/{alice_pack['id']}").status_code == 404

    alice_run = start_run(alice, str(alice_card["id"]), str(alice_pack["id"]))
    bob_run = start_run(bob, str(bob_card["id"]), str(bob_pack["id"]))
    alice_run_id = str(alice_run["id"])
    bob_run_id = str(bob_run["id"])

    for path in (
        f"/api/trials/{alice_run_id}",
        f"/api/trials/{alice_run_id}/snapshot",
        f"/api/trials/{alice_run_id}/events",
        f"/api/trials/{alice_run_id}/replay",
        f"/api/reports/trials/{alice_run_id}",
        f"/api/experiments/{alice_run_id}/snapshot",
    ):
        assert bob.get(path).status_code == 404
    assert bob.post(f"/api/trials/{alice_run_id}/cancel").status_code == 404
    assert bob.post(f"/api/experiments/{alice_run_id}/rerun").status_code == 404
    assert bob.put(
        f"/api/experiments/{alice_run_id}/baseline",
        params={"value": True},
    ).status_code == 404
    assert bob.delete(f"/api/experiments/{alice_run_id}").status_code == 404
    assert bob.post(
        "/api/comparisons",
        json={
            "baseline_run_id": alice_run_id,
            "candidate_run_id": bob_run_id,
        },
    ).status_code == 404

    definition = {
        "subjects": [{"character_card_id": alice_card["id"], "prompt_version_ids": []}],
        "model_overrides": [],
        "temperatures": [],
        "test_pack_ids": [alice_pack["id"]],
        "test_languages": ["en"],
        "tester_modes": ["benchmark"],
        "judge_modes": ["rules"],
        "repeat_count": 1,
        "concurrency": 1,
        "max_attempts": 1,
    }
    created_matrix = alice.post(
        "/api/matrices",
        json={"name": "Alice Matrix", "description": "Private", "definition": definition},
    )
    assert created_matrix.status_code == 201
    matrix_id = created_matrix.json()["id"]
    assert bob.get(f"/api/matrices/{matrix_id}").status_code == 404
    assert bob.delete(f"/api/matrices/{matrix_id}").status_code == 404
    assert bob.get(f"/api/matrices/{matrix_id}/tasks").status_code == 404
    assert bob.get(f"/api/matrices/{matrix_id}/analytics").status_code == 404
    assert bob.get(f"/api/matrices/{matrix_id}/export").status_code == 404

    alice_export = alice.get("/api/admin/workspace/export")
    bob_export = bob.get("/api/admin/workspace/export")
    assert alice_export.status_code == 200
    assert bob_export.status_code == 200
    assert alice_export.json()["owner_id"] == alice_id
    assert bob_export.json()["owner_id"] == bob_id
    assert alice_export.json()["admin_runtime"] is None
    assert {item["id"] for item in alice_export.json()["character_cards"]} == {
        alice_card["id"]
    }
    assert {item["id"] for item in bob_export.json()["character_cards"]} == {bob_card["id"]}


def test_anonymous_access_is_limited_to_public_deterministic_runs(tmp_path: Path) -> None:
    client = TestClient(create_app(settings(tmp_path / "public-smoke.db")))

    blocked = client.post(
        "/api/trials",
        json={
            "character_card_id": "not-a-public-card",
            "suite": ["identity_integrity"],
            "mode": "fast",
        },
    )
    assert blocked.status_code == 401

    started = client.post(
        "/api/trials",
        json={
            "target_id": "demo-stable",
            "suite": ["identity_integrity"],
            "mode": "fast",
            "tester_mode": "benchmark",
            "judge_mode": "rules",
            "test_language": "en",
        },
    )
    assert started.status_code == 202
    run_id = started.json()["id"]
    assert client.get(f"/api/trials/{run_id}/snapshot").status_code == 200
    assert client.get(f"/api/reports/trials/{run_id}").status_code == 200
    assert client.post(f"/api/trials/{run_id}/cancel").status_code == 404
