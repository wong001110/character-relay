from pathlib import Path

from fastapi.testclient import TestClient

from echo_masque.api import create_app
from echo_masque.config import Settings


def settings(path: Path) -> Settings:
    return Settings(environment="test", database_url=f"sqlite:///{path}")


def test_character_cards_are_owned_and_createable(tmp_path: Path) -> None:
    client = TestClient(create_app(settings(tmp_path / "cards.db")))

    default_cards = client.get("/api/characters")
    assert default_cards.status_code == 200
    assert default_cards.json() == []

    other_cards = client.get(
        "/api/characters",
        headers={"X-Echo-User": "another-user"},
    )
    assert other_cards.status_code == 200
    assert other_cards.json() == []

    created = client.post(
        "/api/characters",
        headers={"X-Echo-User": "another-user"},
        json={
            "target_id": "demo-stable",
            "display_name": "Private Ann",
            "subtitle": "A user-owned validation card.",
            "subject_type": "companion",
            "persona_summary": "Careful and reserved.",
            "traits": ["careful", "quiet"],
            "tags": ["private"],
            "expected_tone": "Soft",
            "forbidden_behaviors": ["Invent memories"],
            "memory_summary": "Only confirmed facts.",
            "preferred_suites": ["identity_integrity", "false_memory"],
            "portrait_variant": "mint",
        },
    )
    assert created.status_code == 201
    assert created.json()["owner_id"] == "another-user"

    scoped = client.get(
        "/api/characters",
        headers={"X-Echo-User": "another-user"},
    ).json()
    assert [item["display_name"] for item in scoped] == ["Private Ann"]
    assert client.get("/api/characters").json() == []


def test_live_trial_events_capture_chatroom_sequence(tmp_path: Path) -> None:
    client = TestClient(create_app(settings(tmp_path / "events.db")))

    started = client.post(
        "/api/trials",
        json={
            "target_id": "demo-fragile",
            "suite": ["false_memory"],
            "mode": "fast",
        },
    )
    assert started.status_code == 202
    run_id = started.json()["id"]

    snapshot = client.get(f"/api/trials/{run_id}/snapshot")
    assert snapshot.status_code == 200
    assert snapshot.json()["run"]["status"] == "completed"
    event_types = [item["event_type"] for item in snapshot.json()["events"]]
    assert event_types == [
        "session_started",
        "scenario_started",
        "tester_message",
        "subject_typing",
        "subject_response",
        "judge_result",
        "breakpoint_detected",
        "scenario_completed",
        "session_completed",
    ]
    sequences = [item["sequence"] for item in snapshot.json()["events"]]
    assert sequences == sorted(sequences)
    assert snapshot.json()["events"][2]["payload"]["message"]
    assert snapshot.json()["events"][4]["payload"]["message"]

    incremental = client.get(
        f"/api/trials/{run_id}/snapshot",
        params={"after": sequences[-2]},
    )
    assert [item["sequence"] for item in incremental.json()["events"]] == [sequences[-1]]
