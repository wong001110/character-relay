"""Fixed Agent batches across workers on the explicitly disposable CI PostgreSQL DB."""

from concurrent.futures import ThreadPoolExecutor

import test_web_rooms
from sqlalchemy import select
from test_database_foundation import _destructive_postgres_test_url

from echo_masque.persistence.agent_reading_repository import AgentReadingRepository
from echo_masque.persistence.database import Database
from echo_masque.persistence.models import Base
from echo_masque.persistence.schema_migration_models import DatabaseSchemaMigrationRecord
from echo_masque.persistence.web_room_repository import WebRoomRepository


def test_postgresql_agent_batches_are_durable_and_fixed_across_workers(tmp_path, monkeypatch):
    url = _destructive_postgres_test_url()
    reset = Database(url)
    try:
        Base.metadata.drop_all(reset.engine)
    finally:
        reset.engine.dispose()
    original_settings = test_web_rooms.settings
    monkeypatch.setattr(
        test_web_rooms,
        "settings",
        lambda path: original_settings(path).model_copy(update={"database_url": url}),
    )
    web = test_web_rooms.web.__wrapped__(tmp_path)
    app, client, _, _, room, profile = web
    token = client.cookies.get(app.state.settings.auth_cookie_name)
    identity = app.state.auth_service.resolve(token)
    assert identity is not None and identity.session_id is not None
    second_database = Database(url)
    try:
        test_web_rooms.observe(web, [test_web_rooms.source("pg-agent-first")])
        second_database.initialize()
        second_database.initialize()
        services = [
            AgentReadingRepository(app.state.web_room_repository),
            AgentReadingRepository(WebRoomRepository(second_database)),
        ]
        args = (room, identity.user.id, profile["id"])
        kwargs = {"session_id": identity.session_id}
        with ThreadPoolExecutor(max_workers=2) as executor:
            starts = list(executor.map(lambda service: service.batch(*args, **kwargs), services))
        captured = starts[0].batch
        assert captured is not None
        assert starts[1].batch.id == captured.id
        test_web_rooms.observe(web, [test_web_rooms.source("pg-agent-late")])
        services[1].gap(*args, **kwargs, event_id="postgres-late-gap-0001")
        with ThreadPoolExecutor(max_workers=2) as executor:
            completed = list(
                executor.map(
                    lambda service: service.complete(*args, **kwargs, batch_id=captured.id),
                    services,
                )
            )
        assert all(state.cursor_revision == captured.to_revision for state in completed)
        assert all(state.needs_reread and state.pending_count == 1 for state in completed)
        next_batch = services[1].batch(*args, **kwargs).batch
        assert next_batch is not None and next_batch.id != captured.id
        # A retry of the old confirmation cannot finish the next batch.
        services[0].complete(*args, **kwargs, batch_id=captured.id)
        still_active = services[1].status(*args, **kwargs)
        assert still_active.batch.id == next_batch.id
        assert still_active.cursor_revision == captured.to_revision
        final = services[0].complete(*args, **kwargs, batch_id=next_batch.id)
        assert final.pending_count == 0 and not final.needs_reread
        with second_database.session() as session:
            assert (
                len(
                    session.scalars(
                        select(DatabaseSchemaMigrationRecord).where(
                            DatabaseSchemaMigrationRecord.revision == "web-room-agent-reading-v1"
                        )
                    ).all()
                )
                == 1
            )
    finally:
        second_database.engine.dispose()
        app.state.database.engine.dispose()
