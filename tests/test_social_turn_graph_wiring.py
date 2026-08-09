from pathlib import Path

from fastapi.testclient import TestClient
from pydantic import SecretStr

from echo_masque.api import create_app
from echo_masque.api.connector_schemas import DiscordConnectorReplyView
from echo_masque.api.social_turn_schemas import (
    DiscordSocialTurnCursor,
    DiscordSocialTurnStepRequest,
    DiscordSocialTurnStepView,
)
from echo_masque.config import LangGraphMode, Settings
from echo_masque.orchestration import SocialTurnGraphRunner

CONNECTOR_SECRET = "phase4-social-secret"


def settings(path: Path, *, mode: LangGraphMode) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{path}",
        browser_tools_enabled=False,
        semantic_participation_enabled=False,
        legacy_local_user_enabled=False,
        connector_shared_secret=SecretStr(CONNECTOR_SECRET),
        langgraph_mode=mode,
    )


def request_payload() -> dict[str, object]:
    return {
        "payload": {
            "connection_id": "connection-1",
            "deployment_id": "deployment-a",
            "message_id": "message-1",
            "guild_id": "guild-1",
            "guild_name": "Guild",
            "channel_id": "channel-1",
            "channel_name": "general",
            "category_id": "",
            "thread_id": "",
            "thread_name": "",
            "author_id": "user-1",
            "author_display_name": "Juen",
            "text": "hello",
            "mentioned_bot": True,
            "replied_to_bot": False,
            "smart_candidate": True,
            "author_is_bot": False,
            "recent_messages": [],
        },
        "initial_deployment_ids": ["deployment-a"],
        "available_deployment_ids": ["deployment-a"],
        "continuation_budget": 8,
        "max_depth": 4,
    }


def test_social_runner_only_wires_at_social_turn_mode(tmp_path: Path) -> None:
    for mode in ("off", "condition_watch", "character_turn"):
        app = create_app(settings(tmp_path / f"{mode}.db", mode=mode))
        assert app.state.social_turn_graph_runner is None

    social_app = create_app(settings(tmp_path / "social.db", mode="social_turn"))
    assert isinstance(social_app.state.social_turn_graph_runner, SocialTurnGraphRunner)


def test_social_endpoint_rejects_when_rollout_is_not_enabled(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "character.db", mode="character_turn"))
    client = TestClient(app)
    response = client.post(
        "/api/connectors/discord/social-turns/step",
        headers={"Authorization": f"Bearer {CONNECTOR_SECRET}"},
        json=request_payload(),
    )
    assert response.status_code == 409
    assert "not enabled" in response.json()["detail"]


def test_social_endpoint_dispatches_to_runner(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "dispatch.db", mode="social_turn"))
    called: list[str] = []

    class FakeSocialRunner:
        async def __call__(
            self,
            request: DiscordSocialTurnStepRequest,
        ) -> DiscordSocialTurnStepView:
            called.append(request.payload.deployment_id)
            return DiscordSocialTurnStepView(
                reply=DiscordConnectorReplyView(
                    action="silent",
                    reason="social-graph-dispatch",
                    deployment_id=request.payload.deployment_id,
                ),
                cursor=DiscordSocialTurnCursor(
                    pending_turns=[],
                    completed_deployment_ids=[request.payload.deployment_id],
                    continuation_budget_remaining=8,
                    max_depth=4,
                    step_index=1,
                ),
                current_deployment_id=request.payload.deployment_id,
                done=True,
                stop_reason="completed",
            )

    app.state.social_turn_graph_runner = FakeSocialRunner()
    client = TestClient(app)
    response = client.post(
        "/api/connectors/discord/social-turns/step",
        headers={"Authorization": f"Bearer {CONNECTOR_SECRET}"},
        json=request_payload(),
    )

    assert response.status_code == 200, response.text
    assert response.json()["reply"]["reason"] == "social-graph-dispatch"
    assert response.json()["done"] is True
    assert called == ["deployment-a"]
