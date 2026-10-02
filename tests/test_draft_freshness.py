from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from echo_masque.api.connector_schemas import DiscordConnectorReplyView
from echo_masque.character_turn_context_types import CharacterContextTraceView
from echo_masque.domain import TargetResponse
from echo_masque.draft_freshness import assess_draft
from echo_masque.draft_runtime import DraftRuntime
from echo_masque.persistence import Database, DurableRuntimeRepository
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord
from echo_masque.persistence.room_repository import RoomRepository
from echo_masque.persistence.runtime_durability_models import RuntimeStepRecord
from echo_masque.room_routing import RoomScope
from echo_masque.room_sources import SourceMessage, SourceUnavailable

SCOPE = RoomScope(owner_id="owner", connection_id="connection", guild_id="guild", channel_id="room")
NOW = datetime.now(UTC)


def source(id: str = "m1", **changes: object) -> SourceMessage:
    return SourceMessage.model_validate(
        {
            "message_id": id,
            "channel_id": "room",
            "author_id": "alice",
            "author_display_name": "Alice",
            "text": "Ann, help me plan a game.",
            "created_at": NOW,
            **changes,
        }
    )


def trace_for(focus, **changes):
    return CharacterContextTraceView.model_validate(
        {
            "source_target_message_id": focus.target_message_id,
            "source_snapshot_revision": focus.room_revision,
            "source_fingerprint": focus.fingerprint,
            "source_revisions": {s.message.message_id: s.revision for s in focus.sources},
            "source_content_hashes": {
                s.message.message_id: s.message.draft_fingerprint() for s in focus.sources
            },
            "source_anchor_ids": list(focus.anchor_ids),
            "source_requester_id": "alice",
            "source_origin": "direct",
            **changes,
        }
    )


class FakeTarget:
    def __init__(self):
        self.calls = []
        self.answer = '{"action":"message","text":"The corrected draft."}'
        self.on_send = None

    async def send(self, message):
        self.calls.append(message)
        if self.on_send:
            await self.on_send()
        return TargetResponse(text=self.answer, input_tokens=10, output_tokens=5)


@pytest.fixture
def draft(tmp_path: Path):
    db = Database(f"sqlite:///{tmp_path / 'draft.db'}")
    db.initialize()
    rooms = RoomRepository(db)
    rooms.set_access(SCOPE, readable=True)
    rooms.observe(SCOPE, [source("ancestor"), source(reply_to_message_id="ancestor")])
    role = CharacterDeploymentRecord(
        id="ann",
        owner_id="owner",
        character_card_id="card",
        connection_id="connection",
        platform="discord",
        workspace_id="guild",
        channel_id="room",
        channel_name="Room",
        status="active",
    )
    with db.session() as session:
        session.add(role)
        session.commit()
    durable = DurableRuntimeRepository(db)
    op = durable.claim_character_operation(
        owner_id="owner",
        connection_id="connection",
        guild_id="guild",
        channel_id="room",
        thread_id="",
        source_message_id="m1",
        deployment_id="ann",
    )
    _, step = durable.prepare_character_step(operation_id=op.operation_id, deployment_id="ann")
    reply = DiscordConnectorReplyView(
        action="reply",
        reason="fixture",
        deployment_id="ann",
        text="The original draft.",
        input_tokens=20,
        output_tokens=6,
        context_trace=trace_for(rooms.focus(SCOPE, "m1")),
    )
    durable.complete_social_step_generation(
        step_id=step.step_id,
        response_json=reply.model_dump_json(),
        cursor_json='{"pending_turns":[]}',
        delivery_required=True,
    )
    target = FakeTarget()
    card = SimpleNamespace(
        id="card",
        target_id="target",
        display_name="Ann",
        subtitle="",
        subject_type="custom",
        persona_summary="Calm",
        traits_json="[]",
        expected_tone="brief",
        forbidden_behaviors_json="[]",
        memory_summary=None,
    )
    runtime = SimpleNamespace(
        repository=SimpleNamespace(
            get_character_card=lambda *args: card,
            get_target=lambda *args: SimpleNamespace(
                target_kind="stable", name="fixture", config_json="{}"
            ),
        ),
        _target=lambda **kwargs: target,
    )
    service = DraftRuntime(runtime, rooms, durable)
    return SimpleNamespace(
        db=db,
        rooms=rooms,
        durable=durable,
        role=role,
        operation=op,
        step=step,
        reply=reply,
        target=target,
        service=service,
    )


