import json
from pathlib import Path

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr

from echo_masque.api import create_app
from echo_masque.config import Settings
from echo_masque.providers import ChatMessage, ProviderCompletion
from echo_masque.smart_participation_generation import SmartParticipationGenerationService

ADMIN_EMAIL = "smart-generation-admin@example.com"
ADMIN_PASSWORD = "CharacterRelaySmartGeneration2026!"


class FakeProvider:
    async def complete(
        self,
        *,
        messages: tuple[ChatMessage, ...],
        model: str,
        temperature: float,
    ) -> ProviderCompletion:
        assert messages
        assert model
        assert temperature <= 0.3
        return ProviderCompletion(
            text=json.dumps(
                {
                    "enabled": True,
                    "style": "quiet",
                    "group_role": "secondary",
                    "topics": ["逻辑漏洞", "嘴硬"],
                    "keywords": ["离谱", "硬撑"],
                    "trigger_phrases": ["你认真的", "不会吧"],
                    "avoid_phrases": ["不要继续", "不舒服", "认真求助"],
                    "cooldown_seconds": 180,
                    "preferred_follow_up_character_name": "赛琳娜·维尔 Serena Vale",
                    "follow_up_window_seconds": 30,
                    "rationale": "Mia is explicitly the secondary reaction and follow-up partner.",
                },
                ensure_ascii=False,
            ),
            model="fake-smart-model",
            latency_ms=12,
            input_tokens=100,
            output_tokens=80,
        )


def settings(path: Path) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{path}",
        legacy_local_user_enabled=False,
        bootstrap_admin_email=ADMIN_EMAIL,
        bootstrap_admin_password=SecretStr(ADMIN_PASSWORD),
        bootstrap_admin_display_name="Smart Generation Admin",
        credential_encryption_keys=SecretStr(Fernet.generate_key().decode("ascii")),
    )


def login(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200, response.text


def create_character(
    client: TestClient,
    *,
    name: str,
    persona_summary: str,
) -> dict[str, object]:
    response = client.post(
        "/api/characters/prompt-model",
        json={
            "display_name": name,
            "subtitle": "Discord social character",
            "subject_type": "custom",
            "persona_summary": persona_summary,
            "traits": ["social", "concise"],
            "tags": ["discord", "banter"],
            "expected_tone": "Short group-chat replies.",
            "forbidden_behaviors": ["continue when someone asks to stop"],
            "memory_summary": "Use current conversation context only.",
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


def test_ai_generation_returns_reviewable_draft_without_saving(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "smart-generation.db"))
    app.state.smart_participation_generation_service = SmartParticipationGenerationService(
        app.state.repository,
        app.state.authoring_runtime_service,
        provider_factory=lambda: FakeProvider(),
    )
    client = TestClient(app)
    login(client)
    serena = create_character(
        client,
        name="赛琳娜·维尔 Serena Vale",
        persona_summary="Serena leads the banter and sets the tone.",
    )
    mia = create_character(
        client,
        name="米娅·贝尔 Mia Bell",
        persona_summary="Mia follows Serena's lead and adds one short reaction or punchline.",
    )

    generated = client.post(
        f"/api/smart-participation/profiles/{mia['id']}/generate"
    )
    assert generated.status_code == 200, generated.text
    draft = generated.json()
    assert draft["style"] == "quiet"
    assert draft["group_role"] == "secondary"
    assert draft["preferred_follow_up_character_card_id"] == serena["id"]
    assert draft["preferred_follow_up_character_name"] == "赛琳娜·维尔 Serena Vale"
    assert draft["provider_model"] == "fake-smart-model"
    assert "逻辑漏洞" in draft["topics"]

    persisted = client.get(f"/api/smart-participation/profiles/{mia['id']}")
    assert persisted.status_code == 200, persisted.text
    assert persisted.json()["configured"] is False


def test_playground_can_preview_unsaved_profile_override(tmp_path: Path) -> None:
    client = TestClient(create_app(settings(tmp_path / "smart-preview.db")))
    login(client)
    mia = create_character(
        client,
        name="米娅·贝尔 Mia Bell",
        persona_summary="Mia is a short reactive banter character.",
    )

    response = client.post(
        f"/api/smart-participation/playground/{mia['id']}/evaluate",
        json={
            "message": "这个逻辑漏洞也太明显了吧,你认真的?",
            "profile_override": {
                "enabled": True,
                "style": "quiet",
                "group_role": "independent",
                "topics": ["逻辑漏洞"],
                "keywords": [],
                "trigger_phrases": ["你认真的"],
                "avoid_phrases": ["不要继续"],
                "cooldown_seconds": 180,
                "preferred_follow_up_character_card_id": "",
                "follow_up_window_seconds": 30,
            },
        },
    )
    assert response.status_code == 200, response.text
    preview = response.json()
    assert preview["decision"] == "participate"
    assert preview["score"] >= preview["minimum_score"]
    assert preview["matched_topics"] == ["逻辑漏洞"]
    assert preview["matched_trigger_phrases"] == ["你认真的"]

    persisted = client.get(f"/api/smart-participation/profiles/{mia['id']}")
    assert persisted.status_code == 200, persisted.text
    assert persisted.json()["configured"] is False
