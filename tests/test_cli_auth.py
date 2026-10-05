"""Synthetic device-flow and read-only capability security acceptance tests."""

from __future__ import annotations

import asyncio
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
import test_web_rooms
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_web_rooms import member, observe, source

from echo_masque.api.routes.cli_auth import snapshot, stream
from echo_masque.cli_auth import CliAuthError, CliAuthService, digest, normalized_code
from echo_masque.persistence import Database
from echo_masque.persistence.cli_auth_models import CliDeviceRecord, CliGrantRecord
from echo_masque.persistence.models import AuditEventRecord, AuthSessionRecord, UserRecord
from echo_masque.persistence.room_models import RoomStateRecord
from echo_masque.persistence.web_room_repository import WebRoomRepository

web = test_web_rooms.web

CLIENT = "character-relay-cli"
SCOPES = ["identity:read", "rooms:read", "messages:read"]
GRANT_TYPE = "urn:ietf:params:oauth:grant-type:device_code"


@pytest.fixture
def cli(web):
    web[0].state.settings.cli_auth_enabled = True
    return web


def device(cli, *, scopes=None, room_ids=None):
    response = cli[1].post(
        "/api/cli-auth/device-authorizations",
        json={"client_id": CLIENT, "scopes": scopes or SCOPES, "room_ids": room_ids or [cli[4]]},
    )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    return response.json()


def csrf_headers(client):
    context = client.get("/api/cli-auth/browser-context")
    assert context.status_code == 200
    return {"Origin": "http://testserver", "X-CSRF-Token": context.json()["csrf_token"]}


def review(cli, challenge, *, client=None):
    client = client or cli[1]
    return client.post(
        "/api/cli-auth/authorizations/review",
        headers=csrf_headers(client),
        json={"user_code": challenge["user_code"]},
    )


def decide(cli, challenge, *, decision="approve", client=None):
    client = client or cli[1]
    return client.post(
        "/api/cli-auth/authorizations/decision",
        headers=csrf_headers(client),
        json={"user_code": challenge["user_code"], "decision": decision},
    )


def poll(cli, challenge, **overrides):
    data = {
        "client_id": CLIENT,
        "device_code": challenge["device_code"],
        "grant_type": GRANT_TYPE,
        **overrides,
    }
    return cli[1].post("/api/cli-auth/token", data=data)


def reset_poll(cli, challenge):
    with cli[0].state.database.session() as session:
        record = session.scalar(
            select(CliDeviceRecord).where(
                CliDeviceRecord.device_code_hash == digest(challenge["device_code"])
            )
        )
        record.next_poll_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()


def authorize(cli, *, client=None, scopes=None):
    challenge = device(cli, scopes=scopes)
    assert review(cli, challenge, client=client).status_code == 200
    approved = decide(cli, challenge, client=client)
    assert approved.status_code == 200
    issued = poll(cli, challenge)
    assert issued.status_code == 200
    return challenge, issued.json()["access_token"], approved.json()["grant"]


def bearer(token):
    return {"Authorization": "Bearer " + token}


def test_disabled_by_default_and_no_grants_without_real_cookie(web):
    app, client, *_ = web
    assert (
        client.post(
            "/api/cli-auth/device-authorizations",
            json={
                "client_id": CLIENT,
                "scopes": SCOPES,
                "room_ids": [web[4]],
            },
        ).status_code
        == 404
    )
    app.state.settings.cli_auth_enabled = True
    app.state.settings.legacy_local_user_enabled = True
    anonymous = TestClient(app)
    assert anonymous.get("/api/cli-auth/browser-context").status_code == 401
    assert anonymous.get("/api/cli-auth/grants").status_code == 401
    with app.state.database.session() as session:
        assert session.scalar(select(CliGrantRecord)) is None


