from pathlib import Path

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr

from echo_masque.api import create_app
from echo_masque.api.connector_schemas import DiscordInboundMessage
from echo_masque.config import Settings
from echo_masque.orchestration import CharacterTurnGraphRunner, RuntimeTraceEvent

ADMIN_EMAIL = "phase3-admin@example.com"
ADMIN_PASSWORD = "Phase3CharacterTurn2026!"
CONNECTOR_SECRET = "phase3-connector-secret"


def settings(path: Path) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{path}",
        legacy_local_user_enabled=False,
        bootstrap_admin_email=ADMIN_EMAIL,
        bootstrap_admin_password=SecretStr(ADMIN_PASSWORD),
        credential_encryption_keys=SecretStr(Fernet.generate_key().decode("ascii")),
        connector_shared_secret=SecretStr(CONNECTOR_SECRET),
    )


def seed(app: object, client: TestClient) -> tuple[dict[str, object], dict[str, object]]:
    login = client.post(
        "/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert login.status_code == 200, login.text
    character = client.post(
        "/api/characters",
        json={
            "target_id": "demo-stable",
            "display_name": "Ann",
            "subtitle": "Phase 3 deterministic fixture",
            "subject_type": "companion",
            "persona_summary": "Ann is calm and careful.",
            "traits": ["calm"],
            "tags": ["phase3"],
            "expected_tone": "Concise and gentle.",
            "forbidden_behaviors": ["invent private memories"],
            "memory_summary": "Use only supplied context.",
            "preferred_suites": ["identity_integrity"],
            "portrait_variant": "lavender",
        },
    )
    assert character.status_code == 201, character.text
    connection = client.post(
        "/api/connections",
        json={
            "platform": "discord",
            "display_name": "Phase 3 Discord",
            "connection_mode": "managed",
            "external_account_id": "",
            "status": "disconnected",
            "metadata": {},
        },
    )
    assert connection.status_code == 201, connection.text
    deployment = client.post(
        "/api/deployments",
        json={
            "character_card_id": character.json()["id"],
            "connection_id": connection.json()["id"],
            "workspace_id": "guild-phase3",
            "workspace_name": "Phase 3 Guild",
            "channel_id": "channel-phase3",
            "channel_name": "runtime",
            "thread_id": "",
            "thread_name": "",
            "participation_mode": "mention_and_reply",
            "memory_scope": "channel_isolated",
            "version_label": "Current",
            "sticker_count": 0,
            "status": "active",
        },
    )
    assert deployment.status_code == 201, deployment.text
    return connection.json(), deployment.json()


def payload(
    connection: dict[str, object],
    deployment: dict[str, object],
    *,
    mentioned_bot: bool,
) -> DiscordInboundMessage:
    return DiscordInboundMessage.model_validate(
        {
            "connection_id": connection["id"],
            "deployment_id": deployment["id"],
            "message_id": "message-phase3",
            "guild_id": "guild-phase3",
            "guild_name": "Phase 3 Guild",
            "channel_id": "channel-phase3",
            "channel_name": "runtime",
            "category_id": "",
            "thread_id": "",
            "thread_name": "",
            "author_id": "user-phase3",
            "author_display_name": "Juen",
            "text": "Ann, what do you think?",
            "mentioned_bot": mentioned_bot,
            "replied_to_bot": False,
            "smart_candidate": False,
            "recent_messages": [
                {
                    "message_id": "message-phase3",
                    "author_id": "user-phase3",
                    "author_display_name": "Juen",
                    "text": "Ann, what do you think?",
                    "is_bot": False,
                }
            ],
        }
    )


class TraceCollector:
    def __init__(self) -> None:
        self.events: list[RuntimeTraceEvent] = []

    def emit(self, event: RuntimeTraceEvent) -> None:
        self.events.append(event)


def test_character_turn_graph_matches_direct_runtime(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "phase3-parity.db"))
    client = TestClient(app)
    connection, deployment = seed(app, client)
    incoming = payload(connection, deployment, mentioned_bot=True)

    direct = __import__("asyncio").run(app.state.discord_connector_runtime.respond(incoming))
    traces = TraceCollector()
    runner = CharacterTurnGraphRunner(
        app.state.discord_connector_runtime,
        trace_sink=traces,
    )
    graph_result = __import__("asyncio").run(runner.run(incoming))

    assert graph_result.reply.model_dump() == direct.model_dump()
    assert graph_result.state["status"] == "completed"
    assert graph_result.state["outcome"] == "reply"
    assert graph_result.state["deployment_id"] == deployment["id"]
    assert graph_result.state["character_card_id"] == deployment["character_card_id"]
    assert graph_result.state["context_status"] == "completed"
    assert graph_result.state["model_status"] == "completed"
    assert graph_result.state["smart_output_status"] == "completed"
    assert graph_result.state["authority_status"] == "completed"
    assert graph_result.state["tool_result_count"] == 0

    completed_nodes = [
        event.node_name
        for event in traces.events
        if event.status == "completed"
    ]
    assert completed_nodes == [
        "turn_resolve",
        "turn_context",
        "turn_model",
        "turn_smart_output",
        "turn_authority",
    ]
    assert "Ann, what do you think?" not in repr(traces.events)


def test_character_turn_graph_preserves_early_silent_route(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "phase3-silent.db"))
    client = TestClient(app)
    connection, deployment = seed(app, client)
    incoming = payload(connection, deployment, mentioned_bot=False)

    runner = CharacterTurnGraphRunner(app.state.discord_connector_runtime)
    result = __import__("asyncio").run(runner.run(incoming))

    assert result.reply.action == "silent"
    assert result.reply.reason == "trigger_not_matched"
    assert result.state["status"] == "completed"
    assert result.state["outcome"] == "silent"
    assert result.state["resolve_status"] == "completed"
    assert result.state["context_status"] == "not_started"
    assert result.state["model_status"] == "not_started"
