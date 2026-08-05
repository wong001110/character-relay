from pathlib import Path

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr

from echo_masque.api import create_app
from echo_masque.config import Settings
from echo_masque.expression_retrieval import ExpressionResource, rank_expression_resources

ADMIN_EMAIL = "expression-admin@example.com"
ADMIN_PASSWORD = "ExpressionAdmin2026!"
CONNECTOR_SECRET = "expression-connector-secret"


def settings(path: Path) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{path}",
        legacy_local_user_enabled=False,
        bootstrap_admin_email=ADMIN_EMAIL,
        bootstrap_admin_password=SecretStr(ADMIN_PASSWORD),
        bootstrap_admin_display_name="Expression Admin",
        credential_encryption_keys=SecretStr(Fernet.generate_key().decode("ascii")),
        connector_shared_secret=SecretStr(CONNECTOR_SECRET),
    )


def login(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200, response.text


def connector_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {CONNECTOR_SECRET}"}


def seed(client: TestClient) -> tuple[dict[str, object], dict[str, object]]:
    login(client)
    connection_response = client.post(
        "/api/connections",
        json={
            "platform": "discord",
            "display_name": "Expression Discord",
            "connection_mode": "managed",
            "external_account_id": "bot-expression",
            "status": "connected",
            "metadata": {},
        },
    )
    assert connection_response.status_code == 201, connection_response.text
    connection = connection_response.json()
    character_response = client.post(
        "/api/characters",
        json={
            "target_id": "demo-stable",
            "display_name": "Ann",
            "subtitle": "Expression fixture",
            "subject_type": "companion",
            "persona_summary": "Ann is curious and playful.",
            "traits": ["curious", "playful"],
            "tags": ["discord"],
            "expected_tone": "Light and observant.",
            "forbidden_behaviors": [],
            "memory_summary": "",
            "preferred_suites": ["identity_integrity"],
            "portrait_variant": "lavender",
        },
    )
    assert character_response.status_code == 201, character_response.text
    deployment_response = client.post(
        "/api/deployments",
        json={
            "character_card_id": character_response.json()["id"],
            "connection_id": connection["id"],
            "workspace_id": "guild-expression",
            "workspace_name": "Expression Guild",
            "channel_id": "channel-expression",
            "channel_name": "general",
            "thread_id": "",
            "thread_name": "",
            "participation_mode": "mention_and_reply",
            "memory_scope": "channel_isolated",
            "version_label": "Current",
            "sticker_count": 0,
            "status": "active",
        },
    )
    assert deployment_response.status_code == 201, deployment_response.text
    return connection, deployment_response.json()


def resource(
    key: str,
    *,
    meaning: str,
    tags: tuple[str, ...],
    available: bool = True,
) -> ExpressionResource:
    resource_type, resource_id = key.split(":", maxsplit=1)
    return ExpressionResource(
        key=key,
        resource_type=resource_type,
        resource_id=resource_id,
        name=resource_id,
        description="",
        semantic_intent="reaction",
        semantic_emotion="curious",
        semantic_description=meaning,
        aliases=(),
        tags=tags,
        situations=(),
        avoid_when=(),
        allowed_actions=("reaction",),
        animated=False,
        available=available,
        enabled=True,
        semantic_confidence=1.0,
        asset_url="",
        format_type=resource_type,
    )


def test_hybrid_retrieval_filters_unavailable_and_penalizes_repetition() -> None:
    resources = [
        resource("emoji:peek", meaning="好奇地偷偷观察,等待后续", tags=("好奇", "期待")),
        resource("emoji:wave", meaning="友好地打招呼", tags=("问候",)),
        resource(
            "emoji:missing",
            meaning="好奇地观察",
            tags=("好奇",),
            available=False,
        ),
    ]
    ranked = rank_expression_resources(
        resources,
        query="我很好奇,想偷偷看看后续",
        allowed_actions={"reaction"},
        top_k=3,
    )
    assert next(item.resource.key for item in ranked) == "emoji:peek"
    assert all(item.resource.key != "emoji:missing" for item in ranked)

    repeated = rank_expression_resources(
        resources,
        query="我很好奇,想偷偷看看后续",
        allowed_actions={"reaction"},
        recent_resource_keys={"emoji:peek"},
        top_k=3,
    )
    peek = next(item for item in repeated if item.resource.key == "emoji:peek")
    assert peek.signals["recent_penalty"] > 0


def test_expression_dictionary_retrieval_and_nodes_are_owner_scoped(tmp_path: Path) -> None:
    client = TestClient(create_app(settings(tmp_path / "expressions.db")))
    connection, deployment = seed(client)
    catalog = client.put(
        "/api/connectors/discord/server-catalog",
        headers=connector_headers(),
        json={
            "connection_id": connection["id"],
            "servers": [
                {
                    "guild_id": "guild-expression",
                    "guild_name": "Expression Guild",
                    "channels": [
                        {
                            "id": "channel-expression",
                            "name": "general",
                            "category_id": "",
                            "category_name": "",
                            "type": "text",
                        }
                    ],
                    "emojis": [
                        {
                            "emoji_id": "emoji-peek",
                            "name": "ann_peek",
                            "animated": False,
                            "available": True,
                            "asset_url": "https://cdn.discordapp.com/emojis/emoji-peek.png",
                        },
                        {
                            "emoji_id": "emoji-wave",
                            "name": "ann_wave",
                            "animated": False,
                            "available": True,
                            "asset_url": "https://cdn.discordapp.com/emojis/emoji-wave.png",
                        },
                    ],
                    "stickers": [
                        {
                            "sticker_id": "sticker-side-eye",
                            "name": "side_eye",
                            "description": "A doubtful cat",
                            "tags": ["doubt"],
                            "format_type": "png",
                            "asset_url": "https://cdn.discordapp.com/stickers/sticker-side-eye.png",
                        }
                    ],
                }
            ],
        },
    )
    assert catalog.status_code == 204, catalog.text

    listed = client.get(
        f"/api/discord/expression-dictionary?connection_id={connection['id']}"
        "&guild_id=guild-expression"
    )
    assert listed.status_code == 200, listed.text
    assert {item["resource_type"] for item in listed.json()} == {"emoji", "sticker"}

    peek = next(item for item in listed.json() if item["resource_id"] == "emoji-peek")
    manual = client.put(
        "/api/discord/expression-dictionary",
        json={
            **{
                key: peek[key]
                for key in (
                    "connection_id",
                    "guild_id",
                    "resource_type",
                    "resource_id",
                    "name",
                    "description",
                    "tags",
                    "format_type",
                    "asset_url",
                    "animated",
                    "available",
                )
            },
            "enabled": True,
            "semantic_intent": "curious_peek",
            "semantic_emotion": "curious",
            "semantic_description": "好奇地偷偷观察,也期待对方继续说。",
            "aliases": ["peek", "偷看"],
            "situations": ["等待后续", "轻微吃瓜"],
            "avoid_when": ["正式道歉"],
            "allowed_actions": ["inline", "reaction"],
        },
    )
    assert manual.status_code == 200, manual.text
    assert manual.json()["semantic_source"] == "manual"

    retrieval = client.post(
        "/api/connectors/discord/expressions/retrieve",
        headers=connector_headers(),
        json={
            "connection_id": connection["id"],
            "guild_id": "guild-expression",
            "channel_id": "channel-expression",
            "source_message_id": "message-expression",
            "deployment_id": deployment["id"],
            "query": "我有一点好奇,想偷偷看看接下来会发生什么",
            "allowed_actions": ["inline", "reaction", "sticker"],
            "excluded_resource_keys": [],
            "top_k": 6,
        },
    )
    assert retrieval.status_code == 200, retrieval.text
    body = retrieval.json()
    assert body["retrieval_backend"] == "hybrid_sparse_v1"
    assert body["candidates"][0]["resource_key"] == "emoji:emoji-peek"

    selected = client.post(
        f"/api/connectors/discord/expressions/runs/{body['run_id']}/nodes",
        headers=connector_headers(),
        json={
            "connection_id": connection["id"],
            "node_name": "model_select",
            "status": "completed",
            "input_summary": {"candidate_count": len(body["candidates"])},
            "output_summary": {
                "action": "reaction",
                "resource_key": "emoji:emoji-peek",
            },
            "error": "",
            "selected_action": "reaction",
            "selected_resource_key": "emoji:emoji-peek",
        },
    )
    assert selected.status_code == 204, selected.text
    completed = client.post(
        f"/api/connectors/discord/expressions/runs/{body['run_id']}/nodes",
        headers=connector_headers(),
        json={
            "connection_id": connection["id"],
            "node_name": "execute_delivery",
            "status": "completed",
            "input_summary": {"action": "reaction"},
            "output_summary": {"expression_applied": True},
            "error": "",
            "selected_action": "reaction",
            "selected_resource_key": "emoji:emoji-peek",
            "final_status": "completed",
        },
    )
    assert completed.status_code == 204, completed.text

    detail = client.get(f"/api/discord/expression-runs/{body['run_id']}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["status"] == "completed"
    assert [node["node_name"] for node in detail.json()["nodes"]] == [
        "filter_resources",
        "rank_candidates",
        "model_select",
        "execute_delivery",
    ]
    assert "query" not in detail.json()["state"]
    assert detail.json()["state"]["query_summary"]["length"] > 0


def test_exact_custom_emoji_resolution_uses_dictionary_semantics(tmp_path: Path) -> None:
    client = TestClient(create_app(settings(tmp_path / "emoji-resolve.db")))
    connection, _ = seed(client)
    resolved = client.post(
        "/api/connectors/discord/expressions/resolve",
        headers=connector_headers(),
        json={
            "connection_id": connection["id"],
            "guild_id": "guild-expression",
            "resource_type": "emoji",
            "resource_id": "emoji-exact",
            "name": "exact_emoji",
            "animated": False,
            "available": True,
            "asset_url": "",
        },
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["resource_key"] == "emoji:emoji-exact"
    assert resolved.json()["semantic_source"] == "discord_metadata"
