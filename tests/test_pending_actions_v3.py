from __future__ import annotations

from echo_masque.pending_actions_v3 import PendingActionService
from echo_masque.persistence.conversation_runtime_repository import ConversationRuntimeRepository
from echo_masque.persistence.database import Database


def _service() -> PendingActionService:
    database = Database("sqlite://")
    database.initialize()
    return PendingActionService(ConversationRuntimeRepository(database))


def _register(service: PendingActionService, *, tool_id: str = "image.generate"):
    return service.register(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="channel-1",
        discord_thread_id="",
        source_message_id="message-1",
        source_segment_id="segment-1",
        conversation_thread_id="thread-1",
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


def test_same_thread_continue_cue_does_not_need_topic_continuity() -> None:
    service = _service()
    action = _register(service)
    result = _resolve(
        service, current_message="continue that one", conversation_thread_id="thread-1"
    )
    assert result.action_id == action.id
    assert result.source == "same_thread"
    assert result.confidence == 0.9


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


def test_ambiguous_pending_actions_remain_unresolved_without_utility() -> None:
    service = _service()
    _register(service)
    _register(service, tool_id="scheduler.remind")
    result = _resolve(service, current_message="maybe try that again", conversation_thread_id="")
    assert result.action is None
    assert result.source == "none"
    assert result.reason == "ambiguous_pending_action"