def preflight(draft, **changes):
    return asyncio.run(
        draft.service.preflight(
            **{
                "scope": SCOPE,
                "operation_id": draft.operation.operation_id,
                "step_id": draft.step.step_id,
                "deployment": draft.role,
                "writable": True,
                **changes,
            }
        )
    )


def edit(draft, text="Actually, tomorrow not today."):
    draft.rooms.observe(
        SCOPE,
        [source(text=text, reply_to_message_id="ancestor", edited_at=NOW + timedelta(seconds=1))],
    )


def test_no_change_and_unrelated_addition_need_no_model(draft):
    draft.rooms.observe(
        SCOPE,
        [source("lunch", author_id="bob", text="Lunch?", created_at=NOW + timedelta(seconds=1))],
    )
    result = preflight(draft)
    assert result.disposition == "keep"
    assert result.reply.text == "The original draft."
    assert result.reply.context_trace.publication_checked_at is not None
    assert not draft.target.calls
    assert preflight(draft).disposition == "keep"
    assert (
        draft.durable.claim_delivery(
            operation_id=draft.operation.operation_id,
            step_id=draft.step.step_id,
            claim_nonce="nonce",
        )[0]
        == "granted"
    )


def test_changed_source_refreshes_once_without_tool_or_original_prompt_replay(draft):
    edit(draft)
    result = preflight(draft)
    assert result.disposition == "refreshed"
    assert result.reply.text == "The corrected draft."
    assert result.reply.context_trace.source_refresh_count == 1
    assert result.reply.input_tokens == 30 and result.reply.output_tokens == 11
    assert len(draft.target.calls) == 1
    assert "Actually, tomorrow" in draft.target.calls[0]
    assert preflight(draft).disposition == "keep"
    draft.rooms.observe(
        SCOPE,
        [
            source(
                text="Actually, next week.",
                reply_to_message_id="ancestor",
                edited_at=NOW + timedelta(seconds=2),
            )
        ],
    )
    blocked = preflight(draft)
    assert blocked.disposition == "blocked"
    assert blocked.reason == "draft_obsolete_after_refresh"
    assert len(draft.target.calls) == 1
    assert draft.durable.get_operation(draft.operation.operation_id).last_error == blocked.reason


@pytest.mark.parametrize("kind", ["readonly", "removed", "ancestor_removed", "revoked_role"])
def test_revocation_and_removed_input_never_publish(draft, kind):
    changes = {}
    if kind == "readonly":
        changes["writable"] = False
    elif kind == "removed":
        draft.rooms.observe(SCOPE, [source(deleted=True, text="")])
    elif kind == "ancestor_removed":
        draft.rooms.observe(SCOPE, [source("ancestor", deleted=True, text="")])
    else:
        changes["deployment"] = None
    result = preflight(draft, **changes)
    assert result.disposition == "blocked"
    assert result.reply.action == "silent" and result.reply.text is None
    assert not draft.target.calls
    with draft.db.session() as session:
        step = session.get(RuntimeStepRecord, draft.step.step_id)
        assert step.status == "silent"
    assert draft.durable.get_operation(draft.operation.operation_id).sources_json == "[]"


def test_claim_cannot_skip_preflight_or_use_old_preflight(draft):
    args = dict(
        operation_id=draft.operation.operation_id, step_id=draft.step.step_id, claim_nonce="nonce"
    )
    with pytest.raises(ValueError, match="draft_preflight_required"):
        draft.durable.claim_delivery(**args)
    preflight(draft)
    edit(draft)
    with pytest.raises(ValueError, match="draft_preflight_required"):
        draft.durable.claim_delivery(**args)
    preflight(draft)
    with draft.db.session() as session:
        step = session.get(RuntimeStepRecord, draft.step.step_id)
        raw = json.loads(step.response_json)
        raw["context_trace"]["publication_checked_at"] = (
            datetime.now(UTC) - timedelta(seconds=30)
        ).isoformat()
        step.response_json = json.dumps(raw)
        session.commit()
    with pytest.raises(ValueError, match="draft_preflight_expired"):
        draft.durable.claim_delivery(**args)


