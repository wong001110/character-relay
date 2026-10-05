"""Retirement of backend batch processing preserves existing metadata."""

from sqlalchemy import func, select
from test_web_rooms import web as web

from echo_masque.persistence.agent_reading_models import AgentReadingCursorRecord
from echo_masque.persistence.web_room_models import WebProfileRecord


def test_retired_agent_routes_are_absent_from_runtime_and_openapi(web):
    app, client, _, _, room, profile = web
    base = f"/api/web-chat/rooms/{room}/agent-reading/{profile['id']}"
    for method, suffix in [
        ("GET", ""),
        ("POST", "/gap"),
        ("POST", "/batch"),
        ("POST", "/complete"),
    ]:
        expected = 404 if method == "GET" else 405
        assert client.request(method, base + suffix).status_code == expected
    assert not any("agent-reading" in route for route in app.openapi()["paths"])
    with app.state.database.session() as session:
        assert session.scalar(select(func.count()).select_from(AgentReadingCursorRecord)) == 0


def test_retired_metadata_survives_restart_and_is_only_removed_by_existing_owner_cleanup(web):
    app, _, _, _, room, profile = web
    with app.state.database.session() as session:
        owner_id = session.get(WebProfileRecord, profile["id"]).owner_id
        session.add(
            AgentReadingCursorRecord(
                id="retained-legacy",
                user_id=owner_id,
                room_id=room,
                profile_id=profile["id"],
                cursor_revision=42,
            )
        )
        session.commit()
    app.state.database.initialize()
    with app.state.database.session() as session:
        assert session.get(AgentReadingCursorRecord, "retained-legacy").cursor_revision == 42
    app.state.web_room_repository.delete_owner(owner_id)
    with app.state.database.session() as session:
        assert session.get(AgentReadingCursorRecord, "retained-legacy") is None
