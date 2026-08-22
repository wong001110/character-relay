from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr

from echo_masque.api import create_app
from echo_masque.api.connector_schemas import DiscordConnectorReplyView
from echo_masque.api.social_turn_schemas import (
    DiscordSocialTurnCursor,
    DiscordSocialTurnStepView,
)
from echo_masque.config import Settings
from echo_masque.connector_runtime import ConnectorRuntimeError
from echo_masque.discord_debug_capture import (
    DiscordDebugCaptureConflict,
    InMemoryDiscordDebugCaptureStore,
)

ADMIN_EMAIL = "discord-debug-super@example.com"
ADMIN_PASSWORD = "DiscordDebugSuper2026!"
CONNECTOR_SECRET = "discord-debug-connector-secret"
RAW_TEXT = "private discord debug payload only"


class Clock:
    def __init__(self) -> None:
        self.value = datetime(2026, 8, 23, 8, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.value

    def advance(self, *, minutes: int) -> None:
        self.value += timedelta(minutes=minutes)


def app_settings(path: Path) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{path}",
        legacy_local_user_enabled=False,
        public_registration_enabled=True,
        bootstrap_admin_email=ADMIN_EMAIL,
        bootstrap_admin_password=SecretStr(ADMIN_PASSWORD),
        bootstrap_admin_display_name="Discord Debug Super Admin",
        credential_encryption_keys=SecretStr(Fernet.generate_key().decode("ascii")),
        connector_shared_secret=SecretStr(CONNECTOR_SECRET),
        request_limit_per_minute=1000,
    )


def login(client: TestClient, email: str, password: str = ADMIN_PASSWORD) -> None:
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text


def register(client: TestClient, email: str) -> str:
    response = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "display_name": email.split("@", maxsplit=1)[0],
            "password": ADMIN_PASSWORD,
        },
    )
    assert response.status_code == 201, response.text
    return str(response.json()["user"]["id"])


def connector_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {CONNECTOR_SECRET}"}


def create_runtime_scope(app: object, client: TestClient) -> tuple[str, str, str]:
    connection_response = client.post(
        "/api/connections",
        json={
            "platform": "discord",
            "display_name": "Debug Discord Connector",
            "connection_mode": "managed",
            "external_account_id": "debug-bot",
            "status": "connected",
            "metadata": {},
        },
    )
    assert connection_response.status_code == 201, connection_response.text
    connection_id = str(connection_response.json()["id"])
    profile_response = client.post(
        "/api/discord/server-profiles",
        json={
            "connection_id": connection_id,
            "name": "Debug Server",
            "guild_id": "guild-debug",
            "guild_name": "Debug Guild",
            "excluded_channel_ids": [],
            "excluded_category_ids": [],
            "thread_policy": "inherit_parent",
        },
    )
    assert profile_response.status_code == 201, profile_response.text
    profile_id = str(profile_response.json()["id"])
    user = app.state.auth_repository.get_user_by_email(ADMIN_EMAIL)
    assert user is not None
    card = app.state.repository.create_character_card(
        owner_id=user.id,
        target_id="demo-stable",
        display_name="Debug Character",
        subtitle="Debug capture test",
        subject_type="companion",
        persona_summary="Stable test identity.",
        traits=["stable"],
        tags=["debug"],
        expected_tone="Calm",
        forbidden_behaviors=[],
        memory_summary=None,
        preferred_suites=["identity_integrity"],
        portrait_variant="lavender",
    )
    deployment = app.state.deployment_repository.create_deployment(
        owner_id=user.id,
        character_card_id=card.id,
        connection_id=connection_id,
        server_profile_id=profile_id,
        workspace_id="",
        workspace_name="",
        channel_id="",
        channel_name="",
        thread_id="",
        thread_name="",
        participation_mode="mention_and_reply",
        memory_scope="channel_isolated",
        version_label="Current",
        sticker_count=0,
        status="active",
        excluded_channel_ids=[],
        excluded_category_ids=[],
    )
    app.state.character_turn_graph_runner = None
    app.state.discord_connector_runtime = SimpleNamespace(
        respond=AsyncMock(
            return_value=DiscordConnectorReplyView(
                action="silent",
                reason="test_success",
                deployment_id=deployment.id,
            )
        )
    )
    return connection_id, profile_id, deployment.id


