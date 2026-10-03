from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from echo_masque.api.connector_schemas import DiscordInboundMessage
from echo_masque.connector_runtime import DiscordConnectorRuntime
from echo_masque.persistence import Database
from echo_masque.persistence.room_repository import RoomRepository
from echo_masque.room_context import RoomContextService, bind_requester
from echo_masque.room_routing import RoomScope, SpeakerChoice
from echo_masque.room_sources import (
    SourceMention,
    SourceMessage,
    SourcePoll,
    SourcePollAnswer,
    SourceReaction,
    SourceUnavailable,
    scope_key,
)

NOW = datetime(2026, 10, 1, tzinfo=UTC)
SCOPE = RoomScope(owner_id="owner", connection_id="connection", guild_id="guild", channel_id="room")


@pytest.fixture
def rooms(tmp_path: Path) -> RoomRepository:
    db = Database(f"sqlite:///{tmp_path / 'rooms.db'}")
    db.initialize()
    return RoomRepository(db)


def message(message_id: str = "m1", **updates: object) -> SourceMessage:
    return SourceMessage.model_validate(
        {
            "message_id": message_id,
            "channel_id": "room",
            "author_id": "alice",
            "author_display_name": "Alice",
            "text": "Which game should we play?",
            "created_at": NOW,
            **updates,
        }
    )


def incoming(**updates: object) -> DiscordInboundMessage:
    return DiscordInboundMessage.model_validate(
        {
            "connection_id": "connection",
            "deployment_id": "ann",
            "message_id": "m1",
            "guild_id": "guild",
            "channel_id": "room",
            "author_id": "alice",
            "author_display_name": "Alice",
            "text": "Which game should we play?",
            "mentioned_bot": True,
            **updates,
        }
    )


def resolved(payload: DiscordInboundMessage) -> object:
    return SimpleNamespace(
        payload=payload,
        deployment=SimpleNamespace(id="ann", owner_id="owner"),
        card=SimpleNamespace(display_name="Ann", id="ann-card"),
    )


def test_sources_are_exact_room_and_author_scoped(rooms: RoomRepository) -> None:
    rooms.observe(SCOPE, [message()])
    for field in ("owner_id", "connection_id", "guild_id", "channel_id", "thread_id"):
        other = SCOPE.model_copy(update={field: "different"})
        assert rooms.get(other, "m1") is None
        with pytest.raises(SourceUnavailable):
            rooms.focus(other, "m1")
    with pytest.raises(ValueError, match="source_scope"):
        rooms.observe(SCOPE, [message(channel_id="private")])
    with pytest.raises(ValueError, match="source_author"):
        rooms.observe(SCOPE, [message(author_id="bob")])
    assert rooms.get(SCOPE, "m1").message.author_id == "alice"



def test_presentation_reactions_do_not_advance_agent_source_revision(
    rooms: RoomRepository,
) -> None:
    original = message()
    assert rooms.observe(SCOPE, [original]) == 1
    enriched = message(
        reactions=(
            SourceReaction(key="unicode:😂", name="😂", count=3),
        ),
        pinned=True,
    )
    assert rooms.observe(SCOPE, [enriched]) == 1
    stored = rooms.get(SCOPE, "m1")
    assert stored is not None
    assert stored.revision == 1
    assert stored.room_revision == 1
    assert stored.message.reactions[0].count == 3
    assert stored.message.pinned is True


def test_custom_emoji_and_mention_ids_stay_out_of_agent_model_text() -> None:
    source = message(
        text="hello <:wave:123456789> <a:dance:987654321> <@111> <#222>",
        mentions=(
            SourceMention(kind="user", target_id="111", label="Bob"),
            SourceMention(kind="channel", target_id="222", label="general"),
        ),
    )
    assert "<:wave:123456789>" in source.text
    assert source.model_text() == "hello :wave: :dance: @Bob #general"
    routed = source.routing_message(SCOPE, 1)
    assert routed.text == "hello :wave: :dance: @Bob #general"
    assert "123456789" not in routed.text
    assert "<@111>" not in routed.text


