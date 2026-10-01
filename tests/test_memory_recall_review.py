"""R4 replacements for the old Belief/Episode recall regression cases."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
import test_explicit_notes as note_tests

from echo_masque.notes import NoteInput

SCOPE = note_tests.SCOPE
context = note_tests.context
env = note_tests.env
message = note_tests.message



def test_memory_search_finds_old_note_beyond_recent_context_without_embeddings(env):
    _, _rooms, notes, service = env
    for index in range(160):
        notes.create(
            owner_id="owner",
            card_id="card",
            authored=True,
            payload=NoteInput(text=f"routine entry {index}"),
        )
    notes.create(
        owner_id="owner",
        card_id="card",
        authored=True,
        payload=NoteInput(text="The moonlit orchid is an explicit recall phrase."),
    )
    notes.create(
        owner_id="owner",
        card_id="other-card",
        authored=True,
        payload=NoteInput(text="moonlit orchid from another role"),
    )
    result = json.loads(service.memory_search({"query": "moonlit orchid"}, context()))
    assert result["count"] == 1
    assert result["memories"][0]["value"] == "The moonlit orchid is an explicit recall phrase."
    assert result["retrieval_backend"] == "sparse_v1"


def test_raw_history_recall_reaches_old_evidence_without_aggregate_thread_disclosure(env):
    _, rooms, _, service = env
    now = datetime.now(UTC)
    old = message("old").model_copy(
        update={"text": "Choose the moonlit orchid.", "created_at": now - timedelta(days=60)}
    )
    rooms.observe(SCOPE, [old])
    for start in range(0, 300, 60):
        rooms.observe(
            SCOPE,
            [
                message(f"recent-{i}").model_copy(update={"text": f"routine message {i}"})
                for i in range(start, start + 60)
            ],
        )
    private = SCOPE.model_copy(update={"thread_id": "private"})
    rooms.observe(
        private, [old.model_copy(update={"thread_id": "private", "text": "PRIVATE moonlit orchid"})]
    )
    result = json.loads(service.conversation_search({"query": "moonlit orchid"}, context()))
    assert [hit["ref"] for hit in result["results"]] == ["old"]
    assert result["results"][0]["kind"] == "raw_message"
    assert "PRIVATE" not in str(result)
    assert "old" not in rooms.focus(SCOPE, "recent-299").message_ids


def test_history_search_keeps_real_author_reply_and_edit_revision(env):
    _, rooms, _, service = env
    original = message("reply").model_copy(
        update={"text": "moonlit orchid", "reply_to_message_id": "missing-parent"}
    )
    rooms.observe(SCOPE, [original])
    rooms.observe(
        SCOPE,
        [
            original.model_copy(
                update={
                    "text": "moonlit orchid correction",
                    "edited_at": datetime.now(UTC) + timedelta(seconds=1),
                }
            )
        ],
    )
    result = json.loads(service.conversation_search({"query": "orchid"}, context()))["results"][0]
    assert result["revision"] == 2 and result["author_id"] == "alice"
    assert result["reply_to_message_ref"] == "missing-parent"
    assert result["source_message_refs"] == ["reply"]
    assert result["content"] == "moonlit orchid correction"


@pytest.mark.parametrize(
    "query", ["不存在的月餅", "nothing matching", "'; DROP TABLE room_sources; --"]
)
def test_no_match_does_not_fill_with_irrelevant_memory(env, query):
    _, rooms, _, service = env
    rooms.observe(SCOPE, [message()])
    assert json.loads(service.conversation_search({"query": query}, context()))["count"] == 0


def test_cjk_query_and_bounded_history_snippets(env):
    _, rooms, _, service = env
    rooms.observe(SCOPE, [message().model_copy(update={"text": "喜歡茉莉花茶。" * 500})])
    result = json.loads(service.conversation_search({"query": "茉莉花茶"}, context()))
    assert result["count"] == 1
    assert len(result["results"][0]["content"]) <= 1200
    assert result["results"][0]["content_truncated"] is True