def inbound_message(
    connection_id: str,
    deployment_id: str,
    *,
    message_id: str = "message-debug-1",
    guild_id: str = "guild-debug",
) -> dict[str, object]:
    return {
        "connection_id": connection_id,
        "deployment_id": deployment_id,
        "message_id": message_id,
        "guild_id": guild_id,
        "guild_name": "Debug Guild",
        "channel_id": "channel-debug",
        "channel_name": "debug-room",
        "author_id": "discord-user",
        "author_display_name": "Debug User",
        "text": RAW_TEXT,
        "mentioned_bot": True,
        "available_characters": [deployment_id],
        "runtime_operation_id": "operation-debug",
        "runtime_step_id": "step-debug",
    }


def test_in_memory_store_prunes_ttl_stops_deduplicates_and_evicts_fifo() -> None:
    clock = Clock()
    store = InMemoryDiscordDebugCaptureStore(
        now=clock,
        maximum_records=2,
        maximum_bytes=100_000,
    )
    session = store.start_session(
        owner_id="owner",
        server_profile_id="profile",
        connection_id="connection",
        guild_id="guild",
        guild_name="Guild",
        ttl_minutes=15,
    )
    first = store.capture(
        connection_id="connection",
        guild_id="guild",
        source_message_id="message-1",
        channel_id="channel",
        thread_id="",
        deployment_id="deployment",
        runtime_operation_id="operation",
        runtime_step_id="step",
        character_count=1,
        payload={"text": "first"},
    )
    duplicate = store.capture(
        connection_id="connection",
        guild_id="guild",
        source_message_id="message-1",
        channel_id="channel",
        thread_id="",
        deployment_id="deployment",
        runtime_operation_id="operation",
        runtime_step_id="step",
        character_count=1,
        payload={"text": "first changed"},
    )
    assert first is not None
    assert duplicate is not None and duplicate.id == first.id
    for message_id in ("message-2", "message-3"):
        store.capture(
            connection_id="connection",
            guild_id="guild",
            source_message_id=message_id,
            channel_id="channel",
            thread_id="",
            deployment_id="deployment",
            runtime_operation_id=message_id,
            runtime_step_id="step",
            character_count=1,
            payload={"text": message_id},
        )
    current = store.current_session(owner_id="owner", server_profile_id="profile")
    assert current is not None
    assert current.record_count == 2
    assert current.evicted_record_count == 1
    records, total = store.list_records(session.id, owner_id="owner", page=1, page_size=10)
    assert total == 2
    assert [item.source_message_id for item in records] == ["message-3", "message-2"]
    stopped = store.stop_session(session.id, owner_id="owner")
    assert stopped is not None and stopped.status_at(clock()) == "stopped"
    assert stopped.record_count == 2
    stopped_current = store.current_session(owner_id="owner", server_profile_id="profile")
    assert stopped_current is not None and stopped_current.id == stopped.id
    assert store.capture(
        connection_id="connection",
        guild_id="guild",
        source_message_id="message-4",
        channel_id="channel",
        thread_id="",
        deployment_id="deployment",
        runtime_operation_id="operation-4",
        runtime_step_id="step",
        character_count=1,
        payload={"text": "not captured"},
    ) is None

    expiring = store.start_session(
        owner_id="owner",
        server_profile_id="profile",
        connection_id="connection",
        guild_id="guild",
        guild_name="Guild",
        ttl_minutes=15,
    )
    replaced = store.get_session(session.id, owner_id="owner")
    assert replaced is None
    store.capture(
        connection_id="connection",
        guild_id="guild",
        source_message_id="expiring",
        channel_id="channel",
        thread_id="",
        deployment_id="deployment",
        runtime_operation_id="expiring",
        runtime_step_id="step",
        character_count=1,
        payload={"text": "expires"},
    )
    clock.advance(minutes=16)
    expired = store.get_session(expiring.id, owner_id="owner")
    assert expired is not None and expired.status_at(clock()) == "expired"
    assert expired.record_count == 0
    latest = store.current_session(owner_id="owner", server_profile_id="profile")
    assert latest is not None
    assert latest.id == expiring.id
    assert latest.status_at(clock()) == "expired"

    byte_limited = InMemoryDiscordDebugCaptureStore(
        now=clock,
        maximum_records=100,
        maximum_bytes=30,
    )
    byte_session = byte_limited.start_session(
        owner_id="owner",
        server_profile_id="byte-profile",
        connection_id="byte-connection",
        guild_id="byte-guild",
        guild_name="Byte Guild",
        ttl_minutes=15,
    )
    for index in range(2):
        byte_limited.capture(
            connection_id="byte-connection",
            guild_id="byte-guild",
            source_message_id=f"byte-{index}",
            channel_id="channel",
            thread_id="",
            deployment_id="deployment",
            runtime_operation_id=f"byte-{index}",
            runtime_step_id="step",
            character_count=1,
            payload={"text": "1234567890"},
        )
    byte_current = byte_limited.get_session(byte_session.id, owner_id="owner")
    assert byte_current is not None
    assert byte_current.record_count == 1
    assert byte_current.evicted_record_count == 1
    assert byte_current.captured_bytes <= 30

    globally_bounded = InMemoryDiscordDebugCaptureStore(
        now=clock,
        maximum_records=100,
        maximum_bytes=100_000,
        global_maximum_records=2,
        global_maximum_bytes=100_000,
    )
    first_global = globally_bounded.start_session(
        owner_id="owner",
        server_profile_id="global-profile-1",
        connection_id="global-connection-1",
        guild_id="global-guild-1",
        guild_name="Global Guild 1",
        ttl_minutes=15,
    )
    second_global = globally_bounded.start_session(
        owner_id="owner",
        server_profile_id="global-profile-2",
        connection_id="global-connection-2",
        guild_id="global-guild-2",
        guild_name="Global Guild 2",
        ttl_minutes=15,
    )
    for index, (connection_id, guild_id) in enumerate(
        (
            ("global-connection-1", "global-guild-1"),
            ("global-connection-2", "global-guild-2"),
            ("global-connection-2", "global-guild-2"),
        )
    ):
        globally_bounded.capture(
            connection_id=connection_id,
            guild_id=guild_id,
            source_message_id=f"global-{index}",
            channel_id="channel",
            thread_id="",
            deployment_id="deployment",
            runtime_operation_id=f"global-{index}",
            runtime_step_id="step",
            character_count=1,
            payload={"text": f"global-{index}"},
        )
    first_after_global_eviction = globally_bounded.get_session(
        first_global.id,
        owner_id="owner",
    )
    second_after_global_eviction = globally_bounded.get_session(
        second_global.id,
        owner_id="owner",
    )
    assert first_after_global_eviction is not None
    assert first_after_global_eviction.record_count == 0
    assert first_after_global_eviction.evicted_record_count == 1
    assert second_after_global_eviction is not None
    assert second_after_global_eviction.record_count == 2