def test_poll_vote_counts_update_presentation_without_agent_revision(
    rooms: RoomRepository,
) -> None:
    first = message(
        text="",
        poll=SourcePoll(
            question="Tea?",
            answers=(
                SourcePollAnswer(answer_id=1, text="Yes", vote_count=1),
                SourcePollAnswer(answer_id=2, text="No", vote_count=0),
            ),
        ),
    )
    assert rooms.observe(SCOPE, [first]) == 1
    updated = first.model_copy(
        update={
            "poll": SourcePoll(
                question="Tea?",
                answers=(
                    SourcePollAnswer(answer_id=1, text="Yes", vote_count=4),
                    SourcePollAnswer(answer_id=2, text="No", vote_count=2),
                ),
            )
        }
    )
    assert rooms.observe(SCOPE, [updated]) == 1
    stored = rooms.get(SCOPE, "m1")
    assert stored is not None
    assert stored.revision == 1
    assert stored.message.poll is not None
    assert stored.message.poll.answers[0].vote_count == 4
    assert stored.message.model_text() == "[Poll] Tea? Options: Yes; No"



def test_scope_identity_is_not_colon_concatenation() -> None:
    a = SCOPE.model_copy(update={"connection_id": "c:g", "guild_id": "g"})
    b = SCOPE.model_copy(update={"connection_id": "c", "guild_id": "g:g"})
    assert scope_key(a) != scope_key(b)


def test_duplicate_events_and_old_enrichment_do_not_replace_edit(rooms: RoomRepository) -> None:
    original = message()
    assert rooms.observe(SCOPE, [original]) == 1
    assert rooms.observe(SCOPE, [original]) == 1
    edited = message(text="Correction: tomorrow, not today.", edited_at=NOW + timedelta(seconds=1))
    assert rooms.observe(SCOPE, [edited]) == 2
    rooms.observe(SCOPE, [original, message(text="stale capture")])
    actual = rooms.get(SCOPE, "m1")
    assert actual.revision == 2
    assert actual.message.text == edited.text


def test_equal_version_never_silently_changes_readable_text(rooms: RoomRepository) -> None:
    rooms.observe(SCOPE, [message()])
    rooms.observe(SCOPE, [message(text="contradictory same-version capture")])
    assert rooms.get(SCOPE, "m1").message.text == message().text


def test_delete_before_create_and_after_edit_are_sticky(rooms: RoomRepository) -> None:
    rooms.observe(SCOPE, [message("early", deleted=True, author_id="", text="")])
    rooms.observe(SCOPE, [message("early")])
    assert rooms.get(SCOPE, "early").message.deleted
    rooms.observe(SCOPE, [message()])
    rooms.observe(SCOPE, [message(deleted=True, text="")])
    rooms.observe(SCOPE, [message(text="late edit", edited_at=NOW + timedelta(days=1))])
    stored = rooms.get(SCOPE, "m1")
    assert stored.message.deleted and stored.message.text == ""
    with pytest.raises(SourceUnavailable, match="target_unavailable"):
        rooms.focus(SCOPE, "m1")


def test_character_enrichment_preserves_original_identity(rooms: RoomRepository) -> None:
    rooms.observe(SCOPE, [message(author_is_bot=True)])
    rooms.observe(SCOPE, [message(author_is_bot=True, author_deployment_id="ann")])
    rooms.observe(SCOPE, [message(author_is_bot=True)])
    assert rooms.get(SCOPE, "m1").message.author_deployment_id == "ann"
    with pytest.raises(ValueError, match="source_character"):
        rooms.observe(SCOPE, [message(author_is_bot=True, author_deployment_id="ning")])


def test_focus_prioritizes_primary_and_ancestors_over_recent_unrelated(
    rooms: RoomRepository,
) -> None:
    rooms.observe(
        SCOPE,
        [
            message("root"),
            message("answer", reply_to_message_id="root", created_at=NOW + timedelta(seconds=1)),
        ],
    )
    rooms.observe(
        SCOPE,
        [
            message(f"recent-{i}", text="UNRELATED", created_at=NOW + timedelta(seconds=i + 2))
            for i in range(30)
        ],
    )
    focus = rooms.focus(SCOPE, "answer")
    assert focus.target_message_id == "answer"
    assert focus.anchor_ids == ("answer", "root")
    assert {"answer", "root"}.issubset(focus.message_ids)
    assert len(focus.sources) <= 21
    assert sum(len(source.message.text) for source in focus.sources) <= 24000


