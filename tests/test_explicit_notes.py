from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from echo_masque.api.connector_schemas import DiscordInboundMessage
from echo_masque.internal_context import InternalContextService
from echo_masque.notes import NoteAccessDenied, NoteConflict, NoteInput
from echo_masque.persistence import Database
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord
from echo_masque.persistence.deployment_repository import DeploymentRepository
from echo_masque.persistence.models import CharacterCardRecord, TargetRecord
from echo_masque.persistence.note_models import CharacterNoteRecord
from echo_masque.persistence.note_repository import CharacterNoteRepository
from echo_masque.persistence.room_repository import RoomRepository
from echo_masque.room_context import RoomContextService
from echo_masque.room_routing import RoomScope
from echo_masque.room_sources import SourceMessage
from echo_masque.tool_runtime import ToolExecutionContext

SCOPE = RoomScope(owner_id="owner", connection_id="connection", guild_id="guild", channel_id="room")


def note_environment(path: Path) -> tuple:
    db = Database(f"sqlite:///{path}")
    db.initialize()
    with db.session() as session:
        session.add(
            TargetRecord(id="target", name="test", target_kind="rule_based", config_json="{}")
        )
        session.flush()
        session.add_all(
            [
                CharacterCardRecord(
                    id="card", owner_id="owner", target_id="target", display_name="Ann"
                ),
                CharacterCardRecord(
                    id="other-card", owner_id="owner", target_id="target", display_name="Ning"
                ),
                CharacterCardRecord(
                    id="private-card",
                    owner_id="other-owner",
                    target_id="target",
                    display_name="Private",
                ),
                CharacterDeploymentRecord(
                    id="deployment",
                    owner_id="owner",
                    character_card_id="card",
                    connection_id="connection",
                    platform="discord",
                    workspace_id="guild",
                    channel_id="room",
                    channel_name="Room",
                    status="active",
                ),
            ]
        )
        session.commit()
    rooms = RoomRepository(db)
    rooms.set_access(SCOPE, readable=True)
    notes = CharacterNoteRepository(db)
    service = InternalContextService(notes, rooms, DeploymentRepository(db))
    return db, rooms, notes, service


@pytest.fixture
def env(tmp_path: Path) -> tuple:
    return note_environment(tmp_path / "notes.db")


def context(**updates: object) -> ToolExecutionContext:
    base = ToolExecutionContext(
        owner_id="owner",
        character_card_id="card",
        deployment_id="deployment",
        platform="discord",
        connection_id="connection",
        guild_id="guild",
        channel_id="room",
        initiator_user_id="alice",
    )
    return replace(base, **updates)


def message(id: str = "m1", **changes: object) -> SourceMessage:
    return SourceMessage.model_validate(
        dict(
            message_id=id,
            channel_id="room",
            author_id="alice",
            author_display_name="Alice",
            text="I prefer jasmine tea.",
            created_at=datetime.now(UTC),
            **changes,
        )
    )


def remember(rooms, notes, *, request_id="action-1", source_id="m1", text="I prefer jasmine tea."):
    if rooms.get(SCOPE, source_id) is None:
        rooms.observe(SCOPE, [message(source_id)])
    return notes.create(
        owner_id="owner",
        card_id="card",
        scope=SCOPE,
        actor_id="alice",
        source_message_id=source_id,
        request_id=request_id,
        payload=NoteInput(subject_ref="user:alice", text=text),
    )


def test_explicit_member_note_is_attributed_idempotent_and_never_extracts(env) -> None:
    _, rooms, notes, service = env
    rooms.observe(SCOPE, [message()])
    assert notes.list(owner_id="owner", card_id="card", scope=SCOPE) == ()
    note = remember(rooms, notes)
    assert remember(rooms, notes).id == note.id
    assert note.authored is False and note.subject_ref == "user:alice" and note.version == 1
    result = json.loads(service.memory_search({"query": "jasmine"}, context()))
    assert result["count"] == 1 and result["memories"][0]["source_message_ref"] == "m1"
    assert "trust" not in result["memories"][0]
    with pytest.raises(NoteConflict, match="request_reused"):
        remember(rooms, notes, text="jasmine tea")


