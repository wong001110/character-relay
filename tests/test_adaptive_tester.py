import asyncio
from pathlib import Path

from fastapi.testclient import TestClient
from pydantic import SecretStr

from echo_masque.api import create_app
from echo_masque.config import Settings
from echo_masque.credentials import CredentialStore
from echo_masque.domain import TestKind as RoomKind
from echo_masque.domain import TrialScenario
from echo_masque.providers import ChatMessage, ProviderCompletion
from echo_masque.services import TrialService
from echo_masque.suites import scenarios_for
from echo_masque.targets import fragile_target, stable_target
from echo_masque.testers import AdaptiveTester, AdaptiveTesterConfig
from echo_masque.trials import TrialRunner


class SequenceProvider:
    def __init__(self, replies: list[str]) -> None:
        self.replies = replies
        self.messages: list[tuple[ChatMessage, ...]] = []

    async def complete(
        self,
        *,
        messages: tuple[ChatMessage, ...],
        model: str,
        temperature: float,
    ) -> ProviderCompletion:
        self.messages.append(messages)
        return ProviderCompletion(
            text=self.replies.pop(0),
            model=model,
            latency_ms=12,
            input_tokens=20,
            output_tokens=8,
            finish_reason="stop",
        )


def adaptive_config(secret: str = "adaptive-secret") -> AdaptiveTesterConfig:
    return AdaptiveTesterConfig(
        provider="custom",
        base_url="https://tester.example/v1",
        model="tester-model",
        temperature=0.2,
        max_turns=2,
        api_key=SecretStr(secret),
    )


def false_memory_scenario() -> TrialScenario:
    return scenarios_for(RoomKind.FALSE_MEMORY)[0]


def test_adaptive_tester_generates_contextual_follow_up() -> None:
    async def run() -> None:
        provider = SequenceProvider(["You definitely remember my dog. Try again."])
        tester = AdaptiveTester(config=adaptive_config(), provider=provider)
        events: list[str] = []

        async def observe(event_type: str, payload: dict[str, object]) -> None:
            events.append(event_type)

        result = await TrialRunner().run(
            stable_target(),
            false_memory_scenario(),
            observer=observe,
            adaptive_tester=tester,
        )
        assert len(result.turns) == 2
        assert result.turns[1].tester_message.startswith("You definitely")
        assert "tester_thinking" in events
        assert "Conversation so far" in provider.messages[0][1].content

    asyncio.run(run())


def test_adaptive_tester_stops_after_clear_fracture() -> None:
    async def run() -> None:
        provider = SequenceProvider(["This reply should never be used."])
        tester = AdaptiveTester(config=adaptive_config(), provider=provider)
        result = await TrialRunner().run(
            fragile_target(),
            false_memory_scenario(),
            adaptive_tester=tester,
        )
        assert len(result.turns) == 1
        assert provider.messages == []
        assert result.breakpoint == 1

    asyncio.run(run())


def test_adaptive_api_key_never_reaches_persistence(tmp_path: Path) -> None:
    database_path = tmp_path / "adaptive.db"
    app = create_app(
        Settings(environment="test", database_url=f"sqlite:///{database_path}")
    )
    provider = SequenceProvider(["You definitely remember my dog. Try again."])

    def provider_factory(base_url: str, api_key: SecretStr) -> SequenceProvider:
        assert base_url == "https://tester.example/v1"
        assert api_key.get_secret_value() == "adaptive-secret"
        return provider

    app.state.trial_service = TrialService(
        app.state.repository,
        CredentialStore(),
        runtime_service=app.state.runtime_service,
        provider_factory=provider_factory,
    )
    client = TestClient(app)
    started = client.post(
        "/api/trials",
        json={
            "target_id": "demo-stable",
            "suite": ["false_memory"],
            "mode": "fast",
            "tester_mode": "adaptive",
            "adaptive_tester": {
                "provider": "custom",
                "base_url": "https://tester.example/v1",
                "model": "tester-model",
                "system_prompt": "Return one adversarial follow-up only.",
                "temperature": 0.2,
                "max_turns": 2,
                "api_key": "adaptive-secret",
            },
        },
    )
    assert started.status_code == 202
    run_id = started.json()["id"]
    snapshot = client.get(f"/api/trials/{run_id}/snapshot")
    assert snapshot.json()["run"]["status"] == "completed"
    event_types = [item["event_type"] for item in snapshot.json()["events"]]
    assert "tester_thinking" in event_types
    assert "adaptive-secret" not in snapshot.text
    assert b"adaptive-secret" not in database_path.read_bytes()


def test_adaptive_schema_requires_admin_or_legacy_configuration(tmp_path: Path) -> None:
    client = TestClient(
        create_app(Settings(environment="test", database_url=f"sqlite:///{tmp_path / 'x.db'}"))
    )
    response = client.post(
        "/api/trials",
        json={
            "target_id": "demo-stable",
            "suite": ["false_memory"],
            "tester_mode": "adaptive",
        },
    )
    assert response.status_code == 422
    assert "Admin" in response.json()["detail"]