def test_foreign_scope_cannot_mutate_or_read_draft(draft):
    for field in ("connection_id", "guild_id", "channel_id", "thread_id"):
        with pytest.raises(SourceUnavailable, match="draft_not_found"):
            preflight(draft, scope=SCOPE.model_copy(update={field: "foreign"}))
    assert preflight(draft).disposition == "keep"


def test_ignore_is_optional_not_a_direct_failure_disguised_as_silence(draft):
    edit(draft)
    draft.target.answer = '{"action":"ignore","text":""}'
    result = preflight(draft)
    assert result.disposition == "blocked"
    assert result.reason == "direct_draft_refresh_declined"


def test_mutation_during_refresh_and_parallel_preflight_do_not_repeat_work(draft):
    async def scenario():
        edit(draft)
        entered, release = asyncio.Event(), asyncio.Event()

        async def pause():
            entered.set()
            await release.wait()

        draft.target.on_send = pause
        kwargs = dict(
            scope=SCOPE,
            operation_id=draft.operation.operation_id,
            step_id=draft.step.step_id,
            deployment=draft.role,
            writable=True,
        )
        task = asyncio.create_task(draft.service.preflight(**kwargs))
        await entered.wait()
        concurrent = await draft.service.preflight(**kwargs)
        assert concurrent.disposition == "in_progress"
        draft.rooms.observe(
            SCOPE,
            [
                source(
                    text="A second correction",
                    reply_to_message_id="ancestor",
                    edited_at=NOW + timedelta(seconds=3),
                )
            ],
        )
        release.set()
        return await task

    result = asyncio.run(scenario())
    assert result.disposition == "blocked"
    assert len(draft.target.calls) == 1


def test_restart_during_refresh_does_not_resend_or_regenerate(draft):
    with draft.db.session() as session:
        session.get(RuntimeStepRecord, draft.step.step_id).status = "refreshing"
        session.commit()
    draft.durable.recover_interrupted()
    op = draft.durable.get_operation(draft.operation.operation_id)
    assert op.status == "failed"
    assert op.last_error == "process_restarted_during_draft_preflight"
    with pytest.raises(ValueError, match="failed"):
        draft.durable.prepare_character_step(operation_id=op.operation_id, deployment_id="ann")
    assert not draft.target.calls


def test_silence_deadline_and_missing_bindings_are_distinct(draft):
    focus = draft.rooms.focus(SCOPE, "m1")
    trace = draft.reply.context_trace
    assert assess_draft(trace, focus, writable=True, expired=True).action == "blocked"
    ambient = trace.model_copy(update={"source_origin": "ambient"})
    assert assess_draft(ambient, focus, writable=True, expired=True).action == "drop"
    assert (
        assess_draft(trace, replace(focus, target_message_id="wrong"), writable=True).action
        == "blocked"
    )
    draft.rooms.observe(
        SCOPE,
        [
            source(
                "correction", text="Actually, another day.", created_at=NOW + timedelta(seconds=1)
            )
        ],
    )
    latest = draft.rooms.focus(SCOPE, "m1")
    assert assess_draft(trace, latest, writable=True).action == "refresh"
    assert (
        assess_draft(
            trace.model_copy(update={"source_origin": "continuation"}), latest, writable=True
        ).reason
        == "human_priority_over_optional_continuation"
    )


def test_source_enrichment_does_not_spend_a_model_call(draft):
    draft.rooms.observe(
        SCOPE,
        [
            source(
                author_display_name="Alice renamed",
                reply_to_message_id="ancestor",
                edited_at=NOW + timedelta(seconds=1),
            )
        ],
    )
    current = draft.rooms.focus(SCOPE, "m1")
    assert assess_draft(draft.reply.context_trace, current, writable=True).action == "keep"


def test_media_replacement_is_a_material_source_change(draft):
    draft.rooms.observe(
        SCOPE,
        [
            source(
                reply_to_message_id="ancestor",
                has_unseen_media=True,
                media_fingerprint="new-attachment",
                edited_at=NOW + timedelta(seconds=1),
            )
        ],
    )
    current = draft.rooms.focus(SCOPE, "m1")
    assert assess_draft(draft.reply.context_trace, current, writable=True).action == "refresh"