@pytest.mark.parametrize(
    "change",
    [
        {"actor_id": "bob"},
        {"payload": NoteInput(subject_ref="user:bob", text="jasmine")},
        {"scope": SCOPE.model_copy(update={"owner_id": "other"})},
        {"source_message_id": "missing"},
        {"card_id": "private-card"},
    ],
)
def test_member_cannot_claim_others_facts_scope_or_authority(env, change) -> None:
    _, rooms, notes, _ = env
    rooms.observe(SCOPE, [message()])
    args = dict(
        owner_id="owner",
        card_id="card",
        scope=SCOPE,
        actor_id="alice",
        source_message_id="m1",
        request_id="action",
        payload=NoteInput(subject_ref="user:alice", text="jasmine"),
    )
    with pytest.raises(NoteAccessDenied):
        notes.create(**{**args, **change})
    assert notes.list(owner_id="owner", card_id="card", scope=SCOPE) == ()


def test_bot_guesses_and_model_paraphrases_are_not_member_notes(env) -> None:
    _, rooms, notes, _ = env
    bot = message().model_copy(update={"author_is_bot": True})
    rooms.observe(SCOPE, [bot])
    with pytest.raises(NoteAccessDenied):
        remember(rooms, notes)
    rooms.observe(SCOPE, [message("human")])
    with pytest.raises(NoteConflict, match="quote_explicit"):
        remember(rooms, notes, source_id="human", text="Alice trusts Ann completely.")


def test_note_correction_and_forget_use_versions_and_physical_deletion(env) -> None:
    db, rooms, notes, service = env
    note = remember(rooms, notes)
    rooms.observe(
        SCOPE, [message("correction").model_copy(update={"text": "I prefer coffee now."})]
    )
    updated = notes.change(
        owner_id="owner",
        card_id="card",
        note_id=note.id,
        expected_version=1,
        scope=SCOPE,
        actor_id="alice",
        source_message_id="correction",
        payload=NoteInput(subject_ref="user:alice", text="I prefer coffee now."),
    )
    assert updated.version == 2
    with pytest.raises(NoteConflict, match="version"):
        notes.change(
            owner_id="owner",
            card_id="card",
            note_id=note.id,
            expected_version=1,
            payload=None,
            scope=SCOPE,
            actor_id="alice",
        )
    notes.change(
        owner_id="owner",
        card_id="card",
        note_id=note.id,
        expected_version=2,
        payload=None,
        scope=SCOPE,
        actor_id="alice",
    )
    with db.session() as session:
        assert session.get(CharacterNoteRecord, note.id) is None
    assert json.loads(service.memory_search({"query": "coffee"}, context()))["count"] == 0
    # A delayed retry of the original accepted write must not resurrect forgotten content.
    with pytest.raises(NoteConflict, match="request_retired"):
        remember(rooms, notes)


def test_concurrent_note_updates_have_one_winner(env) -> None:
    _, rooms, notes, _ = env
    note = remember(rooms, notes)

    def update(index):
        try:
            return notes.change(
                owner_id="owner",
                card_id="card",
                note_id=note.id,
                expected_version=1,
                operator=True,
                payload=NoteInput(subject_ref="user:alice", text=f"explicit operator edit {index}"),
            )
        except NoteConflict:
            return None

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(update, range(4)))
    assert sum(result is not None for result in results) == 1


@pytest.mark.parametrize("edit", ["delete", "correction"])
def test_source_change_atomically_removes_derived_note(env, edit) -> None:
    db, rooms, notes, service = env
    note = remember(rooms, notes)
    old = rooms.get(SCOPE, "m1").message
    changed = (
        old.model_copy(update={"deleted": True, "text": ""})
        if edit == "delete"
        else old.model_copy(
            update={"text": "Wrong; coffee.", "edited_at": datetime.now(UTC) + timedelta(seconds=1)}
        )
    )
    rooms.observe(SCOPE, [changed])
    with db.session() as session:
        assert session.get(CharacterNoteRecord, note.id) is None
    assert json.loads(service.memory_search({"query": "jasmine"}, context()))["count"] == 0


