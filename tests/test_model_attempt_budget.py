import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select

from echo_masque.model_attempt_budget import ModelAttemptBudget, ModelAttemptBudgetExceeded
from echo_masque.persistence import Database
from echo_masque.persistence.room_models import ModelAttemptBucketRecord
from echo_masque.providers.attempts import reserve_model_attempt
from echo_masque.providers.base import ChatMessage
from echo_masque.providers.openai_compatible import OpenAICompatibleProvider
from echo_masque.room_routing import RoomScope

ROOM = RoomScope(owner_id="owner", connection_id="conn", guild_id="guild", channel_id="room")
NOW = datetime(2026, 10, 1, 8, tzinfo=UTC)


@pytest.fixture
def budget(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'budget.db'}")
    db.initialize()
    return ModelAttemptBudget(db)


def test_actual_attempts_count_and_cannot_spill_past_atomic_operation_limit(budget):
    def attempt(_):
        try:
            budget.reserve(ROOM, requester_id="alice", operation_id="op", now=NOW)
            return True
        except ModelAttemptBudgetExceeded:
            return False

    with ThreadPoolExecutor(max_workers=4) as pool:
        allowed = list(pool.map(attempt, range(32)))
    assert sum(allowed) == 24
    with budget.database.session() as session:
        assert sorted(session.scalars(select(ModelAttemptBucketRecord.used))) == [24, 24, 24]


def test_new_operation_or_owner_cannot_reset_member_and_room_caps(budget):
    for i in range(60):
        budget.reserve(ROOM, requester_id="alice", operation_id=f"alice-{i}", now=NOW)
    with pytest.raises(ModelAttemptBudgetExceeded):
        budget.reserve(
            ROOM.model_copy(update={"owner_id": "other-role-owner"}),
            requester_id="alice",
            operation_id="new",
            now=NOW,
        )
    for i in range(60):
        budget.reserve(ROOM, requester_id="bob", operation_id=f"bob-{i}", now=NOW)
    with pytest.raises(ModelAttemptBudgetExceeded):
        budget.reserve(ROOM, requester_id="carol", operation_id="new2", now=NOW)
    # A distinct destination remains independent, and denied transactions don't spend its budget.
    budget.reserve(
        ROOM.model_copy(update={"thread_id": "other"}),
        requester_id="alice",
        operation_id="new",
        now=NOW,
    )


def test_scope_is_reset_after_failure_and_retries_consume_real_http_attempts(budget):
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(503, json={"error": {"message": "temporary unavailable"}})
        return httpx.Response(
            200,
            json={
                "model": "fixture",
                "choices": [
                    {"message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}
                ],
            },
        )

    provider = OpenAICompatibleProvider(
        base_url="https://api.example.com/v1",
        api_key=SecretStr("test"),
        transport=httpx.MockTransport(handler),
        max_retries=1,
    )

    async def run():
        with budget.scope(ROOM, requester_id="alice", operation_id="op"):
            result = await provider.complete(
                messages=(ChatMessage(role="user", content="hi"),), model="fixture", temperature=0
            )
            assert result.text == "ok"

    asyncio.run(run())
    assert len(calls) == 2
    with budget.database.session() as session:
        assert list(session.scalars(select(ModelAttemptBucketRecord.used))) == [2, 2, 2]
    reserve_model_attempt()  # No leaked reservation outside the runtime scope.
    with budget.database.session() as session:
        assert list(session.scalars(select(ModelAttemptBucketRecord.used))) == [2, 2, 2]
