from pathlib import Path

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr

from echo_masque.api import create_app
from echo_masque.config import Settings

ADMIN_EMAIL = "smart-admin@example.com"
ADMIN_PASSWORD = "CharacterRelaySmart2026!"
CONNECTOR_SECRET = "smart-connector-secret"


def settings(path: Path) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{path}",
        legacy_local_user_enabled=False,
        bootstrap_admin_email=ADMIN_EMAIL,
        bootstrap_admin_password=SecretStr(ADMIN_PASSWORD),
        bootstrap_admin_display_name="Smart Admin",
        connector_shared_secret=SecretStr(CONNECTOR_SECRET),
        credential_encryption_keys=SecretStr(Fernet.generate_key().decode("ascii")),
    )


def login(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200, response.text


def create_character(client: TestClient, name: str) -> dict[str, object]:
    response = client.post(
        "/api/characters/prompt-model",
        json={
            "display_name": name,
            "subtitle": "Smart participation test character",
            "subject_type": "custom",
            "persona_summary": f"{name} participates in a group chat.",
            "traits": ["social", "concise"],
            "tags": ["smart-participation"],
            "expected_tone": "Concise.",
            "forbidden_behaviors": ["invent private memories"],
            "memory_summary": "Use only supplied context.",
            "preferred_suites": ["identity_integrity"],
            "portrait_variant": "lavender",
            "provider": "deepseek",
            "base_url": "https://api.deepseek.com",
            "model": "deepseek-v4-flash",
            "system_prompt": f"You are {name}.",
            "temperature": 0.4,
            "api_key": "test-provider-key",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_profile_playground_feedback_and_connector_mapping(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "smart-participation.db"))
    client = TestClient(app)
    login(client)
    serena = create_character(client, "赛琳娜·维尔 Serena Vale")
    mia = create_character(client, "米娅·贝尔 Mia Bell")

    default_profile = client.get(f"/api/smart-participation/profiles/{mia['id']}")
    assert default_profile.status_code == 200, default_profile.text
    assert default_profile.json()["configured"] is False
    assert default_profile.json()["style"] == "balanced"

    primary = client.put(
        f"/api/smart-participation/profiles/{serena['id']}",
        json={
            "enabled": True,
            "style": "balanced",
            "group_role": "primary",
            "topics": ["banter"],
            "keywords": ["离谱"],
            "trigger_phrases": [],
            "avoid_phrases": ["不要继续"],
            "cooldown_seconds": 120,
            "preferred_follow_up_character_card_id": "",
            "follow_up_window_seconds": 30,
        },
    )
    assert primary.status_code == 200, primary.text
    assert primary.json()["group_role"] == "primary"

    secondary = client.put(
        f"/api/smart-participation/profiles/{mia['id']}",
        json={
            "enabled": True,
            "style": "quiet",
            "group_role": "secondary",
            "topics": ["逻辑漏洞", "嘴硬"],
            "keywords": ["离谱", "尴尬"],
            "trigger_phrases": ["你认真的"],
            "avoid_phrases": ["不要继续", "不舒服"],
            "cooldown_seconds": 180,
            "preferred_follow_up_character_card_id": serena["id"],
            "follow_up_window_seconds": 30,
        },
    )
    assert secondary.status_code == 200, secondary.text
    profile = secondary.json()
    assert profile["configured"] is True
    assert profile["preferred_follow_up_character_card_id"] == serena["id"]

    preview_message = "等等,这个逻辑漏洞也太明显了吧,你认真的?"
    preview = client.post(
        f"/api/smart-participation/playground/{mia['id']}/evaluate",
        json={
            "message": preview_message,
            "previous_character_card_id": serena["id"],
        },
    )
    assert preview.status_code == 200, preview.text
    decision = preview.json()
    assert decision["decision"] == "participate"
    assert decision["reason"] == "selected"
    assert decision["follow_up_eligible"] is True
    assert "逻辑漏洞" in decision["matched_topics"]
    assert "你认真的" in decision["matched_trigger_phrases"]

    blocked = client.post(
        f"/api/smart-participation/playground/{mia['id']}/evaluate",
        json={"message": "我有点不舒服,不要继续."},
    )
    assert blocked.status_code == 200, blocked.text
    assert blocked.json()["decision"] == "silent"
    assert blocked.json()["reason"] == "avoid_phrase"

    feedback = client.post(
        f"/api/smart-participation/feedback/{mia['id']}",
        json={
            "message": preview_message,
            "previous_character_card_id": serena["id"],
            "predicted_decision": decision["decision"],
            "predicted_reason": decision["reason"],
            "score": decision["score"],
            "minimum_score": decision["minimum_score"],
            "signals": decision["signals"],
            "feedback_label": "correct",
        },
    )
    assert feedback.status_code == 201, feedback.text
    assert feedback.json()["feedback_label"] == "correct"

    connection = client.post(
        "/api/connections",
        json={
            "platform": "discord",
            "display_name": "Smart Discord",
            "connection_mode": "managed",
            "external_account_id": "bot-smart",
            "status": "connected",
            "metadata": {},
        },
    )
    assert connection.status_code == 201, connection.text
    deployment = client.post(
        "/api/deployments",
        json={
            "character_card_id": mia["id"],
            "connection_id": connection.json()["id"],
            "workspace_id": "guild-smart",
            "workspace_name": "Smart Guild",
            "channel_id": "channel-smart",
            "channel_name": "smart-room",
            "thread_id": "",
            "thread_name": "",
            "participation_mode": "smart",
            "memory_scope": "channel_isolated",
            "version_label": "Current",
            "sticker_count": 0,
            "status": "active",
        },
    )
    assert deployment.status_code == 201, deployment.text

    connector_profiles = client.get(
        "/api/smart-participation/connector-profiles",
        params={"connection_id": connection.json()["id"]},
        headers={"Authorization": f"Bearer {CONNECTOR_SECRET}"},
    )
    assert connector_profiles.status_code == 200, connector_profiles.text
    mapped = connector_profiles.json()[deployment.json()["id"]]
    assert mapped["character_card_id"] == mia["id"]
    assert mapped["group_role"] == "secondary"


def test_secondary_cannot_follow_itself(tmp_path: Path) -> None:
    client = TestClient(create_app(settings(tmp_path / "smart-self.db")))
    login(client)
    mia = create_character(client, "Mia")
    response = client.put(
        f"/api/smart-participation/profiles/{mia['id']}",
        json={
            "enabled": True,
            "style": "balanced",
            "group_role": "secondary",
            "preferred_follow_up_character_card_id": mia["id"],
            "follow_up_window_seconds": 30,
        },
    )
    assert response.status_code == 422