@pytest.mark.parametrize(
    "changes",
    [
        {"client_id": "unregistered"},
        {"scopes": ["messages:send"]},
        {"scopes": ["offline_access"]},
        {"scopes": ["identity:read", "admin"]},
        {"scopes": []},
        {"room_ids": []},
        {"room_ids": ["*"]},
        {"room_ids": ["all"] * 33},
        {"room_ids": ["room/elsewhere"]},
        {"room_ids": ["a" * 65]},
        {"user_id": "spoofed"},
    ],
)
def test_unregistered_scope_widening_and_nonexplicit_rooms_rejected(cli, changes):
    body = {"client_id": CLIENT, "scopes": SCOPES, "room_ids": [cli[4]], **changes}
    response = cli[1].post("/api/cli-auth/device-authorizations", json=body)
    assert response.status_code in {400, 422}
    with cli[0].state.database.session() as session:
        assert session.scalar(select(CliDeviceRecord)) is None
        assert session.scalar(select(CliGrantRecord)) is None


def test_pending_and_poll_penalty_are_durable_across_service_restart(cli):
    challenge = device(cli)
    assert poll(cli, challenge).json() == {"error": "authorization_pending"}
    assert poll(cli, challenge).json() == {"error": "slow_down"}
    with cli[0].state.database.session() as session:
        record = session.scalar(select(CliDeviceRecord))
        assert record.interval == 10
        assert record.poll_version == 2
        assert record.status == "pending"
    database = Database(cli[0].state.settings.database_url)
    restarted = CliAuthService(database, cli[0].state.settings, WebRoomRepository(database))
    try:
        with pytest.raises(CliAuthError, match=r"^slow_down$"):
            restarted.exchange(CLIENT, challenge["device_code"])
        with database.session() as session:
            assert session.scalar(select(CliDeviceRecord)).interval == 15
    finally:
        database.engine.dispose()


@pytest.mark.parametrize("failure", ["denied", "expired", "wrong_device", "wrong_client"])
def test_token_failure_states_never_issue_a_credential(cli, failure):
    challenge = device(cli)
    expected = "invalid_grant"
    overrides = {}
    if failure == "denied":
        assert review(cli, challenge).status_code == 200
        assert decide(cli, challenge, decision="deny").json()["status"] == "denied"
        expected = "access_denied"
    elif failure == "expired":
        with cli[0].state.database.session() as session:
            session.scalar(select(CliDeviceRecord)).expires_at = datetime.now(UTC) - timedelta(
                seconds=1
            )
            session.commit()
        expected = "expired_token"
    elif failure == "wrong_device":
        overrides["device_code"] = "synthetic-unknown-device"
    else:
        overrides["client_id"] = "unregistered"
        expected = "invalid_client"
    response = poll(cli, challenge, **overrides)
    assert response.status_code == 400
    assert response.json() == {"error": expected}
    assert response.headers["cache-control"] == "no-store"
    with cli[0].state.database.session() as session:
        assert session.scalar(select(CliGrantRecord)) is None


@pytest.mark.parametrize(
    "payload,content_type",
    [
        ("", "application/x-www-form-urlencoded"),
        (
            "grant_type=a&client_id=b&device_code=c&device_code=d",
            "application/x-www-form-urlencoded",
        ),
        ("grant_type=a&client_id=b&device_code=c&extra=x", "application/x-www-form-urlencoded"),
        ("grant_type=a&client_id=b&device_code=c", "application/json"),
        ("x=" + "a" * 2050, "application/x-www-form-urlencoded"),
    ],
)
def test_token_parser_rejects_ambiguous_or_unbounded_payload(cli, payload, content_type):
    response = cli[1].post(
        "/api/cli-auth/token", content=payload, headers={"Content-Type": content_type}
    )
    assert response.status_code == 400
    assert response.json() == {"error": "invalid_request"}


@pytest.mark.parametrize("operation", ["review", "decision"])
@pytest.mark.parametrize("attack", ["missing", "foreign_origin", "wrong_token"])
def test_browser_approval_requires_csrf_and_same_origin(cli, operation, attack):
    challenge = device(cli)
    headers = csrf_headers(cli[1])
    if attack == "missing":
        headers = {}
    elif attack == "foreign_origin":
        headers["Origin"] = "https://attacker.example"
    else:
        headers["X-CSRF-Token"] = "incorrect"
    body = {"user_code": challenge["user_code"]}
    if operation == "decision":
        body["decision"] = "approve"
    response = cli[1].post(f"/api/cli-auth/authorizations/{operation}", json=body, headers=headers)
    assert response.status_code == 403
    assert response.json() == {"error": "csrf_rejected"}
    with cli[0].state.database.session() as session:
        record = session.scalar(select(CliDeviceRecord))
        assert record.status == "pending"
        assert record.reviewing_user_id is None
        assert session.scalar(select(CliGrantRecord)) is None


