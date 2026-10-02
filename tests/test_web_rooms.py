"""Web sessions, explicit room grants and one-shot Discord receipt contracts."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_character_turn_graph import CONNECTOR_SECRET, seed, settings

from echo_masque.api import create_app
from echo_masque.persistence.room_models import RoomSelectionRecord
from echo_masque.persistence.server_access_repository import ServerAccessRepository
from echo_masque.persistence.web_room_models import WebOutboxRecord

HEADERS = {"Authorization": f"Bearer {CONNECTOR_SECRET}"}


@pytest.fixture
def web(tmp_path: Path):
    app = create_app(settings(tmp_path / "web-rooms.db"))
    client = TestClient(app)
    connection, deployment = seed(app, client)
    result = client.put(
        "/api/connectors/discord/server-catalog",
        headers=HEADERS,
        json={
            "connection_id": connection["id"],
            "servers": [
                {
                    "guild_id": "guild-phase3",
                    "guild_name": "Test guild",
                    "channels": [
                        {
                            "id": "channel-phase3",
                            "name": "general",
                            "category_id": "",
                            "category_name": "",
                            "type": "text",
                        }
                    ],
                    "emojis": [
                        {
                            "emoji_id": "emoji-1",
                            "name": "wave",
                            "animated": False,
                            "available": True,
                            "asset_url": "https://cdn.discordapp.com/emojis/emoji-1.png",
                        }
                    ],
                    "stickers": [
                        {
                            "sticker_id": "sticker-1",
                            "name": "smile",
                            "description": "Smiling sticker",
                            "tags": ["smile"],
                            "format_type": "png",
                            "asset_url": "https://cdn.discordapp.com/stickers/sticker-1.png",
                        }
                    ],
                }
            ],
        },
    )
    assert result.status_code == 204, result.text
    result = client.post(
        "/api/web-chat/rooms",
        json={
            "connection_id": connection["id"],
            "guild_id": "guild-phase3",
            "channel_id": "channel-phase3",
            "name": "General",
        },
    )
    assert result.status_code == 201, result.text
    room = result.json()["id"]
    profile = client.post("/api/web-chat/profiles", json={"display_name": "Little Dragon"}).json()
    assert "id" in profile, profile
    fixture = (app, client, connection, deployment, room, profile)
    observe(fixture, [])
    assert (
        client.put(
            f"/api/connectors/discord/web-chat/rooms/{room}/webhook",
            headers=HEADERS,
            json={"connection_id": connection["id"], "webhook_id": "web-hook"},
        ).status_code
        == 204
    )
    return fixture


def source(message_id="human-1", **changes):
    return {
        "message_id": message_id,
        "channel_id": "channel-phase3",
        "author_id": "human",
        "author_display_name": "Human",
        "author_is_bot": False,
        "text": "Hello",
        "created_at": datetime.now(UTC).isoformat(),
        **changes,
    }


def observe(web, messages, **changes):
    _, client, connection, _, _, _ = web
    result = client.post(
        "/api/connectors/discord/rooms/events",
        headers=HEADERS,
        json={
            "connection_id": connection["id"],
            "guild_id": "guild-phase3",
            "channel_id": "channel-phase3",
            "messages": messages,
            "readable": True,
            "permission_checked_at": datetime.now(UTC).isoformat(),
            **changes,
        },
    )
    assert result.status_code == 200, result.text
    return result.json()


def send(web, key="client-message-1", **changes):
    _, client, _, _, room, profile = web
    return client.post(
        f"/api/web-chat/rooms/{room}/messages",
        json={
            "client_message_id": key,
            "profile_id": profile["id"],
            "text": "Ann, hello",
            **changes,
        },
    )


def claim(web, nonce="claim-nonce-12345678"):
    _, client, connection, _, room, _ = web
    result = client.post(
        f"/api/connectors/discord/web-chat/rooms/{room}/claim",
        headers=HEADERS,
        json={"connection_id": connection["id"], "claim_nonce": nonce},
    )
    assert result.status_code == 200, result.text
    return result.json()


def ack(web, item, **changes):
    _, client, connection, _, _, _ = web
    return client.post(
        f"/api/connectors/discord/web-chat/outbox/{item['id']}/ack",
        headers=HEADERS,
        json={
            "connection_id": connection["id"],
            "claim_nonce": item["claim_nonce"],
            "status": "delivered",
            "message_id": "discord-web-1",
            "webhook_id": "web-hook",
            "created_at": datetime.now(UTC).isoformat(),
            **changes,
        },
    )


def member(web, *, grant_server=True, grant_room=True, can_post=True):
    app, client, connection, _, room, _ = web
    user = app.state.auth_service.register(
        email="web-member@example.com", display_name="Member", password="MemberPassphrase2026!"
    )
    visitor = TestClient(app)
    assert (
        visitor.post(
            "/api/auth/login", json={"email": user.email, "password": "MemberPassphrase2026!"}
        ).status_code
        == 200
    )
    if grant_server:
        ServerAccessRepository(app.state.database).grant_access(
            user_id=user.id, connection_id=connection["id"], guild_id="guild-phase3", source="test"
        )
    if grant_room:
        result = client.put(
            f"/api/web-chat/rooms/{room}/members", json={"user_id": user.id, "can_post": can_post}
        )
        assert result.status_code == 204, result.text
    return user, visitor


def test_existing_login_does_not_grant_room_or_profile_access(web):
    app, client, _, _, room, profile = web
    anonymous = TestClient(app)
    assert anonymous.get("/api/web-chat/rooms").status_code == 401
    user, visitor = member(web, grant_room=False)
    assert visitor.get("/api/web-chat/rooms").json() == []
    assert visitor.get(f"/api/web-chat/rooms/{room}/messages").status_code == 404
    assert (
        visitor.patch(
            f"/api/web-chat/profiles/{profile['id']}",
            json={"display_name": "Admin", "expected_version": 1},
        ).status_code
        == 404
    )
    assert (
        client.put(f"/api/web-chat/rooms/{room}/members", json={"user_id": user.id}).status_code
        == 204
    )
    assert visitor.get(f"/api/web-chat/rooms/{room}/messages").status_code == 200
    result = visitor.post(
        f"/api/web-chat/rooms/{room}/messages",
        json={"profile_id": profile["id"], "client_message_id": "not-my-profile", "text": "spoof"},
    )
    assert result.status_code == 404
    assert visitor.get("/api/web-chat/profiles").json() == []


def test_room_grant_requires_server_access(web):
    _, client, _, _, room, _ = web
    user, visitor = member(web, grant_server=False, grant_room=False)
    result = client.put(f"/api/web-chat/rooms/{room}/members", json={"user_id": user.id})
    assert result.status_code in {403, 404}, result.text
    assert visitor.get("/api/web-chat/rooms").json() == []


def test_readonly_membership_and_revocation_apply_to_reads_and_sends(web):
    _, client, _, _, room, _ = web
    user, visitor = member(web, can_post=False)
    profile = visitor.post("/api/web-chat/profiles", json={"display_name": "Member"}).json()
    assert visitor.get(f"/api/web-chat/rooms/{room}/messages").status_code == 200
    result = visitor.post(
        f"/api/web-chat/rooms/{room}/messages",
        json={"profile_id": profile["id"], "client_message_id": "read-only-send", "text": "hello"},
    )
    assert result.status_code in {403, 404}
    assert client.delete(f"/api/web-chat/rooms/{room}/members/{user.id}").status_code == 204
    assert visitor.get(f"/api/web-chat/rooms/{room}/messages").status_code == 404


@pytest.mark.parametrize(
    "avatar",
    [
        "http://example.com/a.png",
        "https://127.0.0.1/a",
        "https://192.168.1.2/a",
        "https://user:pass@example.com/a",
        "https://host.local/a",
        "javascript:alert(1)",
    ],
)
def test_profile_rejects_unsafe_avatar_without_fetching(web, avatar):
    assert (
        web[1]
        .post("/api/web-chat/profiles", json={"display_name": "Fine", "avatar_url": avatar})
        .status_code
        == 422
    )


def test_profile_version_and_presentation_do_not_change_identity(web):
    _, client, _, _, _, profile = web
    result = client.patch(
        f"/api/web-chat/profiles/{profile['id']}",
        json={
            "expected_version": 1,
            "display_name": "Admin",
            "avatar_url": "https://cdn.discordapp.com/a.png",
        },
    )
    assert result.status_code == 200, result.text
    assert result.json()["id"] == profile["id"]
    assert result.json()["version"] == 2
    assert (
        client.patch(
            f"/api/web-chat/profiles/{profile['id']}",
            json={"expected_version": 1, "display_name": "stale"},
        ).status_code
        == 409
    )


def test_idempotent_pending_send_is_not_delivered_and_payload_conflict_is_rejected(web):
    result = send(web)
    assert result.status_code == 202, result.text
    assert result.json()["status"] == "pending"
    assert result.json()["discord_message_id"] == ""
    assert send(web).json()["id"] == result.json()["id"]
    assert send(web, text="different").status_code == 409
    app, client, _, _, room, profile = web
    assert (
        client.patch(
            f"/api/web-chat/profiles/{profile['id']}",
            json={"expected_version": 1, "display_name": "Changed"},
        ).status_code
        == 200
    )
    item = claim(web)
    assert item["display_name"] == "Little Dragon"  # immutable authored presentation
    assert claim(web, "another-nonce-123456") is None
    assert "claim_nonce" not in client.get(f"/api/web-chat/rooms/{room}/messages").text
    with app.state.database.session() as session:
        assert len(session.scalars(select(WebOutboxRecord)).all()) == 1


def test_unreadable_or_stale_channel_rejects_sends_and_history(web):
    observe(web, [], readable=False)
    assert send(web).status_code == 503
    _, client, _, _, room, _ = web
    assert client.get(f"/api/web-chat/rooms/{room}/messages").status_code == 503


def test_reply_requires_permitted_live_source_in_exact_room(web):
    assert send(web, reply_to_message_id="elsewhere").status_code == 422
    observe(web, [source()])
    result = send(web, reply_to_message_id="human-1")
    assert result.status_code == 202, result.text
    item = claim(web)
    observe(web, [source(deleted=True, text="", content_available=False)])
    assert (
        web[0].state.web_room_repository.preflight(web[2]["id"], item["id"], item["claim_nonce"])
        is False
    )


def test_claim_expiry_is_uncertain_never_a_resend(web):
    send(web)
    item = claim(web)
    with web[0].state.database.session() as session:
        record = session.get(WebOutboxRecord, item["id"])
        record.claimed_at = datetime.now(UTC) - timedelta(minutes=3)
        session.commit()
    assert claim(web, "claim-nonce-next-12345") is None
    assert (
        web[1].get(f"/api/web-chat/rooms/{web[4]}/messages").json()["outbox"][0]["status"]
        == "uncertain"
    )
    result = ack(web, item)
    assert result.status_code == 200, result.text  # exact late receipt can resolve uncertainty


def test_ack_claim_and_webhook_binding_and_exact_retries(web):
    send(web)
    item = claim(web)
    assert ack(web, item, claim_nonce="wrong-nonce-123456").status_code == 409
    assert ack(web, item, webhook_id="another-hook").status_code == 409
    assert ack(web, item, created_at="2026-10-02T00:00:00").status_code == 422
    assert ack(web, item).status_code == 200
    assert ack(web, item).status_code == 200
    assert ack(web, item, message_id="different").status_code == 409
    assert claim(web) is None


def test_revocation_stops_claim_but_does_not_discard_actual_receipt(web):
    _, client, _, _, room, _ = web
    send(web)
    item = claim(web)
    assert client.patch(f"/api/web-chat/rooms/{room}", json={"enabled": False}).status_code == 204
    assert (
        web[0].state.web_room_repository.preflight(web[2]["id"], item["id"], item["claim_nonce"])
        is False
    )
    assert ack(web, item).status_code == 200
    assert client.get(f"/api/web-chat/rooms/{room}/messages").status_code == 404


def test_gateway_before_ack_then_duplicate_echo_has_one_canonical_web_identity(web):
    _, client, connection, deployment, room, profile = web
    send(web)
    item = claim(web)
    message = source(
        "discord-web-1",
        author_id="web-hook",
        author_display_name="Admin",
        author_is_bot=True,
        webhook_id="web-hook",
        text="Ann, hello",
    )
    observe(web, [message])
    assert client.get(f"/api/web-chat/rooms/{room}/messages").json()["messages"] == []
    assert ack(web, item).status_code == 200
    observe(web, [message])
    observe(web, [message])
    rows = client.get(f"/api/web-chat/rooms/{room}/messages").json()["messages"]
    assert len(rows) == 1
    assert rows[0]["author_id"] == f"web:{profile['id']}"
    assert rows[0]["display_name"] == "Little Dragon"
    assert rows[0]["actor_type"] == "web_participant"
    result = client.post(
        "/api/connectors/discord/rooms/resolve",
        headers=HEADERS,
        json={
            "connection_id": connection["id"],
            "guild_id": "guild-phase3",
            "channel_id": "channel-phase3",
            "messages": [message],
            "permission_checked_at": datetime.now(UTC).isoformat(),
            "request_id": message["message_id"],
            "trigger_message_id": message["message_id"],
            "deployment_ids": [deployment["id"]],
            "explicit_deployment_ids": [deployment["id"]],
        },
    )
    assert result.status_code == 200, result.text
    assert result.json()["outcome"] == "direct", result.text
    with web[0].state.database.session() as session:
        selected = session.get(RoomSelectionRecord, result.json()["choices"][0]["selection_id"])
    assert selected.requester_is_bot is True
    assert selected.requester_id == ""


def test_web_receipt_does_not_authorize_other_channel_or_forged_external_identity(web):
    _, client, connection, _, _, _ = web
    send(web)
    item = claim(web)
    assert ack(web, item).status_code == 200
    result = client.post(
        "/api/connectors/discord/rooms/events",
        headers=HEADERS,
        json={
            "connection_id": connection["id"],
            "guild_id": "guild-phase3",
            "channel_id": "channel-phase3",
            "permission_checked_at": datetime.now(UTC).isoformat(),
            "messages": [
                source(
                    "discord-web-1", author_id="web-hook", author_is_bot=True, webhook_id="wrong"
                )
            ],
        },
    )
    assert result.status_code == 403
    result = client.post(
        "/api/connectors/discord/rooms/events",
        headers=HEADERS,
        json={
            "connection_id": connection["id"],
            "guild_id": "guild-phase3",
            "channel_id": "channel-phase3",
            "permission_checked_at": datetime.now(UTC).isoformat(),
            "messages": [
                source(
                    "forged",
                    author_id="web-hook",
                    author_is_bot=True,
                    author_external_id="claimed-profile",
                )
            ],
        },
    )
    assert result.status_code == 403


def test_delete_before_ack_stays_deleted_and_edit_updates(web):
    _, client, _, _, room, _ = web
    send(web)
    item = claim(web)
    observe(web, [source("discord-web-1", deleted=True, text="", content_available=False)])
    assert ack(web, item).status_code == 200
    observe(
        web,
        [
            source(
                "discord-web-1",
                author_id="web-hook",
                author_is_bot=True,
                webhook_id="web-hook",
                text="late echo",
            )
        ],
    )
    rows = client.get(f"/api/web-chat/rooms/{room}/messages").json()["messages"]
    assert rows[0]["deleted"] is True
    assert rows[0]["text"] == ""


def test_transport_requires_secret_and_profile_api_rejects_legacy_identity(web):
    app, client, connection, _, room, _ = web
    anonymous = TestClient(app)
    assert (
        anonymous.get(
            f"/api/connectors/discord/web-chat/rooms?connection_id={connection['id']}"
        ).status_code
        == 401
    )
    assert (
        anonymous.get("/api/web-chat/profiles", headers={"X-User-Id": "local-user"}).status_code
        == 401
    )
    assert (
        client.post(
            f"/api/connectors/discord/web-chat/rooms/{room}/claim",
            headers=HEADERS,
            json={"connection_id": "other", "claim_nonce": "claim-nonce-test-1234"},
        ).status_code
        == 404
    )


def test_room_expression_picker_is_guild_scoped(web):
    _, client, _, _, room, _ = web
    result = client.get(f"/api/web-chat/rooms/{room}/expressions")
    assert result.status_code == 200, result.text
    resources = {item["resource_key"]: item for item in result.json()}
    assert resources["emoji:emoji-1"]["name"] == "wave"
    assert resources["sticker:sticker-1"]["name"] == "smile"
    assert all(item["asset_url"].startswith("https://cdn.discordapp.com/") for item in resources.values())


def test_snapshot_preserves_media_reactions_and_reply_preview(web):
    _, client, _, _, room, _ = web
    observe(
        web,
        [
            source(
                "parent",
                text="Look at this <:wave:emoji-1>",
                custom_emojis=[
                    {
                        "resource_id": "emoji-1",
                        "name": "wave",
                        "asset_url": "https://cdn.discordapp.com/emojis/emoji-1.png",
                    }
                ],
                attachments=[
                    {
                        "attachment_id": "attachment-1",
                        "url": "https://cdn.discordapp.com/attachments/a/image.png",
                        "proxy_url": "https://media.discordapp.net/attachments/a/image.png",
                        "filename": "image.png",
                        "description": "Cat image",
                        "content_type": "image/png",
                        "size_bytes": 1234,
                        "width": 320,
                        "height": 240,
                    }
                ],
                stickers=[
                    {
                        "resource_id": "sticker-1",
                        "name": "smile",
                        "asset_url": "https://cdn.discordapp.com/stickers/sticker-1.png",
                        "format_type": "png",
                    }
                ],
                mentions=[
                    {"kind": "user", "target_id": "human-2", "label": "Bob"},
                    {"kind": "channel", "target_id": "channel-2", "label": "memes"},
                ],
                embeds=[
                    {
                        "embed_type": "rich",
                        "url": "https://example.com/post",
                        "title": "Preview",
                        "description": "Preview description",
                        "provider_name": "Example",
                        "image_url": "https://example.com/image.png",
                        "image_proxy_url": "https://media.discordapp.net/external/image.png",
                    }
                ],
                poll={
                    "question": "Tea?",
                    "answers": [
                        {"answer_id": 1, "text": "Yes", "vote_count": 3},
                        {"answer_id": 2, "text": "No", "vote_count": 1},
                    ],
                    "allow_multiselect": False,
                    "results_finalized": False,
                },
                reactions=[
                    {"key": "unicode:😂", "name": "😂", "count": 2},
                ],
                pinned=True,
            ),
            source(
                "child",
                text="reply",
                reply_to_message_id="parent",
            ),
        ],
    )
    rows = client.get(f"/api/web-chat/rooms/{room}/messages").json()["messages"]
    parent = next(item for item in rows if item["id"] == "parent")
    child = next(item for item in rows if item["id"] == "child")
    assert parent["attachments"][0]["filename"] == "image.png"
    assert parent["custom_emojis"][0]["name"] == "wave"
    assert parent["stickers"][0]["name"] == "smile"
    assert parent["mentions"][0]["label"] == "Bob"
    assert parent["embeds"][0]["image_proxy_url"].startswith("https://media.discordapp.net/")
    assert parent["poll"]["question"] == "Tea?"
    assert parent["poll"]["answers"][0]["vote_count"] == 3
    assert parent["reactions"][0]["discord_count"] == 2
    assert parent["pinned"] is True
    assert child["reply_preview"] == {
        "message_id": "parent",
        "available": True,
        "in_snapshot": True,
        "display_name": "Human",
        "summary": "Look at this <:wave:emoji-1>",
    }


def test_web_reactions_are_profile_bound_and_not_discord_identity(web):
    _, client, _, _, room, profile = web
    observe(web, [source()])
    payload = {
        "profile_id": profile["id"],
        "emoji_key": "emoji:emoji-1",
        "emoji_name": "forged-name",
    }
    result = client.put(
        f"/api/web-chat/rooms/{room}/messages/human-1/reactions",
        json=payload,
    )
    assert result.status_code == 204, result.text
    row = client.get(f"/api/web-chat/rooms/{room}/messages").json()["messages"][0]
    reaction = next(item for item in row["reactions"] if item["key"] == "emoji:emoji-1")
    assert reaction["name"] == "wave"
    assert reaction["web_count"] == 1
    assert reaction["discord_count"] == 0
    assert reaction["mine_profile_ids"] == [profile["id"]]

    result = client.request(
        "DELETE",
        f"/api/web-chat/rooms/{room}/messages/human-1/reactions",
        json=payload,
    )
    assert result.status_code == 204, result.text
    row = client.get(f"/api/web-chat/rooms/{room}/messages").json()["messages"][0]
    assert all(item["key"] != "emoji:emoji-1" for item in row["reactions"])


def test_sticker_only_send_is_validated_and_claimed_with_server_resource(web):
    result = send(
        web,
        key="sticker-only",
        text="",
        sticker_resource_key="sticker:sticker-1",
    )
    assert result.status_code == 202, result.text
    assert result.json()["sticker_resource_key"] == "sticker:sticker-1"
    item = claim(web)
    assert item["sticker_name"] == "smile"
    assert item["sticker_asset_url"].startswith("https://cdn.discordapp.com/")
    assert item["sticker_format_type"] == "png"


def test_unknown_sticker_resource_is_rejected_before_outbox(web):
    result = send(
        web,
        key="missing-sticker",
        text="",
        sticker_resource_key="sticker:not-in-this-guild",
    )
    assert result.status_code == 422
