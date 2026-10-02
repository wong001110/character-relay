"""Replacement guarantees for retired automatic cognition/selection tests.

Optional speech, identity, recall isolation, edits, bot authority and media provenance
are exercised on the actual Room/Notes/Tool paths, not on removed simulators.
"""

from datetime import UTC, datetime
from importlib.util import find_spec

import pytest
from sqlalchemy import inspect, select

from echo_masque.account_lifecycle import LifecycleConflict
from echo_masque.persistence import Database
from echo_masque.persistence.chat_lifecycle_repository import ChatLifecycleRepository
from echo_masque.persistence.note_models import CharacterNoteRecord
from echo_masque.persistence.pending_action_models import PendingActionRecord
from echo_masque.persistence.room_models import RoomStateRecord
from echo_masque.persistence.room_repository import RoomRepository
from echo_masque.retired_chat_tables import RETIRED_CHAT_TABLES
from echo_masque.room_routing import RoomScope
from echo_masque.room_sources import SourceMessage


@pytest.fixture
def db():
    database = Database("sqlite://")
    database.initialize()
    yield database
    database.engine.dispose()


@pytest.mark.parametrize(
    "module",
    [
        "participation_planner_v3",
        "semantic_participation",
        "smart_participation",
        "conversation_structure_resolver",
        "context_resolver_v3",
        "current_turn_belief_v3",
        "social_intelligence_v3",
        "social_event_runtime",
        "knowledge_gap_discovery_v3",
        "deployment_activity_scheduler",
        "deployment_presence_scheduler",
        "discovery_runtime",
    ],
)
def test_retired_engines_are_not_importable(module):
    assert find_spec(f"echo_masque.{module}") is None


def test_fresh_schema_does_not_create_cognitive_graph_or_old_workflow_tables(db):
    assert not set(inspect(db.engine).get_table_names()).intersection(RETIRED_CHAT_TABLES)
    with db.engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1


def _seed(db, owner):
    scope = RoomScope(owner_id=owner, connection_id="conn", guild_id="guild", channel_id="room")
    RoomRepository(db).observe(
        scope,
        [
            SourceMessage(
                message_id="m1",
                channel_id="room",
                author_id="alice",
                text="Remember this explicit note.",
                created_at=datetime.now(UTC),
            )
        ],
    )
    with db.session() as session:
        session.add(
            CharacterNoteRecord(
                id=f"note-{owner}",
                owner_id=owner,
                character_card_id="card",
                scope_id="",
                scope_json="",
                subject_ref="character:card",
                kind="background",
                text=owner,
                authored=True,
                actor_id=owner,
            )
        )
        session.add(
            PendingActionRecord(
                id=f"action-{owner}",
                owner_id=owner,
                connection_id="conn",
                guild_id="guild",
                channel_id="room",
                source_message_id="m1",
                requested_by_user_id="alice",
                tool_id="test-tool",
                state="completed",
            )
        )
        session.commit()
    return scope


def test_account_chat_cleanup_preserves_other_owner_same_room_evidence_and_effects(db):
    own = _seed(db, "owner-a")
    other = _seed(db, "owner-b")
    counts = ChatLifecycleRepository(db).delete_owner("owner-a")
    assert counts["room_sources"] == counts["room_states"] == 1
    assert counts["character_notes"] == counts["pending_actions"] == 1
    assert RoomRepository(db).get(own, "m1") is None
    assert RoomRepository(db).get(other, "m1") is not None
    with db.session() as session:
        assert session.get(CharacterNoteRecord, "note-owner-b") is not None
        assert session.get(PendingActionRecord, "action-owner-b") is not None


def test_legacy_authoring_claim_does_not_reassign_scoped_conversations_or_effects(db):
    scope = _seed(db, "local-user")
    with pytest.raises(LifecycleConflict, match="Scoped chat state"):
        ChatLifecycleRepository(db).claim_authored_notes("local-user", "new-owner")
    assert RoomRepository(db).get(scope, "m1") is not None
    with db.session() as session:
        assert session.get(CharacterNoteRecord, "note-local-user").owner_id == "local-user"
        assert session.get(PendingActionRecord, "action-local-user").owner_id == "local-user"


def test_corrupt_owned_scope_cannot_cause_broad_cleanup(db):
    _seed(db, "owner-a")
    with db.session() as session:
        row = session.scalar(select(RoomStateRecord))
        row.id = "wrong-key"
        session.commit()
    with pytest.raises(LifecycleConflict, match="integrity"):
        ChatLifecycleRepository(db).delete_owner("owner-a")
    with db.session() as session:
        assert session.get(CharacterNoteRecord, "note-owner-a") is not None
