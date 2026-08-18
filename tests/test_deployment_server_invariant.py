from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from echo_masque.persistence.database import Database
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord


def deployment(*, channel_id: str) -> CharacterDeploymentRecord:
    return CharacterDeploymentRecord(
        id=str(uuid4()),
        owner_id="owner-1",
        character_card_id="character-1",
        connection_id="connection-1",
        platform="discord",
        workspace_id="guild-1",
        workspace_name="Guild One",
        channel_id=channel_id,
        channel_name=f"#{channel_id}",
        thread_id="",
        thread_name="",
        participation_mode="mention_and_reply",
        memory_scope="channel_isolated",
        version_label="Current",
        sticker_count=0,
        status="paused",
    )


def test_legacy_duplicates_are_reported_without_destructive_cleanup(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'legacy-duplicates.db'}")
    database.initialize()

    # Simulate rows that predate the server-wide uniqueness invariant. The existing
    # channel-level uniqueness rule allowed these records because their channels differ.
    with database.engine.begin() as connection:
        connection.exec_driver_sql("DROP TRIGGER cr_one_character_per_discord_server_insert")
        connection.exec_driver_sql("DROP TRIGGER cr_one_character_per_discord_server_update")
    with database.session() as session:
        session.add(deployment(channel_id="channel-a"))
        session.add(deployment(channel_id="channel-b"))
        session.commit()

    # Re-initialization installs the new non-destructive guards but must not delete either
    # legacy row. Instead the explicit inspection path reports the conflict for owner repair.
    database.initialize()
    duplicates = database.inspect_deployment_server_duplicates()
    assert len(duplicates) == 1
    assert duplicates[0].owner_id == "owner-1"
    assert duplicates[0].connection_id == "connection-1"
    assert duplicates[0].workspace_id == "guild-1"
    assert duplicates[0].character_card_id == "character-1"
    assert duplicates[0].deployment_count == 2

    with database.session() as session:
        assert len(list(session.query(CharacterDeploymentRecord))) == 2
        session.add(deployment(channel_id="channel-c"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