def test_in_memory_store_bounds_expired_session_summaries() -> None:
    clock = Clock()
    store = InMemoryDiscordDebugCaptureStore(now=clock, maximum_sessions=2)
    first = store.start_session(
        owner_id="owner",
        server_profile_id="profile-1",
        connection_id="connection-1",
        guild_id="guild-1",
        guild_name="Guild 1",
        ttl_minutes=15,
    )
    second = store.start_session(
        owner_id="owner",
        server_profile_id="profile-2",
        connection_id="connection-2",
        guild_id="guild-2",
        guild_name="Guild 2",
        ttl_minutes=15,
    )
    with pytest.raises(DiscordDebugCaptureConflict):
        store.start_session(
            owner_id="owner",
            server_profile_id="profile-3",
            connection_id="connection-3",
            guild_id="guild-3",
            guild_name="Guild 3",
            ttl_minutes=15,
        )

    clock.advance(minutes=16)
    third = store.start_session(
        owner_id="owner",
        server_profile_id="profile-3",
        connection_id="connection-3",
        guild_id="guild-3",
        guild_name="Guild 3",
        ttl_minutes=15,
    )

    assert third.id
    assert store.get_session(first.id, owner_id="owner") is None
    assert store.get_session(second.id, owner_id="owner") is not None


