"""Delivery receipts, not guessed recency or model text, establish response provenance."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from test_runtime_durability import repository

from echo_masque.character_turn_context_types import CharacterContextTraceView
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord
from echo_masque.persistence.room_repository import RoomRepository
from echo_masque.persistence.runtime_durability_models import RuntimeStepRecord
from echo_masque.room_routing import RoomScope
from echo_masque.room_sources import SourceMessage


def prepared(path: Path, *, source: str = "target-not-latest") -> tuple:
    db, runtime = repository(path)
    operation = runtime.claim_character_operation(
        owner_id="owner",
        connection_id="conn",
        guild_id="guild",
        channel_id="channel",
        thread_id="thread",
        source_message_id="request-not-source",
        deployment_id="ann",
    )
    _, step = runtime.prepare_character_step(
        operation_id=operation.operation_id, deployment_id="ann"
    )
    scope = RoomScope(
        owner_id="owner",
        connection_id="conn",
        guild_id="guild",
        channel_id="channel",
        thread_id="thread",
    )
    rooms = RoomRepository(db)
    rooms.set_access(scope, readable=True)
    if source:
        rooms.observe(
            scope,
            [
                SourceMessage(
                    message_id=source,
                    channel_id="channel",
                    thread_id="thread",
                    author_id="user",
                    text="Source",
                )
            ],
        )
    with db.session() as session:
        session.add(
            CharacterDeploymentRecord(
                id="ann",
                owner_id="owner",
                character_card_id="card",
                connection_id="conn",
                platform="discord",
                workspace_id="guild",
                channel_id="channel",
                thread_id="thread",
                channel_name="room",
                status="active",
            )
        )
        session.commit()
    focus = rooms.focus(scope, source) if source else None
    trace = CharacterContextTraceView(
        source_target_message_id=source,
        source_origin="direct",
        source_requester_id="user",
        source_snapshot_revision=focus.room_revision if focus else 0,
        source_revisions={s.message.message_id: s.revision for s in focus.sources} if focus else {},
        publication_checked_at=datetime.now(UTC),
    )
    runtime.complete_social_step_generation(
        step_id=step.step_id,
        response_json=json.dumps(
            {
                "action": "reply",
                "text": "A private draft until confirmed",
                "reply_to_message_id": "model-tried-other-source",
                "context_trace": trace.model_dump(mode="json"),
            }
        ),
        cursor_json='{"pending_turns":[]}',
        delivery_required=True,
    )
    runtime.claim_delivery(
        operation_id=operation.operation_id, step_id=step.step_id, claim_nonce="nonce"
    )
    scope = RoomScope(
        owner_id="owner",
        connection_id="conn",
        guild_id="guild",
        channel_id="channel",
        thread_id="thread",
    )
    return db, runtime, operation, step, scope


def test_ack_links_actual_source_atomically_and_survives_body_scrubbing(tmp_path: Path) -> None:
    db, runtime, op, step, scope = prepared(tmp_path / "links.db")
    room = RoomRepository(db)
    assert room.delivery_source(scope, "sent-1") is None
    runtime.acknowledge_character_delivery(
        operation_id=op.operation_id,
        step_id=step.step_id,
        claim_nonce="nonce",
        sent_message_ids=["sent-1", "sent-2"],
    )
    for mid in ("sent-1", "sent-2"):
        link = room.delivery_source(scope, mid)
        assert link.target_message_id == "target-not-latest"
        assert link.deployment_id == "ann"
        assert link.complete is True
        assert link.step_id == step.step_id
        # Shared-room evidence is available to another role owner, not another destination.
        assert (
            room.delivery_source(scope.model_copy(update={"owner_id": "another-owner"}), mid)
            is not None
        )
        for field in ("connection_id", "guild_id", "channel_id", "thread_id"):
            assert room.delivery_source(scope.model_copy(update={field: "other"}), mid) is None
    with db.session() as session:
        assert session.get(RuntimeStepRecord, step.step_id).response_json == "{}"
    # Retrying an ACK does not erase, reassign, or duplicate source evidence.
    runtime.acknowledge_character_delivery(
        operation_id=op.operation_id,
        step_id=step.step_id,
        claim_nonce="nonce",
        sent_message_ids=["sent-1", "sent-2"],
    )
    assert room.delivery_source(scope, "sent-1").target_message_id == "target-not-latest"


def test_confirmed_partial_chunks_not_promoted_to_completed_dialogue(tmp_path: Path) -> None:
    db, runtime, op, step, scope = prepared(tmp_path / "partial.db")
    runtime.mark_delivery_uncertain(
        operation_id=op.operation_id,
        step_id=step.step_id,
        claim_nonce="nonce",
        error="chunk-two-timeout",
        sent_message_ids=["sent-1"],
    )
    link = RoomRepository(db).delivery_source(scope, "sent-1")
    assert link.complete is False
    assert link.target_message_id == "target-not-latest"
    assert runtime.get_operation(op.operation_id).status == "uncertain"
    assert runtime.get_operation(op.operation_id).sources_json == "[]"
    runtime.mark_delivery_uncertain(
        operation_id=op.operation_id,
        step_id=step.step_id,
        claim_nonce="wrong",
        error="forged",
        sent_message_ids=["forged-id"],
    )
    assert RoomRepository(db).delivery_source(scope, "forged-id") is None


@pytest.mark.parametrize(
    "change",
    [{"deployment_id": "ning"}, {"cursor_json": '{"pending_turns":[{"deployment_id":"admin"}]}'}],
)
def test_ack_cannot_rewrite_persisted_participant_or_budget(tmp_path: Path, change: dict) -> None:
    db, runtime, op, step, scope = prepared(tmp_path / "cursor.db")
    args = dict(
        operation_id=op.operation_id,
        step_id=step.step_id,
        claim_nonce="nonce",
        cursor_json='{"pending_turns":[]}',
        sent_message_ids=["sent-1"],
        outgoing_text="reply",
        applied=False,
        deployment_id="ann",
    )
    args.update(change)
    with pytest.raises(ValueError, match="persisted generation cursor"):
        runtime.acknowledge_delivery(**args)
    assert RoomRepository(db).delivery_source(scope, "sent-1") is None
    with db.session() as session:
        assert session.get(RuntimeStepRecord, step.step_id).status == "delivery_claimed"


def test_empty_target_receipt_is_not_guessed_from_request_id(tmp_path: Path) -> None:
    db, runtime, op, step, scope = prepared(tmp_path / "legacy.db", source="")
    runtime.acknowledge_character_delivery(
        operation_id=op.operation_id,
        step_id=step.step_id,
        claim_nonce="nonce",
        sent_message_ids=["sent-1"],
    )
    assert RoomRepository(db).delivery_source(scope, "sent-1") is None
