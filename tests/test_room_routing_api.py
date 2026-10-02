"""Production Connector path: routing is source-scoped, idempotent and failure-aware."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from test_character_turn_graph import CONNECTOR_SECRET, seed, settings

from echo_masque.api import create_app
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord
from echo_masque.room_director import DirectorDecision, DirectorResult
from echo_masque.room_routing import RoomScope

HEADERS = {"Authorization": f"Bearer {CONNECTOR_SECRET}"}


@pytest.fixture
def setup(tmp_path: Path) -> tuple[object, TestClient, dict[str, object], dict[str, object]]:
    app = create_app(settings(tmp_path / "room-api.db"))
    client = TestClient(app)
    connection, deployment = seed(app, client)
    return app, client, connection, deployment


def source(id: str = "m1", **changes: object) -> dict[str, object]:
    return {
        "message_id": id,
        "channel_id": "channel-phase3",
        "author_id": "alice",
        "author_display_name": "Alice",
        "text": "Ann, help me plan a game.",
        "created_at": datetime.now(UTC).isoformat(),
        **changes,
    }


def routing(
    connection: dict[str, object], deployment: dict[str, object], **changes: object
) -> dict[str, object]:
    return {
        "connection_id": connection["id"],
        "guild_id": "guild-phase3",
        "channel_id": "channel-phase3",
        "request_id": "m1",
        "trigger_message_id": "m1",
        "deployment_ids": [deployment["id"]],
        "explicit_deployment_ids": [deployment["id"]],
        "messages": [source()],
        "permission_checked_at": datetime.now(UTC).isoformat(),
        **changes,
    }


def call(client: TestClient, body: dict[str, object]) -> dict[str, object]:
    result = client.post("/api/connectors/discord/rooms/resolve", json=body, headers=HEADERS)
    assert result.status_code == 200, result.text
    return result.json()


def smart(app: object, deployment: dict[str, object]) -> None:
    with app.state.database.session() as session:
        record = session.get(CharacterDeploymentRecord, deployment["id"])
        record.participation_mode = "smart"
        session.commit()


def test_direct_zero_provider_calls_and_exact_selection(setup: tuple) -> None:
    app, client, connection, deployment = setup
    app.state.room_director = SimpleNamespace()  # Any attempted call would fail.
    body = routing(connection, deployment)
    result = call(client, body)
    assert result["outcome"] == "direct"
    assert result["attempts"] == []
    assert result["choices"][0]["target_message_id"] == "m1"
    # Retry with new unrelated history does not create a second provider request/selection.
    body["messages"] += [source("m2", text="Lunch tomorrow?")]
    replay = call(client, body)
    assert replay == result
    assert "persona" not in str(result)


def test_context_action_actor_is_not_source_author(setup: tuple) -> None:
    app, client, connection, deployment = setup
    result = call(
        client,
        routing(
            connection,
            deployment,
            request_id="action-1",
            action_actor_id="bob",
            action_target_message_id="old-question",
            messages=[source("old-question", text="Alice's question"), source()],
        ),
    )
    assert result["outcome"] == "direct"
    with app.state.database.session() as session:
        role = session.get(CharacterDeploymentRecord, deployment["id"])
    scope = RoomScope(
        owner_id=role.owner_id,
        connection_id=connection["id"],
        guild_id="guild-phase3",
        channel_id="channel-phase3",
    )
    selection = app.state.room_repository.selection(
        scope, result["choices"][0]["selection_id"], deployment["id"]
    )
    assert selection.requester_id == "bob"
    assert selection.request_id == "action-1"
    assert selection.target_message_id == "old-question"
    assert selection.origin == "context_action"
    assert selection.requester_is_bot is False


def test_wrong_room_and_unverified_character_rejected_before_model(setup: tuple) -> None:
    app, client, connection, deployment = setup
    app.state.room_director = SimpleNamespace()
    result = client.post(
        "/api/connectors/discord/rooms/resolve",
        headers=HEADERS,
        json=routing(connection, deployment, messages=[source(channel_id="secret-thread")]),
    )
    assert result.status_code == 403
    result = client.post(
        "/api/connectors/discord/rooms/resolve",
        headers=HEADERS,
        json=routing(
            connection,
            deployment,
            messages=[source(author_is_bot=True, author_deployment_id=deployment["id"])],
        ),
    )
    assert result.status_code == 403


def test_mention_only_role_cannot_be_selected_for_ambient(setup: tuple) -> None:
    app, client, connection, deployment = setup
    app.state.room_director = SimpleNamespace()
    result = call(
        client, routing(connection, deployment, explicit_deployment_ids=[], ambient_requested=True)
    )
    assert result["outcome"] == "none"
    assert result["reason"] == "no_eligible_roles"
    assert not result["choices"]


def test_none_unavailable_and_failure_not_conflated(setup: tuple) -> None:
    app, client, connection, deployment = setup
    smart(app, deployment)
    body = routing(connection, deployment, explicit_deployment_ids=[], ambient_requested=True)
    result = call(client, body)
    assert result["outcome"] == "unavailable"  # No operator-qualified live member.
    assert result["attempts"] == []
    # A failed logical decision is replayed; silence isn't fabricated and calls aren't retried.
    assert call(client, body) == result


def test_model_cannot_promote_private_card_and_deactivation_is_rechecked(setup: tuple) -> None:
    app, client, connection, deployment = setup
    smart(app, deployment)
    seen = []

    class Director:
        async def decide(self, view: object) -> DirectorResult:
            seen.append(view.user_prompt)
            assert "calm and careful" not in view.user_prompt
            assert "memory" not in view.user_prompt
            with app.state.database.session() as session:
                record = session.get(CharacterDeploymentRecord, deployment["id"])
                record.status = "paused"
                session.commit()
            return DirectorResult(
                outcome="decision",
                input_fingerprint=view.fingerprint,
                decision=DirectorDecision(
                    speaker=deployment["id"], target_message_id="m1", mode="supplement"
                ),
            )

    app.state.room_director = Director()
    result = call(
        client, routing(connection, deployment, explicit_deployment_ids=[], ambient_requested=True)
    )
    assert len(seen) == 1
    assert result["outcome"] == "blocked"
    assert result["reason"] == "selected_role_revoked"
    assert result["choices"] == []


def test_source_deleted_during_model_does_not_fall_back_to_latest(setup: tuple) -> None:
    app, client, connection, deployment = setup
    smart(app, deployment)

    class Director:
        async def decide(self, view: object) -> DirectorResult:
            from echo_masque.room_sources import SourceMessage

            app.state.room_repository.observe(
                view.scope, [SourceMessage.model_validate(source(deleted=True, text=""))]
            )
            return DirectorResult(
                outcome="decision",
                input_fingerprint=view.fingerprint,
                decision=DirectorDecision(
                    speaker=deployment["id"], target_message_id="m1", mode="supplement"
                ),
            )

    app.state.room_director = Director()
    result = call(
        client,
        routing(
            connection,
            deployment,
            explicit_deployment_ids=[],
            ambient_requested=True,
            messages=[source(), source("m2")],
        ),
    )
    assert result["outcome"] == "blocked"
    assert result["reason"] == "target_unavailable"
    assert result["choices"] == []


def test_stale_permission_cannot_reopen_revoked_room(setup: tuple) -> None:
    _app, client, connection, deployment = setup
    old = datetime.now(UTC) - timedelta(seconds=2)
    body = routing(connection, deployment, permission_checked_at=old.isoformat())
    assert call(client, body)["outcome"] == "direct"
    event = {k: body[k] for k in ("connection_id", "guild_id", "channel_id")}
    result = client.post(
        "/api/connectors/discord/rooms/events",
        headers=HEADERS,
        json={**event, "readable": False, "permission_checked_at": datetime.now(UTC).isoformat()},
    )
    assert result.status_code == 200, result.text
    result = client.post("/api/connectors/discord/rooms/resolve", headers=HEADERS, json=body)
    assert result.status_code == 409
    assert result.json()["detail"] == "room_access_revoked"


def test_no_shared_secret_no_ingest_or_routing(setup: tuple) -> None:
    _, client, connection, deployment = setup
    response = client.post(
        "/api/connectors/discord/rooms/resolve", json=routing(connection, deployment)
    )
    assert response.status_code in (401, 403)


def test_real_generated_reply_needs_current_preflight_before_delivery(setup: tuple) -> None:
    from test_character_turn_graph import payload

    _app, client, connection, deployment = setup
    body = routing(connection, deployment)
    choice = call(client, body)["choices"][0]
    incoming = payload(connection, deployment, mentioned_bot=True).model_dump(mode="json")
    incoming.update(
        message_id="m1",
        author_id="alice",
        text="Ann, help me plan a game.",
        source_selection_id=choice["selection_id"],
    )
    # Field name is an actual schema contract, not a caller-specified context trace.
    response = client.post("/api/connectors/discord/messages", headers=HEADERS, json=incoming)
    assert response.status_code == 200, response.text
    reply = response.json()
    assert reply["delivery_required"]
    claim = dict(
        connection_id=connection["id"],
        operation_id=reply["operation_id"],
        step_id=reply["step_id"],
        claim_nonce="current-preflight-test",
    )
    denied = client.post(
        "/api/connectors/discord/messages/delivery/claim", headers=HEADERS, json=claim
    )
    assert denied.status_code == 409 and "draft_preflight_required" in denied.text
    evidence = {
        key: body[key]
        for key in ("connection_id", "guild_id", "channel_id", "messages", "permission_checked_at")
    }
    check = client.post(
        "/api/connectors/discord/rooms/drafts/preflight",
        headers=HEADERS,
        json={
            **evidence,
            "operation_id": reply["operation_id"],
            "step_id": reply["step_id"],
            "writable": True,
        },
    )
    assert check.status_code == 200, check.text
    assert check.json()["disposition"] == "keep"
    assert (
        client.post(
            "/api/connectors/discord/messages/delivery/claim", headers=HEADERS, json=claim
        ).status_code
        == 200
    )


def test_preflight_rejects_client_draft_or_cross_room_operation(setup: tuple) -> None:
    _app, client, connection, deployment = setup
    evidence = routing(connection, deployment)
    data = {
        key: evidence[key]
        for key in ("connection_id", "guild_id", "channel_id", "messages", "permission_checked_at")
    }
    data.update(operation_id="x" * 64, step_id="y" * 64, writable=True)
    assert (
        client.post(
            "/api/connectors/discord/rooms/drafts/preflight", headers=HEADERS, json=data
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/connectors/discord/rooms/drafts/preflight",
            headers=HEADERS,
            json={**data, "reply": {"text": "client-made"}},
        ).status_code
        == 422
    )
    assert (
        client.post("/api/connectors/discord/rooms/drafts/preflight", json=data).status_code == 401
    )


def test_room_buffer_policy_is_authenticated_without_old_profile_endpoint(setup: tuple) -> None:
    _app, client, connection, _ = setup
    path = f"/api/connectors/discord/rooms/runtime?connection_id={connection['id']}"
    assert client.get(path).status_code == 401
    response = client.get(path, headers=HEADERS)
    assert response.status_code == 200
    assert set(response.json()) == {
        "enabled",
        "quiet_window_ms",
        "max_wait_ms",
        "max_messages",
        "max_characters",
    }
    assert (
        client.get("/api/smart-participation/connector-profiles", headers=HEADERS).status_code
        == 404
    )
