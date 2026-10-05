"""Real authenticated API/database counterexamples for fixed Agent reading batches."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from test_web_rooms import ack, claim, member, observe, send, source
from test_web_rooms import web as web

from echo_masque.persistence.agent_reading_models import AgentReadingCursorRecord
from echo_masque.persistence.agent_reading_repository import AgentReadingRepository
from echo_masque.persistence.models import AuthSessionRecord, UserRecord
from echo_masque.persistence.room_models import RoomStateRecord
from echo_masque.persistence.schema_migration_models import DatabaseSchemaMigrationRecord
from echo_masque.persistence.web_room_models import WebProfileRecord
from echo_masque.persistence.web_room_repository import WebRoomRepository
from echo_masque.public_demo import PUBLIC_DEMO_EMAIL
from echo_masque.room_sources import scope_key
from echo_masque.web_rooms import room_scope


def path(web, profile=None, room=None):
    return f"/api/web-chat/rooms/{room or web[4]}/agent-reading/{profile or web[5]['id']}"


def status(web):
    response = web[1].get(path(web))
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()


def batch(web):
    response = web[1].post(path(web) + "/batch", json={})
    assert response.status_code == 200, response.text
    return response.json()


def complete(web, batch_id):
    response = web[1].post(path(web) + "/complete", json={"batch_id": batch_id})
    assert response.status_code == 200, response.text
    return response.json()


def finish(web):
    return complete(web, batch(web)["batch"]["id"])


def test_initial_status_is_readonly_and_empty_reread_requires_explicit_confirmation(web):
    app, client, *_ = web
    initial = status(web)
    assert initial["needs_reread"] and initial["gap_generation"] == 1
    assert initial["pending_count"] == 0 and initial["batch"] is None
    with app.state.database.session() as session:
        assert session.scalar(select(func.count()).select_from(AgentReadingCursorRecord)) == 0
        assert session.get(DatabaseSchemaMigrationRecord, "web-room-agent-reading-v1") is not None
    active = batch(web)["batch"]
    assert active["items"] == [] and active["needs_reread"]
    assert batch(web)["batch"] == active
    done = complete(web, active["id"])
    assert not done["needs_reread"] and done["batch"] is None
    assert complete(web, active["id"]) == done
    assert client.post(path(web) + "/complete", json={"batch_id": "unknown"}).status_code == 409
    assert client.post(path(web) + "/complete", json={"batch_id": ""}).status_code == 422
    assert (
        client.post(
            path(web) + "/complete", json={"batch_id": active["id"], "to_revision": 999}
        ).status_code
        == 422
    )


def test_cap_does_not_skip_pending_old_edit_or_messages_arriving_during_processing(web):
    base = datetime.now(UTC)
    messages = [
        source(f"m-{index:03d}", created_at=(base + timedelta(seconds=index)).isoformat())
        for index in range(130)
    ]
    for start in range(0, 130, 64):
        observe(web, messages[start : start + 64])
    assert status(web)["pending_count"] == 130
    first = batch(web)["batch"]
    assert len(first["items"]) == 64 and first["to_revision"] == 64
    # The oldest message has already left the normal latest64 snapshot.
    assert "m-000" not in {
        item["id"]
        for item in web[1].get(f"/api/web-chat/rooms/{web[4]}/messages").json()["messages"]
    }
    observe(
        web,
        [
            {
                **messages[0],
                "text": "edited old",
                "edited_at": (base + timedelta(seconds=300)).isoformat(),
            },
            source("late"),
        ],
    )
    active = batch(web)["batch"]
    assert active["id"] == first["id"] and active["to_revision"] == 64
    assert active["items"][0]["state"] == "changed" and active["items"][0]["message"] is None
    remaining = complete(web, first["id"])
    assert remaining["cursor_revision"] == 64 and remaining["pending_count"] == 68
    second = batch(web)["batch"]
    assert len(second["items"]) == 64 and second["to_revision"] == 128
    complete(web, second["id"])
    third = batch(web)["batch"]
    assert {item["message_id"] for item in third["items"]} == {"m-128", "m-129", "m-000", "late"}
    assert (
        next(item for item in third["items"] if item["message_id"] == "m-000")["change"] == "edited"
    )
    assert not complete(web, third["id"])["pending_count"]


def test_edit_delete_and_parent_preview_never_replace_captured_content(web):
    base = datetime.now(UTC)
    parent = source("parent", text="first parent", created_at=base.isoformat())
    child = source(
        "child",
        text="first child",
        reply_to_message_id="parent",
        created_at=(base + timedelta(seconds=1)).isoformat(),
    )
    observe(web, [parent, child])
    active = batch(web)["batch"]
    assert active["items"][1]["message"]["reply_preview"]["summary"] == "first parent"
    observe(
        web,
        [
            {
                **parent,
                "text": "later parent",
                "edited_at": (base + timedelta(seconds=10)).isoformat(),
            }
        ],
    )
    changed = status(web)["batch"]
    assert changed["id"] == active["id"]
    assert changed["items"][0]["state"] == "changed"
    assert changed["items"][1]["message"]["reply_preview"]["available"] is False
    assert "later parent" not in str(changed)
    observe(web, [{**child, "deleted": True, "text": "", "content_available": False}])
    removed = status(web)["batch"]["items"][1]
    assert removed["state"] == "removed" and removed["message"] is None
    assert complete(web, active["id"])["pending_count"] == 2
    next_batch = batch(web)["batch"]
    deleted = next(item for item in next_batch["items"] if item["message_id"] == "child")
    assert deleted["change"] == "deleted" and deleted["message"] is None
    assert "first child" not in str(next_batch)


def test_gap_report_idempotence_and_later_gap_survives_completion(web):
    finish(web)
    first = web[1].post(path(web) + "/gap", json={"event_id": "gap-event-first-1234"}).json()
    duplicate = web[1].post(path(web) + "/gap", json={"event_id": "gap-event-first-1234"}).json()
    assert duplicate["gap_generation"] == first["gap_generation"]
    active = batch(web)["batch"]
    later = web[1].post(path(web) + "/gap", json={"event_id": "gap-event-later-1234"}).json()
    assert later["gap_generation"] == active["gap_generation"] + 1
    result = complete(web, active["id"])
    assert result["needs_reread"] and result["gap_generation"] == later["gap_generation"]
    assert not finish(web)["needs_reread"]


def test_gap_reread_adds_recorded_context_and_does_not_claim_external_coverage(web):
    observe(web, [source("one", text="retained context")])
    finish(web)
    web[1].post(path(web) + "/gap", json={"event_id": "disconnect-event-12345"})
    current = batch(web)
    assert current["pending_count"] == 0 and current["history_scope"] == "recorded_current_state"
    assert current["batch"]["needs_reread"]
    assert current["batch"]["items"][0]["message"]["text"] == "retained context"


def test_progress_persists_as_references_only_and_duplicate_ack_never_completes_next_batch(web):
    app, *_ = web
    observe(web, [source("one", text="never persist this body twice")])
    active = batch(web)["batch"]
    with app.state.database.session() as session:
        cursor = session.scalar(select(AgentReadingCursorRecord))
        assert "never persist" not in cursor.batch_references_json
        assert '"message_id": "one"' in cursor.batch_references_json
        session_id = session.scalar(select(AuthSessionRecord.id))
        user_id = cursor.user_id
    # Reconstruct the service over a fresh repository instance; no in-memory progress authority.
    restarted = AgentReadingRepository(WebRoomRepository(app.state.database))
    assert (
        restarted.status(web[4], user_id, web[5]["id"], session_id=session_id).batch.id
        == active["id"]
    )
    complete(web, active["id"])
    observe(web, [source("two")])
    second = batch(web)["batch"]
    duplicate = complete(web, active["id"])
    assert duplicate["batch"]["id"] == second["id"] and duplicate["pending_count"] == 1
    assert complete(web, second["id"])["pending_count"] == 0


def test_own_receipt_echo_excluded_but_matching_display_name_is_pending(web):
    finish(web)
    assert send(web).status_code == 202
    item = claim(web)
    assert ack(web, item).status_code == 200
    observe(
        web,
        [
            source(
                "discord-web-1",
                author_id="web-hook",
                author_is_bot=True,
                webhook_id="web-hook",
                text="Ann, hello",
            ),
            source("same-name", author_display_name=web[5]["display_name"]),
        ],
    )
    assert status(web)["pending_count"] == 1
    assert [item["message_id"] for item in batch(web)["batch"]["items"]] == ["same-name"]
    other = web[1].post("/api/web-chat/profiles", json={"display_name": "Second"}).json()
    assert web[1].get(path(web, profile=other["id"])).json()["pending_count"] == 2


@pytest.mark.parametrize("operation", ["", "/batch", "/gap", "/complete"])
def test_room_profile_user_and_fresh_permissions_enforced_for_every_operation(web, operation):
    app, client, _, _, room, _profile = web
    user, visitor = member(web, can_post=False)
    owned = visitor.post("/api/web-chat/profiles", json={"display_name": "Member"}).json()
    payload = (
        {}
        if operation == "/batch"
        else {"event_id": "disconnect-event-12345"}
        if operation == "/gap"
        else {"batch_id": "unrelated"}
    )

    def request(client, endpoint):
        return (
            client.post(endpoint + operation, json=payload) if operation else client.get(endpoint)
        )

    assert request(TestClient(app), path(web)).status_code == 401
    assert request(visitor, path(web)).status_code == 404  # another participant's profile
    assert request(client, path(web, profile=owned["id"])).status_code == 404
    assert request(client, path(web, room="foreign-room")).status_code == 404
    endpoint = path(web, profile=owned["id"])
    assert request(visitor, endpoint).status_code == (409 if operation == "/complete" else 200)
    assert client.delete(f"/api/web-chat/rooms/{room}/members/{user.id}").status_code == 204
    assert request(visitor, endpoint).status_code == 404
    with app.state.database.session() as session:
        published = app.state.web_room_repository.require(
            room, client.get("/api/auth/me").json()["id"]
        )
        state = session.get(RoomStateRecord, scope_key(room_scope(published)))
        state.permission_checked_at = datetime.now(UTC) - timedelta(seconds=91)
        session.commit()
    assert request(client, path(web)).status_code == 503
    observe(web, [], readable=False)
    assert request(client, path(web)).status_code == 503


def test_demo_and_restricted_credentials_cannot_read_or_create_cursor(web):
    app, client, *_ = web
    with app.state.database.session() as session:
        profile = session.get(WebProfileRecord, web[5]["id"])
        user = session.get(UserRecord, profile.owner_id)
        user.email = PUBLIC_DEMO_EMAIL
        session.commit()
    assert client.get(path(web)).status_code == 403
    assert client.post(path(web) + "/batch", json={}).status_code == 403
    assert client.get(path(web), headers={"Authorization": "Bearer crcli_invalid"}).status_code in {
        401,
        403,
    }
    with app.state.database.session() as session:
        assert session.scalar(select(func.count()).select_from(AgentReadingCursorRecord)) == 0


def test_owner_lifecycle_deletes_member_progress_and_participant_cascade(web):
    app, _client, *_ = web
    batch(web)
    _user, visitor = member(web)
    profile = visitor.post("/api/web-chat/profiles", json={"display_name": "Member"}).json()
    assert visitor.post(path(web, profile=profile["id"]) + "/batch", json={}).status_code == 200
    with app.state.database.session() as session:
        own = session.get(WebProfileRecord, web[5]["id"]).owner_id
    counts = app.state.web_room_repository.delete_owner(own)
    assert counts["web_room_agent_reading_cursors"] == 2
    with app.state.database.session() as session:
        assert session.scalar(select(func.count()).select_from(AgentReadingCursorRecord)) == 0


def test_inaccessible_content_is_reference_placeholder_not_readable_body(web):
    observe(web, [source("hidden", text="", content_available=False)])
    active = batch(web)["batch"]
    assert active["items"][0]["change"] == "unavailable"
    assert active["items"][0]["state"] == "current"
    assert active["items"][0]["message"] is None
    assert "unavailable body" not in str(active)


def test_status_count_does_not_parse_backlog_and_active_read_is_bounded(web, monkeypatch):
    from echo_masque.persistence import agent_reading_repository as implementation

    messages = [source(f"bounded-{index}") for index in range(130)]
    for start in range(0, 130, 64):
        observe(web, messages[start : start + 64])
    parsed = []
    original = implementation._source_from_json

    def tracked(value):
        parsed.append(1)
        return original(value)

    monkeypatch.setattr(implementation, "_source_from_json", tracked)
    assert status(web)["pending_count"] == 130
    assert parsed == []  # SQL count, no unbounded body deserialization.
    batch(web)
    parsed.clear()
    assert len(status(web)["batch"]["items"]) == 64
    assert len(parsed) == 64


def test_participant_profile_fk_cascade_cannot_leave_progress_in_foreign_room(web):
    app, _client, *_ = web
    _user, visitor = member(web)
    profile = visitor.post("/api/web-chat/profiles", json={"display_name": "Member"}).json()
    assert visitor.post(path(web, profile=profile["id"]) + "/batch", json={}).status_code == 200
    with app.state.database.session() as session:
        session.delete(session.get(WebProfileRecord, profile["id"]))
        session.commit()
    with app.state.database.session() as session:
        assert session.scalar(select(func.count()).select_from(AgentReadingCursorRecord)) == 0
    assert web[1].get(f"/api/web-chat/rooms/{web[4]}/messages").status_code == 200


def test_repository_revalidates_revoked_session_inside_transaction(web):
    from echo_masque.web_rooms import WebRoomError

    app, *_ = web
    active = batch(web)["batch"]
    with app.state.database.session() as session:
        cursor = session.scalar(select(AgentReadingCursorRecord))
        auth = session.scalar(
            select(AuthSessionRecord).where(AuthSessionRecord.user_id == cursor.user_id)
        )
        auth.revoked_at = datetime.now(UTC)
        user_id, session_id = cursor.user_id, auth.id
        session.commit()
    with pytest.raises(WebRoomError, match="session_unavailable"):
        AgentReadingRepository(app.state.web_room_repository).complete(
            web[4],
            user_id,
            web[5]["id"],
            session_id=session_id,
            batch_id=active["id"],
        )
    with app.state.database.session() as session:
        assert session.scalar(select(AgentReadingCursorRecord)).batch_id == active["id"]


def test_tagged_cli_bearer_never_inherits_valid_browser_cookie_for_agent_routes(web):
    headers = {"Authorization": "Bearer crcli_invalid"}
    assert web[1].get(path(web), headers=headers).status_code in {401, 403}
    for suffix, payload in [
        ("batch", {}),
        ("gap", {"event_id": "gap-event-1234567890"}),
        ("complete", {"batch_id": "arbitrary"}),
    ]:
        assert web[1].post(path(web) + "/" + suffix, headers=headers, json=payload).status_code in {
            401,
            403,
        }
    with web[0].state.database.session() as session:
        assert session.scalar(select(func.count()).select_from(AgentReadingCursorRecord)) == 0


def test_two_granted_rooms_use_independent_source_and_participant_progress(web):
    _app, client, connection, *_ = web
    second = client.post(
        "/api/web-chat/rooms",
        json={
            "connection_id": connection["id"],
            "guild_id": "guild-phase3",
            "channel_id": "channel-phase3",
            "thread_id": "second-thread",
            "name": "Second",
        },
    )
    assert second.status_code == 201, second.text
    second_id = second.json()["id"]
    observe(web, [source("same-id", text="first room")])
    observe(
        web,
        [source("same-id", text="second room", thread_id="second-thread")],
        thread_id="second-thread",
    )
    assert status(web)["pending_count"] == 1
    other_path = path(web, room=second_id)
    assert client.get(other_path).json()["pending_count"] == 1
    first = batch(web)["batch"]
    assert [item["message"]["text"] for item in first["items"]] == ["first room"]
    complete(web, first["id"])
    other_status = client.get(other_path).json()
    assert other_status["pending_count"] == 1 and other_status["cursor_revision"] == 0
    other = client.post(other_path + "/batch", json={}).json()["batch"]
    assert [item["message"]["text"] for item in other["items"]] == ["second room"]
    assert client.post(other_path + "/complete", json={"batch_id": first["id"]}).status_code == 409
    assert client.post(other_path + "/complete", json={"batch_id": other["id"]}).status_code == 200
    assert status(web)["pending_count"] == 0


def test_old_edit_changes_snapshot_source_revision_without_changing_latest_messages(web):
    base = datetime.now(UTC)
    messages = [
        source(f"old-{index}", created_at=(base + timedelta(seconds=index)).isoformat())
        for index in range(65)
    ]
    observe(web, messages[:64])
    observe(web, messages[64:])
    endpoint = f"/api/web-chat/rooms/{web[4]}/messages"
    before = web[1].get(endpoint).json()
    observe(
        web,
        [
            {
                **messages[0],
                "text": "changed outside snapshot",
                "edited_at": (base + timedelta(seconds=100)).isoformat(),
            }
        ],
    )
    after = web[1].get(endpoint).json()
    assert before["messages"] == after["messages"]
    assert after["source_revision"] == before["source_revision"] + 1
