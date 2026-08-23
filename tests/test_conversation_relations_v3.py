from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from echo_masque.conversation_relations import ConversationRelationService
from echo_masque.persistence import Database
from echo_masque.persistence.conversation_structure_repository import (
    ConversationStructureRepository,
)


def _service() -> ConversationRelationService:
    database = Database("sqlite://")
    database.initialize()
    return ConversationRelationService(ConversationStructureRepository(database))


def test_relation_revision_preserves_original_interpretation_and_author_snapshots() -> None:
    service = _service()
    now = datetime.now(UTC)
    original = service.record(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="general",
        discord_thread_id="",
        source_message_id="m1",
        source_author_id="member-1",
        source_author_display_name="Mina",
        relation_type="INSULTS",
        target_ref_type="deployment",
        target_ref="zhi",
        target_author_id="character-zhi",
        target_author_display_name="Zhi",
        confidence=0.58,
        source="semantic_judge",
        evidence_refs=("message:m1",),
        status="unresolved",
        now=now,
    )
    replacement = service.revise(
        owner_id="owner-1",
        relation_id=original.id,
        target_ref_type="deployment",
        target_ref="zhi",
        confidence=0.99,
        source="explicit_clarification",
        evidence_refs=("message:m1", "message:m2"),
        status="resolved",
        now=now,
    )

    history = service.history(
        owner_id="owner-1",
        source_message_id="m1",
        relation_type="INSULTS",
    )
    assert len(history) == 2
    assert history[0].id == original.id
    assert history[0].status == "superseded"
    assert history[1].id == replacement.id
    assert history[1].status == "resolved"
    assert history[1].supersedes_relation_id == original.id
    assert history[1].evidence_refs == ("message:m1", "message:m2")
    assert history[1].source_author_display_name == "Mina"
    assert history[1].target_author_display_name == "Zhi"


def test_existing_sqlite_relation_table_gains_author_snapshot_columns(tmp_path: Path) -> None:
    path = tmp_path / "relations.db"
    database = Database(f"sqlite:///{path}")
    database.initialize()
    with database.engine.begin() as connection:
        for column in (
            "source_author_id",
            "source_author_display_name",
            "target_author_id",
            "target_author_display_name",
        ):
            connection.exec_driver_sql(f"ALTER TABLE message_relations_v3 DROP COLUMN {column}")

    database.initialize()
    with database.engine.connect() as connection:
        columns = {
            str(row[1])
            for row in connection.exec_driver_sql("PRAGMA table_info(message_relations_v3)").all()
        }
    assert {
        "source_author_id",
        "source_author_display_name",
        "target_author_id",
        "target_author_display_name",
    }.issubset(columns)


def test_rejected_relation_remains_in_history() -> None:
    service = _service()
    relation = service.record(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="general",
        discord_thread_id="",
        source_message_id="m1",
        relation_type="DEPICTS",
        target_ref_type="entity",
        target_ref="provisional-character",
        confidence=0.66,
        source="media_association",
        evidence_refs=("media:image-1",),
        status="unresolved",
    )
    rejected = service.reject(owner_id="owner-1", relation_id=relation.id)
    assert rejected.status == "rejected"
    history = service.history(
        owner_id="owner-1",
        source_message_id="m1",
        relation_type="DEPICTS",
    )
    assert len(history) == 1
    assert history[0].status == "rejected"