def test_review_binds_account_and_displays_server_controlled_metadata(cli):
    _, visitor = member(cli, can_post=False)
    challenge = device(cli, scopes=["messages:read"])
    response = review(cli, challenge)
    assert response.status_code == 200
    body = response.json()
    assert body["client_name"] == "Character Relay CLI"
    assert body["rooms"] == [{"id": cli[4], "name": "General"}]
    assert body["scopes"] == ["messages:read"]
    assert body["access_token_ttl_seconds"] == 900
    assert body["account"]["user_id"] == cli[1].get("/api/auth/me").json()["id"]
    assert review(cli, challenge, client=visitor).status_code == 403
    assert decide(cli, challenge, client=visitor).status_code == 403
    assert decide(cli, challenge).status_code == 200
    assert decide(cli, challenge).status_code == 409


def test_wrong_expired_or_unreviewed_code_cannot_approve(cli):
    challenge = device(cli)
    assert decide(cli, challenge).status_code == 403
    assert review(cli, {"user_code": "AAAAA-AAAAA"}).status_code == 400
    with cli[0].state.database.session() as session:
        session.scalar(select(CliDeviceRecord)).expires_at = datetime.now(UTC) - timedelta(
            seconds=1
        )
        session.commit()
    assert review(cli, challenge).status_code == 400
    assert decide(cli, challenge).status_code == 400


def test_single_redemption_and_restart_preserve_limited_grant(cli):
    challenge, token, grant = authorize(cli)
    assert poll(cli, challenge).json() == {"error": "invalid_grant"}
    database = Database(cli[0].state.settings.database_url)
    restarted = CliAuthService(database, cli[0].state.settings, WebRoomRepository(database))
    try:
        actor = restarted.resolve(token)
        assert actor.grant_id == grant["grant_id"]
        assert actor.room_ids == (cli[4],)
        assert actor.scopes == frozenset(SCOPES)
        assert not hasattr(actor, "role")
        with pytest.raises(CliAuthError, match=r"^invalid_grant$"):
            restarted.exchange(CLIENT, challenge["device_code"])
    finally:
        database.engine.dispose()


def test_concurrent_database_exchange_has_exactly_one_winner(cli):
    challenge = device(cli)
    assert review(cli, challenge).status_code == 200
    assert decide(cli, challenge).status_code == 200
    database = Database(cli[0].state.settings.database_url)
    second = CliAuthService(database, cli[0].state.settings, WebRoomRepository(database))

    def exchange(service):
        try:
            result = service.exchange(CLIENT, challenge["device_code"])
            return "issued" if result["token_type"] == "Bearer" else "unexpected"
        except CliAuthError as exc:
            return exc.code

    try:
        with ThreadPoolExecutor(max_workers=2) as workers:
            outcomes = list(workers.map(exchange, [cli[0].state.cli_auth_service, second]))
        assert outcomes.count("issued") == 1
        assert all(outcome in {"issued", "invalid_grant", "slow_down"} for outcome in outcomes)
        with database.session() as session:
            assert session.scalar(select(CliDeviceRecord)).status == "redeemed"
            assert len(session.scalars(select(CliGrantRecord)).all()) == 1
    finally:
        database.engine.dispose()


def test_minimal_identity_explicit_rooms_and_bounded_messages(cli):
    observe(cli, [source(str(index), text=f"Synthetic {index}") for index in range(64)])
    observe(cli, [source(str(index), text=f"Synthetic {index}") for index in range(64, 70)])
    _, token, grant = authorize(cli)
    client = cli[1]
    identity = client.get("/api/cli-auth/me", headers=bearer(token))
    assert identity.status_code == 200
    assert set(identity.json()) == {
        "user_id",
        "display_name",
        "grant_id",
        "client_id",
        "client_name",
        "scopes",
        "room_ids",
        "approved_at",
        "expires_at",
        "revoked_at",
    }
    assert identity.json()["grant_id"] == grant["grant_id"]
    assert client.get("/api/cli/rooms", headers=bearer(token)).json() == {
        "rooms": [{"id": cli[4], "name": "General"}]
    }
    response = client.get(f"/api/cli/rooms/{cli[4]}/messages", headers=bearer(token))
    assert response.status_code == 200
    assert len(response.json()["messages"]) == 64
    assert response.json()["history_limit"] == 64
    assert "outbox" not in response.json()
    assert response.headers["cache-control"] == "no-store"
    assert (
        client.get("/api/cli/rooms/other-room/messages", headers=bearer(token)).status_code == 403
    )


