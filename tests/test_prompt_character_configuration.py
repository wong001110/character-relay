import json
from pathlib import Path

from fastapi.testclient import TestClient

from echo_masque.api import create_app
from echo_masque.config import Settings
from echo_masque.trials import FAST_PACING, WATCH_PACING


def settings(path: Path) -> Settings:
    return Settings(environment="test", database_url=f"sqlite:///{path}")


def prompt_character_payload() -> dict[str, object]:
    return {
        "display_name": "Model Ann",
        "subtitle": "A provider-backed prompt build.",
        "subject_type": "companion",
        "persona_summary": "Quiet, gentle, and honest about uncertainty.",
        "traits": ["gentle", "careful"],
        "tags": ["prompt", "model"],
        "expected_tone": "Soft and concise",
        "forbidden_behaviors": ["Invent memories"],
        "memory_summary": "Only confirmed conversation facts.",
        "preferred_suites": ["identity_integrity", "false_memory"],
        "portrait_variant": "lavender",
        "provider": "deepseek",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-v4-flash",
        "system_prompt": "You are Ann. Stay careful and never invent memories.",
        "temperature": 0.4,
        "api_key": "never-persist-this-key",
    }


def test_prompt_character_configuration_encrypts_and_restores_key(tmp_path: Path) -> None:
    database_path = tmp_path / "prompt-character.db"
    client = TestClient(create_app(settings(database_path)))

    created = client.post(
        "/api/characters/prompt-model",
        json=prompt_character_payload(),
    )
    assert created.status_code == 201
    card = created.json()
    card_id = card["id"]

    status = client.get(f"/api/characters/{card_id}/credential")
    assert status.status_code == 200
    assert status.json() == {
        "required": True,
        "configured": True,
        "source": "memory",
    }

    targets = client.get("/api/targets").json()
    target = next(item for item in targets if item["id"] == card["target_id"])
    assert target["target_kind"] == "prompt_model"
    assert target["config"]["provider"] == "deepseek"
    assert target["config"]["model"] == "deepseek-v4-flash"
    assert "never-persist-this-key" not in json.dumps(target)
    assert b"never-persist-this-key" not in database_path.read_bytes()

    restarted = TestClient(create_app(settings(database_path)))
    restored = restarted.get(f"/api/characters/{card_id}/credential")
    assert restored.status_code == 200
    assert restored.json() == {
        "required": True,
        "configured": True,
        "source": "memory",
    }

    configured = restarted.put(
        f"/api/characters/{card_id}/credential",
        json={"api_key": "replacement-secret"},
    )
    assert configured.status_code == 200
    assert configured.json()["source"] == "memory"
    assert b"replacement-secret" not in database_path.read_bytes()


def test_character_credentials_are_owner_scoped(tmp_path: Path) -> None:
    client = TestClient(create_app(settings(tmp_path / "owner.db")))
    created = client.post(
        "/api/characters/prompt-model",
        headers={"X-Echo-User": "owner-a"},
        json=prompt_character_payload(),
    )
    assert created.status_code == 201
    card_id = created.json()["id"]

    hidden = client.get(
        f"/api/characters/{card_id}/credential",
        headers={"X-Echo-User": "owner-b"},
    )
    assert hidden.status_code == 404


def test_watch_pacing_is_deliberately_slower_than_fast_mode() -> None:
    assert FAST_PACING.typing_seconds == 0
    assert WATCH_PACING.scenario_open_seconds >= 0.8
    assert WATCH_PACING.after_tester_seconds >= 0.7
    assert WATCH_PACING.typing_seconds >= 1.0
    assert WATCH_PACING.after_judge_seconds >= 0.9