def test_missing_parent_is_not_replaced_with_another_room_source(rooms: RoomRepository) -> None:
    rooms.observe(SCOPE, [message(reply_to_message_id="secret")])
    private = SCOPE.model_copy(update={"thread_id": "private"})
    rooms.observe(private, [message("secret", thread_id="private", text="PRIVATE_SECRET")])
    focus = rooms.focus(SCOPE, "m1")
    assert focus.missing_ancestor_ids == ("secret",)
    assert "PRIVATE_SECRET" not in repr(focus)


def test_reply_cycle_and_context_size_are_bounded(rooms: RoomRepository) -> None:
    rooms.observe(
        SCOPE,
        [
            message("a", reply_to_message_id="b", text="x" * 10000),
            message("b", reply_to_message_id="a", text="y" * 10000),
            message("c", text="z" * 10000),
        ],
    )
    focus = rooms.focus(SCOPE, "a")
    assert focus.anchor_ids == ("a", "b")
    assert len(focus.sources) == 2
    with pytest.raises(ValueError):
        rooms.focus(SCOPE, "a", recent_limit=100000)


def test_revoked_room_cannot_rehydrate_until_adapter_rechecks_access(rooms: RoomRepository) -> None:
    rooms.observe(SCOPE, [message()])
    rooms.set_access(SCOPE, readable=False)
    assert rooms.get(SCOPE, "m1") is None
    assert rooms.recent(SCOPE) == ()
    with pytest.raises(SourceUnavailable):
        rooms.observe(SCOPE, [message("m2")])
    rooms.set_access(SCOPE, readable=True)
    assert rooms.get(SCOPE, "m1") is not None


def test_concurrent_sources_preserve_room_revision(rooms: RoomRepository) -> None:
    other_repository = RoomRepository(rooms.database)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(
            pool.map(
                lambda index: (rooms if index % 2 else other_repository).observe(
                    SCOPE, [message(str(index))]
                ),
                range(20),
            )
        )
    assert max(source.room_revision for source in rooms.recent(SCOPE)) == 20


def test_context_action_actor_is_not_source_author_or_caller_hint(rooms: RoomRepository) -> None:
    rooms.observe(SCOPE, [message()])
    selection = rooms.select(
        SCOPE,
        request_id="interaction-1",
        trigger_message_id="m1",
        requester_id="bob",
        requester_is_bot=False,
        choice=SpeakerChoice(speaker="ann", target_message_id="m1", mode="direct_answer"),
        origin="context_action",
    )
    payload = incoming(
        source_selection_id=selection.id,
        runtime_requester_id="admin",
        runtime_request_id="forged",
        runtime_requester_is_bot=True,
    )
    result = RoomContextService(rooms).build(resolved(payload))
    assert result.payload.author_id == "alice"
    assert result.payload.runtime_requester_id == "bob"
    assert result.payload.runtime_request_id == "interaction-1"
    assert not result.payload.runtime_requester_is_bot
    assert result.bundle.focus.target_message_id == "m1"
    assert result.turn_context.trace.rag_reason == "recall_on_demand"


def test_selection_cannot_transfer_role_room_or_trigger(rooms: RoomRepository) -> None:
    rooms.observe(SCOPE, [message()])
    selection = rooms.select(
        SCOPE,
        request_id="r",
        trigger_message_id="m1",
        requester_id="alice",
        requester_is_bot=False,
        choice=SpeakerChoice(speaker="ann", target_message_id="m1", mode="direct_answer"),
        origin="direct",
    )
    with pytest.raises(SourceUnavailable):
        rooms.selection(SCOPE, selection.id, "ning")
    with pytest.raises(SourceUnavailable):
        rooms.selection(SCOPE.model_copy(update={"owner_id": "else"}), selection.id, "ann")
    with pytest.raises(SourceUnavailable, match="trigger_mismatch"):
        bind_requester(
            incoming(message_id="other", source_selection_id=selection.id),
            SimpleNamespace(id="ann", owner_id="owner"),
            rooms,
        )


