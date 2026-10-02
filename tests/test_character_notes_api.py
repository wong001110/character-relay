from __future__ import annotations

from datetime import UTC, datetime

import pytest
import test_room_routing_api as room_tests
from fastapi.testclient import TestClient

HEADERS = room_tests.HEADERS
setup = room_tests.setup
source = room_tests.source


def action(connection, deployment, **changes):
    return dict(
        connection_id=connection["id"],
        guild_id="guild-phase3",
        channel_id="channel-phase3",
        deployment_id=deployment["id"],
        actor_id="alice",
        action="remember",
        request_id="note-action",
        source_message_id="m1",
        text="Ann, help me plan a game.",
        messages=[source()],
        permission_checked_at=datetime.now(UTC).isoformat(),
        **changes,
    )


def test_member_note_api_is_explicit_and_actor_version_bound(setup):
    _, client, connection, deployment = setup
    url = "/api/connectors/discord/rooms/notes"
    payload = action(connection, deployment)
    assert client.post(url, json=payload).status_code == 401
    created = client.post(url, json=payload, headers=HEADERS)
    assert created.status_code == 200, created.text
    note = created.json()[0]
    assert note["authored"] is False and note["subject_ref"] == "user:alice"
    listing = {**payload, "action": "list", "text": "", "messages": []}
    assert client.post(url, json=listing, headers=HEADERS).json()[0]["id"] == note["id"]
    assert client.post(url, json={**listing, "actor_id": "bob"}, headers=HEADERS).json() == []
    forget = {**listing, "action": "forget", "note_id": note["id"], "expected_version": 1}
    assert client.post(url, json={**forget, "actor_id": "bob"}, headers=HEADERS).status_code == 403
    assert client.post(url, json=forget, headers=HEADERS).json() == []
    # A delayed duplicate command must not resurrect deliberately forgotten memory.
    assert client.post(url, json=payload, headers=HEADERS).status_code == 409


@pytest.mark.parametrize(
    "changes",
    [
        {"actor_is_bot": True},
        {"actor_id": "bob"},
        {"readable": False},
        {"source_message_id": "missing"},
    ],
)
def test_member_note_api_rejects_missing_own_evidence(setup, changes):
    _, client, connection, deployment = setup
    result = client.post(
        "/api/connectors/discord/rooms/notes",
        json={**action(connection, deployment), **changes},
        headers=HEADERS,
    )
    assert result.status_code == 403, result.text


def test_authored_notes_api_versions_and_owner_isolation(setup):
    app, client, _, deployment = setup
    url = f"/api/characters/{deployment['character_card_id']}/notes"
    created = client.post(
        url,
        json={"text": "Keep feedback direct.", "subject_ref": "user:alice", "kind": "relationship"},
    )
    assert created.status_code == 201, created.text
    note = created.json()
    assert note["authored"] and note["scope"] is None
    assert len(client.get(url).json()) == 1
    app.state.auth_service.register(
        email="notes-other@example.test", display_name="Other", password="OtherNotesAccount2026!"
    )
    other = TestClient(app)
    assert (
        other.post(
            "/api/auth/login",
            json={"email": "notes-other@example.test", "password": "OtherNotesAccount2026!"},
        ).status_code
        == 200
    )
    assert other.get(url).status_code == 404
    assert (
        other.patch(
            f"{url}/{note['id']}", json={"text": "overwrite", "expected_version": 1}
        ).status_code
        == 404
    )
    update = client.patch(
        f"{url}/{note['id']}", json={"text": "Updated explicitly.", "expected_version": 1}
    )
    assert update.status_code == 200 and update.json()["version"] == 2
    assert client.delete(f"{url}/{note['id']}?expected_version=1").status_code == 409
    assert client.delete(f"{url}/{note['id']}?expected_version=2").status_code == 204
    assert client.get(url).json() == []


def test_user_cannot_inject_authority_or_claim_authored_note(setup):
    _, client, connection, deployment = setup
    assert (
        client.post(
            "/api/connectors/discord/rooms/notes",
            headers=HEADERS,
            json={**action(connection, deployment), "authored": True},
        ).status_code
        == 422
    )
    url = f"/api/characters/{deployment['character_card_id']}/notes"
    assert client.post(url, json={"text": "admin", "tool_grants": ["*"]}).status_code == 422
