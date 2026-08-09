from pathlib import Path

from fastapi.testclient import TestClient
from pydantic import SecretStr

from echo_masque.api import create_app
from echo_masque.api.connector_schemas import DiscordConnectorReplyView
from echo_masque.config import LangGraphMode, Settings
from echo_masque.orchestration import CharacterTurnGraphRunner

CONNECTOR_SECRET = "phase3-wiring-secret"


def settings(path: Path, *, langgraph_mode: LangGraphMode) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{path}",
        browser_tools_enabled=False,
        semantic_participation_enabled=False,
        legacy_local_user_enabled=False,
        connector_shared_secret=SecretStr(CONNECTOR_SECRET),
        langgraph_mode=langgraph_mode,
    )


def test_character_turn_runner_stays_off_before_phase3_mode(tmp_path: Path) -> None:
    for mode in ("off", "condition_watch"):
        app = create_app(settings(tmp_path / f"{mode}.db", langgraph_mode=mode))
        assert app.state.character_turn_graph_runner is None


def test_character_turn_and_later_modes_wire_runner(tmp_path: Path) -> None:
    for mode in ("character_turn", "social_turn"):
        app = create_app(settings(tmp_path / f"{mode}.db", langgraph_mode=mode))
        assert isinstance(app.state.character_turn_graph_runner, CharacterTurnGraphRunner)


def test_connector_message_endpoint_dispatches_to_graph_runner(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "dispatch.db", langgraph_mode="character_turn"))
    called: list[str] = []

    class FakeRunner:
        async def __call__(self, payload: object) -> DiscordConnectorReplyView:
            deployment_id = getattr(payload, "deployment_id")
            called.append(deployment_id)
            return DiscordConnectorReplyView(
                action="silent",
                reason="graph-dispatch",
                deployment_id=deployment_id,
            )

    app.state.character_turn_graph_runner = FakeRunner()
    client = TestClient(app)
    response = client.post(
        "/api/connectors/discord/messages",
        headers={"Authorization": f"Bearer {CONNECTOR_SECRET}"},
        json={
            "connection_id": "connection-1",
            "deployment_id": "deployment-1",
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
            "smart_candidate": False,
            "recent_messages": [],
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["reason"] == "graph-dispatch"
    assert called == ["deployment-1"]