def test_deleted_selected_source_fails_without_room_fallback(rooms: RoomRepository) -> None:
    rooms.observe(SCOPE, [message(), message("unrelated", text="NOT_MY_ANSWER")])
    selection = rooms.select(
        SCOPE,
        request_id="r",
        trigger_message_id="m1",
        requester_id="alice",
        requester_is_bot=False,
        choice=SpeakerChoice(speaker="ann", target_message_id="m1", mode="direct_answer"),
        origin="direct",
    )
    rooms.observe(SCOPE, [message(deleted=True, text="")])
    result = RoomContextService(rooms).build(resolved(incoming(source_selection_id=selection.id)))
    assert result.error_reason == "target_unavailable"
    assert result.bundle.focus is None
    assert result.bundle.prompt_sections() == ()


def test_unscoped_history_is_not_relabelled_into_current_room(rooms: RoomRepository) -> None:
    payload = incoming(
        recent_messages=[
            {
                "message_id": "secret",
                "author_id": "bob",
                "author_display_name": "Bob",
                "text": "PRIVATE_SECRET",
            }
        ]
    )
    result = RoomContextService(rooms).build(resolved(payload))
    assert not result.error_reason
    assert result.bundle.focused_message_ids == ("m1",)
    assert "PRIVATE_SECRET" not in result.payload.model_dump_json()


def test_selected_older_source_stays_primary_in_actual_prompt(rooms: RoomRepository) -> None:
    rooms.observe(
        SCOPE,
        [
            message("game", text="GAME_QUESTION"),
            message(
                "lunch",
                author_id="bob",
                text="LUNCH_QUESTION",
                created_at=NOW + timedelta(seconds=2),
            ),
        ],
    )
    selection = rooms.select(
        SCOPE,
        request_id="lunch",
        trigger_message_id="lunch",
        requester_id="bob",
        requester_is_bot=False,
        choice=SpeakerChoice(speaker="ann", target_message_id="game", mode="supplement"),
        origin="ambient",
    )
    result = RoomContextService(rooms).build(
        resolved(
            incoming(
                message_id="lunch",
                author_id="bob",
                text="LUNCH_QUESTION",
                source_selection_id=selection.id,
            )
        )
    )
    prompt = DiscordConnectorRuntime._social_prompt_with_manifest(
        character_name="Ann",
        payload=result.payload,
        smart_context=result.turn_context.smart_output,
        focused_message_ids=result.bundle.focused_message_ids,
        context_sections=result.bundle.prompt_sections(),
    )
    primary = next(line for line in prompt.text.splitlines() if "[PRIMARY REPLY TARGET]" in line)
    assert "GAME_QUESTION" in primary and "LUNCH_QUESTION" not in primary
    assert "THREAD WORKING" not in prompt.text and "DIRECTOR BRIEF" not in prompt.text


def test_source_contract_rejects_unavailable_prose_and_naive_time() -> None:
    for values in (
        {"content_available": False},
        {"deleted": True},
        {"created_at": datetime(2026, 10, 1)},
        {"author_deployment_id": "ann"},
    ):
        with pytest.raises(ValidationError):
            message(**values)


def test_response_source_link_is_followed_without_native_discord_reply(tmp_path: Path) -> None:
    from echo_masque.persistence.database import Database
    from echo_masque.persistence.room_repository import RoomRepository
    from echo_masque.room_routing import RoomScope
    from echo_masque.room_sources import SourceMessage

    db = Database(f"sqlite:///{tmp_path / 'webhook.db'}")
    db.initialize()
    room = RoomRepository(db)
    scope = RoomScope(
        owner_id="owner", connection_id="conn", guild_id="guild", channel_id="channel"
    )
    room.observe(
        scope,
        [
            SourceMessage(
                message_id="question",
                channel_id="channel",
                author_id="alice",
                text="Explain recursion",
            ),
            SourceMessage(
                message_id="webhook",
                channel_id="channel",
                author_id="webhook-id",
                author_is_bot=True,
                author_deployment_id="ann",
                text="A function calls itself",
                response_to_message_id="question",
                response_delivery_complete=True,
            ),
            SourceMessage(
                message_id="followup",
                channel_id="channel",
                author_id="alice",
                text="An example?",
                reply_to_message_id="webhook",
            ),
        ],
    )
    focus = room.focus(scope, "followup", recent_limit=0)
    assert focus.anchor_ids == ("followup", "webhook", "question")
    assert focus.missing_ancestor_ids == ()