def test_metadata_enrichment_does_not_invalidate_note(env) -> None:
    _, rooms, notes, _ = env
    note = remember(rooms, notes)
    rooms.observe(
        SCOPE,
        [rooms.get(SCOPE, "m1").message.model_copy(update={"author_display_name": "Alice 2"})],
    )
    assert notes.list(owner_id="owner", card_id="card", scope=SCOPE)[0].id == note.id


def test_authored_background_is_deliberate_and_not_mutable_by_member(env) -> None:
    _, _, notes, service = env
    note = notes.create(
        owner_id="owner",
        card_id="card",
        authored=True,
        payload=NoteInput(
            subject_ref="user:alice", kind="relationship", text="Keep feedback direct."
        ),
    )
    with pytest.raises(NoteAccessDenied):
        notes.change(
            owner_id="owner",
            card_id="card",
            note_id=note.id,
            expected_version=1,
            scope=SCOPE,
            actor_id="alice",
            payload=None,
        )
    assert json.loads(service.memory_search({"query": "feedback"}, context()))["count"] == 1
    assert notes.list(owner_id="owner", card_id="other-card", scope=SCOPE) == ()


@pytest.mark.parametrize(
    "field",
    [
        "owner_id",
        "character_card_id",
        "deployment_id",
        "connection_id",
        "guild_id",
        "channel_id",
        "thread_id",
    ],
)
def test_recall_never_uses_cross_scope_candidates(env, field) -> None:
    _, rooms, notes, service = env
    remember(rooms, notes)
    for tool in ("memory.search", "conversation.search"):
        result = json.loads(
            service.execute(tool, {"query": "jasmine"}, context(**{field: "other"}))
        )
        assert result["count"] == 0 and "jasmine" not in str(result)


def test_revocation_pause_and_stale_permission_block_recall(env) -> None:
    db, rooms, notes, service = env
    remember(rooms, notes)
    rooms.set_access(SCOPE, readable=False)
    assert json.loads(service.memory_search({"query": "jasmine"}, context()))["ok"] is False
    rooms.set_access(SCOPE, readable=True)
    with db.session() as session:
        deployment = session.get(CharacterDeploymentRecord, "deployment")
        deployment.status = "paused"
        session.commit()
    assert json.loads(service.conversation_search({"query": "jasmine"}, context()))["ok"] is False


def test_recall_rechecks_grant_after_search(env, monkeypatch) -> None:
    _, rooms, notes, service = env
    remember(rooms, notes)
    original = rooms.search

    def revoke(*args, **kwargs):
        result = original(*args, **kwargs)
        rooms.set_access(SCOPE, readable=False)
        return result

    monkeypatch.setattr(rooms, "search", revoke)
    result = service.conversation_search({"query": "jasmine"}, context())
    assert "jasmine" not in result and json.loads(result)["ok"] is False


def test_context_loads_only_anchor_participant_notes_without_automatic_recall(
    env, monkeypatch
) -> None:
    _, rooms, notes, service = env
    remember(rooms, notes)
    notes.create(
        owner_id="owner",
        card_id="card",
        authored=True,
        payload=NoteInput(subject_ref="user:bob", text="BOB_PRIVATE_PREFERENCE"),
    )
    monkeypatch.setattr(service, "memory_search", lambda *args: pytest.fail("eager recall"))
    payload = DiscordInboundMessage(
        connection_id="connection",
        deployment_id="deployment",
        guild_id="guild",
        channel_id="room",
        message_id="m1",
        author_id="alice",
        author_display_name="Alice",
        text="jasmine",
        mentioned_bot=True,
    )
    result = RoomContextService(rooms, notes=notes).build(
        SimpleNamespace(
            payload=payload,
            deployment=SimpleNamespace(id="deployment", owner_id="owner"),
            card=SimpleNamespace(id="card", display_name="Ann"),
        )
    )
    prompt = "\n".join(result.bundle.prompt_sections())
    assert "jasmine" in prompt and "BOB_PRIVATE" not in prompt


def test_note_contract_rejects_privilege_fields_and_empty_text() -> None:
    for value in (
        {"text": " "},
        {"text": "note", "tools": ["admin"]},
        {"text": "note", "subject_ref": "admin:alice"},
    ):
        with pytest.raises(ValidationError):
            NoteInput.model_validate(value)