def test_capture_api_authorization_scope_dedupe_no_store_and_payload_free_audit(
    tmp_path: Path,
) -> None:
    app = create_app(app_settings(tmp_path / "discord-debug.db"))
    super_admin = TestClient(app)
    regular_user = TestClient(app)
    regular_admin = TestClient(app)
    login(super_admin, ADMIN_EMAIL)
    user_id = register(regular_user, "debug-user@example.com")
    admin_id = register(regular_admin, "debug-admin@example.com")

    assert regular_user.get("/api/admin/discord-debug-captures/access").status_code == 403
    promoted = super_admin.put(
        f"/api/admin/users/{admin_id}/role",
        json={"role": "admin"},
    )
    assert promoted.status_code == 200, promoted.text
    assert regular_admin.get("/api/admin/discord-debug-captures/access").status_code == 403
    access = super_admin.get("/api/admin/discord-debug-captures/access")
    assert access.status_code == 200
    assert access.json()["global_maximum_records"] == 500
    assert access.json()["global_maximum_bytes"] == 50 * 1024 * 1024
    assert access.json()["maximum_session_summaries"] == 500
    assert user_id

    connection_id, profile_id, deployment_id = create_runtime_scope(app, super_admin)
    disabled = super_admin.post(
        "/api/connectors/discord/messages",
        headers=connector_headers(),
        json=inbound_message(connection_id, deployment_id, message_id="disabled"),
    )
    assert disabled.status_code == 200, disabled.text
    assert super_admin.get(
        "/api/admin/discord-debug-captures/sessions/current",
        params={"server_profile_id": profile_id},
    ).json() is None

    started = super_admin.post(
        "/api/admin/discord-debug-captures/sessions",
        json={"server_profile_id": profile_id, "ttl_minutes": 60},
    )
    assert started.status_code == 201, started.text
    session_id = str(started.json()["id"])
    conflict = super_admin.post(
        "/api/admin/discord-debug-captures/sessions",
        json={"server_profile_id": profile_id, "ttl_minutes": 15},
    )
    assert conflict.status_code == 409

    for _ in range(2):
        captured = super_admin.post(
            "/api/connectors/discord/messages",
            headers=connector_headers(),
            json=inbound_message(connection_id, deployment_id),
        )
        assert captured.status_code == 200, captured.text
    spoofed = super_admin.post(
        "/api/connectors/discord/messages",
        headers=connector_headers(),
        json=inbound_message(
            connection_id,
            deployment_id,
            message_id="spoofed",
            guild_id="different-guild",
        ),
    )
    assert spoofed.status_code == 200, spoofed.text

    page = super_admin.get(
        f"/api/admin/discord-debug-captures/sessions/{session_id}/records/page"
    )
    assert page.status_code == 200, page.text
    assert page.json()["total"] == 1
    summary = page.json()["items"][0]
    assert summary["outcome"] == "succeeded"
    assert summary["character_count"] == len(RAW_TEXT)
    record_id = str(summary["id"])
    assert RAW_TEXT not in page.text

    detail = super_admin.get(f"/api/admin/discord-debug-captures/records/{record_id}")
    assert detail.status_code == 200, detail.text
    assert detail.headers["cache-control"] == "no-store"
    assert detail.json()["payload"]["text"] == RAW_TEXT

    cleared = super_admin.delete(
        f"/api/admin/discord-debug-captures/sessions/{session_id}/records"
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["deleted_count"] == 1
    stopped = super_admin.post(
        f"/api/admin/discord-debug-captures/sessions/{session_id}/stop"
    )
    assert stopped.status_code == 200, stopped.text
    assert stopped.json()["status"] == "stopped"
    current_after_stop = super_admin.get(
        "/api/admin/discord-debug-captures/sessions/current",
        params={"server_profile_id": profile_id},
    )
    assert current_after_stop.status_code == 200, current_after_stop.text
    assert current_after_stop.json()["id"] == session_id
    assert current_after_stop.json()["status"] == "stopped"
    audit = super_admin.get("/api/admin/audit")
    assert audit.status_code == 200, audit.text
    assert RAW_TEXT not in audit.text
    debug_actions = {
        item["action"] for item in audit.json() if item["action"].startswith("discord_debug")
    }
    assert debug_actions == {
        "discord_debug_capture.started",
        "discord_debug_capture.record_viewed",
        "discord_debug_capture.records_cleared",
        "discord_debug_capture.stopped",
    }
    database_path = tmp_path / "discord-debug.db"
    for candidate in (database_path, Path(f"{database_path}-wal")):
        if candidate.exists():
            assert RAW_TEXT.encode("utf-8") not in candidate.read_bytes()


def test_start_is_rolled_back_when_required_audit_fails(tmp_path: Path) -> None:
    app = create_app(app_settings(tmp_path / "discord-debug-audit-failure.db"))
    client = TestClient(app, raise_server_exceptions=False)
    login(client, ADMIN_EMAIL)
    _, profile_id, _ = create_runtime_scope(app, client)
    repository = app.state.auth_repository
    original_audit = repository.audit

    def fail_audit(**kwargs: object) -> None:
        del kwargs
        raise RuntimeError("audit unavailable")

    repository.audit = fail_audit
    response = client.post(
        "/api/admin/discord-debug-captures/sessions",
        json={"server_profile_id": profile_id, "ttl_minutes": 15},
    )
    repository.audit = original_audit

    assert response.status_code == 500
    current = client.get(
        "/api/admin/discord-debug-captures/sessions/current",
        params={"server_profile_id": profile_id},
    )
    assert current.status_code == 200
    assert current.json() is None


def test_capture_store_failure_does_not_change_message_response(tmp_path: Path) -> None:
    app = create_app(app_settings(tmp_path / "discord-debug-failure.db"))
    client = TestClient(app)
    login(client, ADMIN_EMAIL)
    connection_id, profile_id, deployment_id = create_runtime_scope(app, client)
    started = client.post(
        "/api/admin/discord-debug-captures/sessions",
        json={"server_profile_id": profile_id, "ttl_minutes": 15},
    )
    assert started.status_code == 201, started.text
    working_store = app.state.discord_debug_capture_store

    class FailingCaptureStore:
        codec = working_store.codec

        def capture(self, **kwargs: object) -> None:
            del kwargs
            raise RuntimeError("capture unavailable")

    app.state.discord_debug_capture_store = FailingCaptureStore()
    response = client.post(
        "/api/connectors/discord/messages",
        headers=connector_headers(),
        json=inbound_message(connection_id, deployment_id),
    )
    assert response.status_code == 200, response.text
    assert response.json()["reason"] == "test_success"

    class FailingMarkStore:
        codec = working_store.codec

        def capture(self, **kwargs: object) -> object:
            return working_store.capture(**kwargs)

        def mark_outcome(self, *args: object, **kwargs: object) -> None:
            del args, kwargs
            raise RuntimeError("capture mark unavailable")

    app.state.discord_debug_capture_store = FailingMarkStore()
    mark_response = client.post(
        "/api/connectors/discord/messages",
        headers=connector_headers(),
        json=inbound_message(connection_id, deployment_id, message_id="mark-failure"),
    )
    assert mark_response.status_code == 200, mark_response.text
    assert mark_response.json()["reason"] == "test_success"


def test_message_runtime_failures_mark_capture_outcome(tmp_path: Path) -> None:
    app = create_app(app_settings(tmp_path / "discord-debug-outcomes.db"))
    client = TestClient(app)
    login(client, ADMIN_EMAIL)
    connection_id, profile_id, deployment_id = create_runtime_scope(app, client)
    started = client.post(
        "/api/admin/discord-debug-captures/sessions",
        json={"server_profile_id": profile_id, "ttl_minutes": 15},
    )
    assert started.status_code == 201, started.text
    session_id = str(started.json()["id"])

    app.state.discord_connector_runtime.respond = AsyncMock(
        side_effect=ConnectorRuntimeError("runtime conflict")
    )
    conflict = client.post(
        "/api/connectors/discord/messages",
        headers=connector_headers(),
        json=inbound_message(connection_id, deployment_id, message_id="conflict"),
    )
    assert conflict.status_code == 409, conflict.text

    app.state.discord_connector_runtime.respond = AsyncMock(
        side_effect=RuntimeError("provider unavailable")
    )
    provider_error = client.post(
        "/api/connectors/discord/messages",
        headers=connector_headers(),
        json=inbound_message(connection_id, deployment_id, message_id="provider-error"),
    )
    assert provider_error.status_code == 502, provider_error.text

    page = client.get(
        f"/api/admin/discord-debug-captures/sessions/{session_id}/records/page"
    )
    assert page.status_code == 200, page.text
    outcomes = {item["source_message_id"]: item["outcome"] for item in page.json()["items"]}
    assert outcomes == {"conflict": "conflict", "provider-error": "provider_error"}


def test_non_durable_social_turn_runtime_ingress_is_captured_once(tmp_path: Path) -> None:
    app = create_app(app_settings(tmp_path / "discord-debug-social.db"))
    client = TestClient(app)
    login(client, ADMIN_EMAIL)
    connection_id, profile_id, deployment_id = create_runtime_scope(app, client)
    started = client.post(
        "/api/admin/discord-debug-captures/sessions",
        json={"server_profile_id": profile_id, "ttl_minutes": 15},
    )
    assert started.status_code == 201, started.text
    session_id = str(started.json()["id"])
    app.state.social_turn_graph_runner = AsyncMock(
        return_value=DiscordSocialTurnStepView(
            reply=DiscordConnectorReplyView(
                action="silent",
                reason="social_test_success",
                deployment_id=deployment_id,
            ),
            cursor=DiscordSocialTurnCursor(),
            current_deployment_id=deployment_id,
            done=True,
        )
    )
    request = {
        "payload": inbound_message(connection_id, deployment_id, message_id="social-message"),
        "initial_deployment_ids": [deployment_id],
        "available_deployment_ids": [deployment_id],
        "continuation_budget": 1,
        "max_depth": 1,
    }
    for _ in range(2):
        response = client.post(
            "/api/connectors/discord/social-turns/step",
            headers=connector_headers(),
            json=request,
        )
        assert response.status_code == 200, response.text

    page = client.get(
        f"/api/admin/discord-debug-captures/sessions/{session_id}/records/page"
    )
    assert page.status_code == 200, page.text
    assert page.json()["total"] == 1
    assert page.json()["items"][0]["source_message_id"] == "social-message"
    assert page.json()["items"][0]["outcome"] == "succeeded"


def test_new_app_process_has_no_previous_capture_session(tmp_path: Path) -> None:
    database_path = tmp_path / "discord-debug-restart.db"
    first_app = create_app(app_settings(database_path))
    first = TestClient(first_app)
    login(first, ADMIN_EMAIL)
    _, profile_id, _ = create_runtime_scope(first_app, first)
    started = first.post(
        "/api/admin/discord-debug-captures/sessions",
        json={"server_profile_id": profile_id, "ttl_minutes": 1440},
    )
    assert started.status_code == 201, started.text

    restarted = TestClient(create_app(app_settings(database_path)))
    login(restarted, ADMIN_EMAIL)
    current = restarted.get(
        "/api/admin/discord-debug-captures/sessions/current",
        params={"server_profile_id": profile_id},
    )
    assert current.status_code == 200, current.text
    assert current.json() is None
