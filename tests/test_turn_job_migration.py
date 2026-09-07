from __future__ import annotations

from sqlalchemy import inspect, text

from echo_masque.persistence import Database
from echo_masque.persistence.turn_job_models import TurnJobRecord
from echo_masque.persistence.turn_job_repository import TurnJobRepository


def test_initialize_adds_turn_job_author_column_to_an_existing_sqlite_database(tmp_path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'turn-jobs.db'}")
    database.initialize()
    repository = TurnJobRepository(database)
    original, created = repository.submit(
        kind="message",
        owner_id="owner-1",
        connection_id="connection-1",
        deployment_id="deployment-1",
        guild_id="guild-1",
        channel_id="channel-1",
        message_id="message-1",
        source_author_id="author-1",
        request_json='{"message":"preserve this"}',
        deadline_seconds=300,
    )
    assert created

    # SQLite will not drop an indexed column until its generated index is removed.  This models
    # an installed schema from before ``source_author_id`` existed without rebuilding the table
    # or touching the existing job row.
    with database.engine.begin() as connection:
        for index in inspect(connection).get_indexes("discord_turn_jobs"):
            if "source_author_id" in index["column_names"]:
                connection.execute(text(f'DROP INDEX "{index["name"]}"'))
        connection.execute(text("ALTER TABLE discord_turn_jobs DROP COLUMN source_author_id"))

    assert "source_author_id" not in {
        column["name"] for column in inspect(database.engine).get_columns("discord_turn_jobs")
    }

    database.initialize()
    database.initialize()

    columns = {
        column["name"] for column in inspect(database.engine).get_columns("discord_turn_jobs")
    }
    assert "source_author_id" in columns
    with database.session() as session:
        migrated = session.get(TurnJobRecord, original.job_id)
    assert migrated is not None
    assert migrated.source_author_id == ""
    assert migrated.request_json == '{"message":"preserve this"}'
    assert migrated.connection_id == "connection-1"
    assert migrated.deployment_id == "deployment-1"