@pytest.mark.parametrize(
    "scope,path",
    [
        ("identity:read", "/api/cli/rooms"),
        ("rooms:read", "/api/cli-auth/me"),
        ("identity:read", "/api/cli/rooms/{room}/messages"),
        ("rooms:read", "/api/cli/rooms/{room}/events"),
    ],
)
def test_independent_scopes_cannot_silently_expand(cli, scope, path):
    _, token, _ = authorize(cli, scopes=[scope])
    assert cli[1].get(path.format(room=cli[4]), headers=bearer(token)).status_code == 403


def test_admin_owned_cli_rejected_by_every_unrelated_api_operation(cli):
    _, token, _ = authorize(cli)
    cli[0].state.settings.legacy_local_user_enabled = True
    assert cli[1].get("/api/auth/me").json()["role"] == "admin"
    exempt = {
        "/api/cli-auth/me",
        "/api/cli-auth/revoke",
        "/api/cli/rooms",
        "/api/cli/rooms/{room_id}/messages",
        "/api/cli/rooms/{room_id}/events",
    }
    checked = 0
    for path, operations in cli[0].openapi()["paths"].items():
        if not path.startswith("/api/") or path in exempt:
            continue
        import re

        concrete = re.sub(r"\{[^}]+\}", "synthetic-id", path)
        for method in operations:
            if method.upper() not in {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"}:
                continue
            response = cli[1].request(method, concrete, headers=bearer(token))
            assert response.status_code == 403, (method, path, response.status_code)
            checked += 1
    assert checked > 100
    # Explicitly block writes on the read API, including unknown subroutes.
    for method in ["POST", "PUT", "PATCH", "DELETE"]:
        assert (
            cli[1]
            .request(method, f"/api/cli/rooms/{cli[4]}/messages", headers=bearer(token))
            .status_code
            == 403
        )


@pytest.mark.parametrize("credential", ["crcli_malformed", "CRCLI_malformed"])
@pytest.mark.parametrize("transport", ["bearer", "cookie"])
def test_cli_shaped_invalid_credentials_never_fall_back_to_legacy_admin(cli, credential, transport):
    cli[0].state.settings.legacy_local_user_enabled = True
    anonymous = TestClient(cli[0])
    headers = bearer(credential) if transport == "bearer" else {}
    if transport == "cookie":
        anonymous.cookies.set(cli[0].state.settings.auth_cookie_name, credential)
    for path in ["/api/auth/me", "/api/auth/sessions", "/api/connections", "/api/web-chat/rooms"]:
        assert anonymous.get(path, headers=headers).status_code == 403


@pytest.mark.parametrize(
    "failure", ["revoked", "expired", "inactive", "membership", "server", "stale"]
)
def test_each_read_rechecks_current_grant_account_and_room_permissions(cli, failure):
    user, visitor = member(cli, can_post=False)
    _, token, grant = authorize(cli, client=visitor)
    assert cli[1].get(f"/api/cli/rooms/{cli[4]}/messages", headers=bearer(token)).status_code == 200
    invalidate(cli, failure, user.id, grant["grant_id"])
    for path in ["/api/cli-auth/me", "/api/cli/rooms", f"/api/cli/rooms/{cli[4]}/messages"]:
        assert cli[1].get(path, headers=bearer(token)).status_code in {401, 404, 503}
    assert cli[1].get("/api/connections", headers=bearer(token)).status_code == 403


def invalidate(cli, failure, user_id, grant_id):
    app, client, connection, _, room, _ = cli
    if failure == "membership":
        assert client.delete(f"/api/web-chat/rooms/{room}/members/{user_id}").status_code == 204
    elif failure == "server":
        from echo_masque.persistence.server_access_repository import ServerAccessRepository

        ServerAccessRepository(app.state.database).revoke_access(
            user_id=user_id, connection_id=connection["id"], guild_id="guild-phase3"
        )
    else:
        with app.state.database.session() as session:
            if failure == "revoked":
                session.get(CliGrantRecord, grant_id).revoked_at = datetime.now(UTC)
            elif failure == "expired":
                session.get(CliGrantRecord, grant_id).expires_at = datetime.now(UTC) - timedelta(
                    seconds=1
                )
            elif failure == "inactive":
                session.get(UserRecord, user_id).is_active = False
            elif failure == "stale":
                for record in session.scalars(select(RoomStateRecord)):
                    record.permission_checked_at = datetime.now(UTC) - timedelta(seconds=120)
            session.commit()


def test_owner_only_browser_and_cli_revocation_and_csrf(cli):
    user, visitor = member(cli)
    _, token, grant = authorize(cli, client=visitor)
    path = "/api/cli-auth/grants/" + grant["grant_id"]
    assert cli[1].delete(path, headers=csrf_headers(cli[1])).status_code == 404
    assert visitor.delete(path).status_code == 403
    assert cli[1].get("/api/cli-auth/grants").json() == {"grants": []}
    assert visitor.get("/api/cli-auth/grants").json()["grants"][0]["grant_id"] == grant["grant_id"]
    assert cli[1].post("/api/cli-auth/revoke", headers=bearer(token)).status_code == 204
    assert visitor.get("/api/cli-auth/grants").json()["grants"][0]["revoked_at"] is not None
    assert cli[1].get("/api/cli-auth/me", headers=bearer(token)).status_code == 401
    assert cli[1].post("/api/cli-auth/revoke", headers=bearer(token)).status_code == 401
    assert visitor.delete(path, headers=csrf_headers(visitor)).status_code == 204
    with cli[0].state.database.session() as session:
        assert session.get(CliGrantRecord, grant["grant_id"]).user_id == user.id


def test_browser_cookie_cannot_be_replaced_by_bearer_and_cli_cookie_cannot_read(cli):
    _, token, _ = authorize(cli)
    for path in ["/api/cli-auth/browser-context", "/api/cli-auth/grants"]:
        assert cli[1].get(path, headers=bearer(token)).status_code == 403
    anonymous = TestClient(cli[0])
    anonymous.cookies.set(cli[0].state.settings.auth_cookie_name, token)
    assert anonymous.get("/api/cli-auth/me").status_code == 401
    assert cli[1].get("/api/cli-auth/me").status_code == 401


def test_credentials_are_hashed_not_sessions_or_audit_or_exception_output(cli, caplog, capsys):
    challenge, token, grant = authorize(cli)
    with cli[0].state.database.session() as session:
        record = session.scalar(select(CliDeviceRecord))
        stored = session.get(CliGrantRecord, grant["grant_id"])
        assert record.device_code_hash == digest(challenge["device_code"])
        assert record.user_code_hash == digest(normalized_code(challenge["user_code"]))
        assert stored.token_hash == digest(token)
        sessions = session.scalars(select(AuthSessionRecord)).all()
        assert len(sessions) == 1
        assert all(row.token_hash != stored.token_hash for row in sessions)
        audits = session.scalars(
            select(AuditEventRecord).where(AuditEventRecord.action.like("cli_grant.%"))
        ).all()
        assert {row.action for row in audits} == {"cli_grant.approved", "cli_grant.redeemed"}
        serialized = json.dumps(
            [
                {"action": row.action, "metadata": row.metadata_json, "resource": row.resource_id}
                for row in audits
            ]
        )
    response = poll(cli, challenge)
    listing = cli[1].get("/api/cli-auth/grants")
    public = serialized + response.text + listing.text + caplog.text + capsys.readouterr().out
    assert all(
        secret not in public for secret in [token, challenge["device_code"], challenge["user_code"]]
    ), "private credential exposure"
    with pytest.raises(CliAuthError) as error:
        cli[0].state.cli_auth_service.exchange(CLIENT, challenge["device_code"])
    assert str(error.value) == "invalid_grant"


@pytest.mark.parametrize(
    "failure", ["revoked", "expired", "inactive", "membership", "server", "stale"]
)
def test_established_stream_stops_before_new_snapshot_after_invalidation(cli, failure, monkeypatch):
    user, visitor = member(cli)
    _, token, grant = authorize(cli, client=visitor)

    async def connected():
        return False

    async def invalidate_on_interval(seconds):
        assert seconds == 1
        invalidate(cli, failure, user.id, grant["grant_id"])

    monkeypatch.setattr("echo_masque.api.routes.cli_auth.asyncio.sleep", invalidate_on_interval)

    async def consume():
        generator = stream(
            cli[0].state.cli_auth_service, token, cli[4], SimpleNamespace(is_disconnected=connected)
        )
        first = await anext(generator)
        assert "event: snapshot" in first
        second = await anext(generator)
        assert second == 'event: revoked\ndata: {"reason":"authorization_unavailable"}\n\n'
        with pytest.raises(StopAsyncIteration):
            await anext(generator)

    asyncio.run(consume())


def test_snapshot_revalidates_after_room_io_before_emission(cli, monkeypatch):
    _, token, grant = authorize(cli)
    from echo_masque.api.routes import web_chat

    original = web_chat._snapshot

    def revoked_during_snapshot(*args, **kwargs):
        data = original(*args, **kwargs)
        cli[0].state.cli_auth_service.revoke(
            grant["grant_id"], cli[1].get("/api/auth/me").json()["id"]
        )
        return data

    monkeypatch.setattr(web_chat, "_snapshot", revoked_during_snapshot)
    with pytest.raises(CliAuthError, match=r"^invalid_token$"):
        snapshot(cli[0].state.cli_auth_service, token, cli[4])


@pytest.mark.parametrize(
    "authorization",
    [
        "crcli_malformed",
        "Bearer\tcrcli_malformed",
        "bearer CRCLI_malformed",
        "Basic crcli_malformed",
        "Bearer  crcli_malformed",
    ],
)
def test_malformed_authorization_syntax_cannot_reach_legacy_admin(cli, authorization):
    cli[0].state.settings.legacy_local_user_enabled = True
    for path in ["/api/auth/me", "/api/connections", "/api/auth/sessions"]:
        response = cli[1].get(path, headers={"Authorization": authorization})
        assert response.status_code == 403


def test_validation_responses_do_not_echo_accidentally_supplied_private_credentials(cli):
    challenge, token, _ = authorize(cli)
    for payload in [
        {"client_id": CLIENT, "scopes": [token], "room_ids": [cli[4]]},
        {"client_id": CLIENT, "scopes": SCOPES, "room_ids": [cli[4]], "token": token},
        {"client_id": CLIENT, "scopes": SCOPES, "room_ids": [challenge["device_code"] + "/"]},
    ]:
        response = cli[1].post("/api/cli-auth/device-authorizations", json=payload)
        assert response.status_code in {400, 422}
        assert response.headers["cache-control"] == "no-store"
        assert not any(secret in response.text for secret in [token, challenge["device_code"]])
    response = cli[1].post(
        "/api/cli-auth/authorizations/decision",
        headers=csrf_headers(cli[1]),
        json={"user_code": challenge["user_code"], "decision": token},
    )
    assert response.status_code == 422
    assert all(secret not in response.text for secret in [token]), "private credential exposure"


def test_csrf_is_bound_to_browser_session_not_transferable_account(cli):
    _, visitor = member(cli)
    challenge = device(cli)
    response = visitor.post(
        "/api/cli-auth/authorizations/review",
        json={"user_code": challenge["user_code"]},
        headers=csrf_headers(cli[1]),
    )
    assert response.status_code == 403
    with cli[0].state.database.session() as session:
        assert session.scalar(select(CliDeviceRecord)).reviewing_user_id is None


def test_room_access_must_exist_at_review_and_still_exist_at_approval(cli):
    user, visitor = member(cli, grant_room=False)
    challenge = device(cli)
    assert review(cli, challenge, client=visitor).status_code == 404
    assert (
        cli[1].put(f"/api/web-chat/rooms/{cli[4]}/members", json={"user_id": user.id}).status_code
        == 204
    )
    assert review(cli, challenge, client=visitor).status_code == 200
    assert cli[1].delete(f"/api/web-chat/rooms/{cli[4]}/members/{user.id}").status_code == 204
    assert decide(cli, challenge, client=visitor).status_code == 404
    with cli[0].state.database.session() as session:
        assert session.scalar(select(CliGrantRecord)) is None


@pytest.mark.parametrize("failure", ["revoked", "expired", "inactive", "membership"])
def test_approval_does_not_allow_exchange_after_grant_invalidated(cli, failure):
    user, visitor = member(cli)
    challenge = device(cli)
    assert review(cli, challenge, client=visitor).status_code == 200
    approved = decide(cli, challenge, client=visitor)
    assert approved.status_code == 200
    invalidate(cli, failure, user.id, approved.json()["grant"]["grant_id"])
    response = poll(cli, challenge)
    assert response.status_code in {400, 404}
    assert "access_token" not in response.json()
    with cli[0].state.database.session() as session:
        assert session.scalar(select(CliGrantRecord)).token_hash is None
        assert session.scalar(select(CliDeviceRecord)).status != "redeemed"


def test_brute_force_review_limit_survives_request_state_and_creates_no_grants(cli):
    headers = csrf_headers(cli[1])
    for _ in range(20):
        response = cli[1].post(
            "/api/cli-auth/authorizations/review",
            headers=headers,
            json={"user_code": "AAAAA-AAAAA"},
        )
        assert response.status_code == 400
    response = cli[1].post(
        "/api/cli-auth/authorizations/review", headers=headers, json={"user_code": "AAAAA-AAAAA"}
    )
    assert response.status_code == 429
    assert response.json() == {"error": "rate_limit_exceeded"}
    with cli[0].state.database.session() as session:
        assert session.scalar(select(CliGrantRecord)) is None


def test_stream_io_timeout_closes_without_emitting_late_private_snapshot(cli, monkeypatch):
    _, token, _ = authorize(cli)

    def stalled_snapshot(*args):
        time.sleep(0.1)
        return {"messages": [{"text": "synthetic-private-snapshot"}]}

    async def connected():
        return False

    monkeypatch.setattr("echo_masque.api.routes.cli_auth.snapshot", stalled_snapshot)
    monkeypatch.setattr("echo_masque.api.routes.cli_auth.CLI_STREAM_IO_TIMEOUT", 0.01)

    async def consume():
        generator = stream(
            cli[0].state.cli_auth_service, token, cli[4], SimpleNamespace(is_disconnected=connected)
        )
        event = await anext(generator)
        assert event == 'event: unavailable\ndata: {"reason":"snapshot_unavailable"}\n\n'
        with pytest.raises(StopAsyncIteration):
            await anext(generator)

    asyncio.run(consume())


def test_openapi_documents_restricted_bearer_and_bounded_credential_free_metadata(cli):
    document = cli[0].openapi()
    security = document["components"]["securitySchemes"]["CliReadOnlyGrant"]
    assert security["type"] == "http"
    assert security["scheme"] == "bearer"
    paths = document["paths"]
    for path in ["/api/cli-auth/me", "/api/cli/rooms", "/api/cli/rooms/{room_id}/messages"]:
        assert {"CliReadOnlyGrant": []} in paths[path]["get"]["security"]
        schema = paths[path]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
        assert "$ref" in schema
    schemas = document["components"]["schemas"]
    for model in ["CliIdentityView", "CliGrantView", "CliSnapshotView"]:
        assert not {"access_token", "device_code", "token_hash", "password", "email"} & set(
            schemas[model]["properties"]
        )
    assert schemas["CliSnapshotView"]["properties"]["messages"]["maxItems"] == 64
    assert schemas["CliSnapshotView"]["properties"]["history_limit"]["const"] == 64
    for schema, field in [
        ("DeviceAuthorizationView", "device_code"),
        ("CliTokenView", "access_token"),
    ]:
        credential = schemas[schema]["properties"][field]
        assert credential["x-sensitive"] is True
        assert credential["format"] == "password"
        assert "writeOnly" not in credential
    assert set(
        document["paths"]["/api/cli/rooms/{room_id}/events"]["get"]["responses"]["200"]["content"]
    ) == {"text/event-stream"}
    assert (
        "application/x-www-form-urlencoded"
        in paths["/api/cli-auth/token"]["post"]["requestBody"]["content"]
    )
