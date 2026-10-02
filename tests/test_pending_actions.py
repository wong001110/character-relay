from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from echo_masque.pending_actions import PendingActionService
from echo_masque.persistence.database import Database
from echo_masque.persistence.pending_action_repository import PendingActionRepository


def _service() -> PendingActionService:
    database = Database("sqlite://")
    database.initialize()
    return PendingActionService(PendingActionRepository(database))


def _register(service: PendingActionService, *, tool_id: str = "image.generate"):
    return service.register(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="channel-1",
        source_message_id="message-1",
        discord_thread_id="thread-1",
        requested_by_user_id="user-1",
        target_character_card_id="card-ann",
        deployment_id="deployment-ann",
        tool_id=tool_id,
        intent_summary="generate the image",
    )


def _resolve(service: PendingActionService, **updates: str):
    values = {
        "owner_id": "owner-1",
        "connection_id": "connection-1",
        "guild_id": "guild-1",
        "current_message": "maybe try that again",
        "requested_by_user_id": "user-1",
        "target_character_card_id": "card-ann",
        "deployment_id": "deployment-ann",
        "channel_id": "channel-1",
        "discord_thread_id": "thread-1",
    }
    values.update(updates)
    return service.resolve_continuation(**values)


def test_explicit_reply_continues_exact_standalone_pending_action() -> None:
    service = _service()
    action = _register(service)
    result = _resolve(service, reply_to_message_id="message-1")
    assert result.action_id == action.id
    assert result.tool_id == "image.generate"
    assert result.source == "explicit_reply"
    assert result.reason == "reply_to_pending_action_source"


def test_unique_same_thread_resumes_without_current_keyword_or_reply() -> None:
    service = _service()
    action = _register(service)
    result = _resolve(service, current_message="go ahead", discord_thread_id="thread-1")
    assert result.action_id == action.id
    assert result.source == "same_native_thread"
    assert result.reason == "unique_native_thread_pending_action"


def test_reply_or_same_thread_without_a_clear_continuation_does_not_resume() -> None:
    service = _service()
    _register(service)

    reply = _resolve(
        service,
        current_message="What is everyone having for lunch?",
        reply_to_message_id="message-1",
    )
    same_thread = _resolve(
        service,
        current_message="What is everyone having for lunch?",
        discord_thread_id="thread-1",
    )

    assert reply.action is None
    assert same_thread.action is None
    assert reply.reason == same_thread.reason == "continuation_intent_required"
    assert reply.suppressed_tool_ids == same_thread.suppressed_tool_ids == ("image.generate",)


def test_channel_scope_cannot_resume_another_channel_pending_action() -> None:
    service = _service()
    _register(service)

    result = _resolve(
        service,
        current_message="go ahead",
        channel_id="channel-2",
        discord_thread_id="thread-1",
    )

    assert result.action is None
    assert result.reason == "no_active_action"


def test_explicit_reply_cancel_updates_only_the_linked_action() -> None:
    service = _service()
    action = _register(service)
    result = _resolve(service, current_message="cancel that", reply_to_message_id="message-1")
    assert result.action_id == action.id
    assert result.source == "cancelled"
    assert (
        service.repository.pending_action(owner_id="owner-1", action_id=action.id).state
        == "cancelled"
    )  # type: ignore[union-attr]


def test_in_progress_side_effect_is_not_resumed_after_an_uncertain_interruption() -> None:
    service = _service()
    action = _register(service)
    service.repository.update_pending_action_state(
        owner_id="owner-1",
        action_id=action.id,
        state="in_progress",
    )

    result = _resolve(service, reply_to_message_id="message-1", current_message="try again")

    assert result.action is None
    assert result.reason == "action_execution_uncertain"
    assert result.suppressed_tool_ids == ("image.generate",)


def test_atomic_claim_allows_only_one_concurrent_retry_to_force_execution(
    tmp_path: Path,
) -> None:
    database = Database(f"sqlite:///{tmp_path / 'pending-action-race.db'}")
    database.initialize()
    service = PendingActionService(PendingActionRepository(database))
    action = _register(service)

    def claim() -> object:
        return service.repository.claim_pending_action_for_execution(
            owner_id="owner-1",
            action_id=action.id,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        claims = list(executor.map(lambda _: claim(), range(2)))

    assert sum(item is not None for item in claims) == 1
    stored = service.repository.pending_action(owner_id="owner-1", action_id=action.id)
    assert stored is not None
    assert stored.state == "in_progress"


def test_replayed_source_registration_uses_the_same_deterministic_action_identity() -> None:
    service = _service()
    first = _register(service)
    replay = _register(service)

    assert replay.id == first.id


def test_ambiguous_pending_actions_remain_unresolved_without_utility() -> None:
    service = _service()
    _register(service)
    _register(service, tool_id="scheduler.remind")
    result = _resolve(service, current_message="maybe try that again")
    assert result.action is None
    assert result.source == "none"
    assert result.reason == "continuation_reply_required"


def test_expired_action_cannot_be_claimed_between_resolution_and_execution() -> None:
    from datetime import UTC, datetime, timedelta

    service = _service()
    action = _register(service)
    future = datetime.now(UTC) + timedelta(days=1)
    # Set an expiry on an isolated record, then exercise the atomic claim boundary.
    from echo_masque.persistence.pending_action_models import PendingActionRecord

    with service.repository.database.session() as session:
        record = session.get(PendingActionRecord, action.id)
        assert record is not None
        record.expires_at = future
        session.commit()
    assert (
        service.repository.claim_pending_action_for_execution(
            owner_id="owner-1", action_id=action.id, now=future + timedelta(seconds=1)
        )
        is None
    )


def test_terminal_action_is_not_revived_by_registration_or_invalid_state() -> None:
    import pytest

    service = _service()
    action = _register(service)
    service.repository.update_pending_action_state(
        owner_id="owner-1", action_id=action.id, state="completed"
    )
    assert _register(service).id == action.id
    assert (
        service.repository.update_pending_action_state(
            owner_id="owner-1", action_id=action.id, state="pending"
        )
        is None
    )
    with pytest.raises(ValueError, match="invalid_pending_action_state"):
        service.repository.update_pending_action_state(
            owner_id="owner-1", action_id=action.id, state="unknown"
        )
    assert (
        service.repository.pending_action(owner_id="owner-1", action_id=action.id).state
        == "completed"
    )


def test_pending_action_cannot_cross_any_scope_boundary() -> None:
    service = _service()
    _register(service)
    for field in (
        "owner_id",
        "connection_id",
        "guild_id",
        "channel_id",
        "discord_thread_id",
        "requested_by_user_id",
        "target_character_card_id",
        "deployment_id",
    ):
        result = _resolve(service, reply_to_message_id="message-1", **{field: "other"})
        assert result.action is None, field


def test_schema_has_no_dependency_on_semantic_memory() -> None:
    from echo_masque.persistence.pending_action_models import PendingActionRecord

    names = set(PendingActionRecord.__table__.columns.keys())
    assert "source_segment_id" not in names
    assert "conversation_thread_id" not in names
    assert not PendingActionRecord.__table__.foreign_keys
