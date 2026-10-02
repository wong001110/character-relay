"""Runtime-owned bounds on actual HTTP model attempts, including retries and repairs.

This is an admission counter, not pricing, a provider pool, or an agent scheduler.
The call-site scope cannot be supplied by a model. Provider traces remain usage evidence.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from echo_masque.persistence.database import Database
from echo_masque.persistence.room_models import ModelAttemptBucketRecord
from echo_masque.providers.attempts import ModelAttemptBudgetExceeded, bind_attempt_reservation
from echo_masque.room_routing import RoomScope


def _key(*items: str) -> str:
    return hashlib.sha256("\x1f".join(items).encode()).hexdigest()


class ModelAttemptBudget:
    def __init__(self, database: Database) -> None:
        self.database = database

    def reserve(
        self,
        scope: RoomScope,
        *,
        requester_id: str,
        operation_id: str,
        now: datetime | None = None,
    ) -> None:
        now = now or datetime.now(UTC)
        room = _key(scope.connection_id, scope.guild_id, scope.channel_id, scope.thread_id)
        window = str(int(now.timestamp()) // 600)
        # Runtime-only initial ceilings, not measured optima. A source reset/new operation
        # cannot reset the fixed ten-minute room/member buckets. Empty identities fail closed.
        if not requester_id or not operation_id:
            raise ModelAttemptBudgetExceeded("model_attempt_identity_missing")
        entries = sorted(
            (
                ("room:" + _key(room, window), 120),
                ("member:" + _key(room, requester_id, window), 60),
                ("operation:" + _key(room, operation_id), 24),
            )
        )
        insert = pg_insert if self.database.engine.dialect.name == "postgresql" else sqlite_insert
        with self.database.session() as session:
            # Constant expiry on conflict: repeated requests cannot keep an exhausted window alive.
            for key, limit in entries:
                session.execute(
                    insert(ModelAttemptBucketRecord)
                    .values(id=key, used=0, expires_at=now + timedelta(days=1))
                    .on_conflict_do_nothing(index_elements=["id"])
                )
                result = session.scalar(
                    update(ModelAttemptBucketRecord)
                    .where(
                        ModelAttemptBucketRecord.id == key, ModelAttemptBucketRecord.used < limit
                    )
                    .values(used=ModelAttemptBucketRecord.used + 1)
                    .returning(ModelAttemptBucketRecord.id)
                )
                if result is None:
                    session.rollback()
                    raise ModelAttemptBudgetExceeded("room_model_attempt_budget_exhausted")
            session.execute(
                delete(ModelAttemptBucketRecord).where(ModelAttemptBucketRecord.expires_at < now)
            )
            session.commit()

    @contextmanager
    def scope(
        self,
        room: RoomScope,
        *,
        requester_id: str,
        operation_id: str,
    ) -> Iterator[None]:
        with bind_attempt_reservation(
            lambda: self.reserve(
                room,
                requester_id=requester_id,
                operation_id=operation_id,
            )
        ):
            yield
