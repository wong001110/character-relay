"""Persistence authority for bounded asynchronous Discord turn jobs."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import cast

from sqlalchemy import and_, delete, or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from echo_masque.persistence.database import Database
from echo_masque.persistence.runtime_durability_models import (
    RuntimeOperationRecord,
    RuntimeStepRecord,
)
from echo_masque.persistence.turn_job_models import TurnJobProgressRecord, TurnJobRecord

TERMINAL = frozenset({"succeeded", "failed", "timed_out", "stopped", "cancelled"})


def _rowcount(result: object) -> int:
    return int(cast(CursorResult[object], result).rowcount or 0)


def _is_due(deadline: datetime, now: datetime) -> bool:
    """SQLite returns naive datetimes even for timezone-aware mapped columns."""
    if deadline.tzinfo is None:
        now = now.replace(tzinfo=None)
    return deadline <= now


class TurnJobRepository:
    def __init__(self, database: Database, *, retention_hours: int = 24) -> None:
        self.database = database
        self.retention_hours = max(1, min(retention_hours, 168))

    @staticmethod
    def job_id(*, kind: str, connection_id: str, deployment_id: str, message_id: str) -> str:
        raw = "\x1f".join(("discord-turn-job-v1", kind, connection_id, deployment_id, message_id))
        return hashlib.sha256(raw.encode()).hexdigest()

    def submit(
        self,
        *,
        kind: str,
        owner_id: str,
        connection_id: str,
        deployment_id: str,
        guild_id: str,
        channel_id: str,
        message_id: str,
        request_json: str,
        deadline_seconds: int,
        source_author_id: str = "",
        thread_id: str = "",
        category_id: str = "",
    ) -> tuple[TurnJobRecord, bool]:
        identifier = self.job_id(
            kind=kind,
            connection_id=connection_id,
            deployment_id=deployment_id,
            message_id=message_id,
        )
        now = datetime.now(UTC)
        record = TurnJobRecord(
            job_id=identifier,
            kind=kind,
            owner_id=owner_id,
            connection_id=connection_id,
            deployment_id=deployment_id,
            guild_id=guild_id,
            channel_id=channel_id,
            thread_id=thread_id,
            category_id=category_id,
            source_message_id=message_id,
            source_author_id=source_author_id,
            request_json=request_json,
            status="queued",
            deadline_at=now + timedelta(seconds=deadline_seconds),
            expires_at=now + timedelta(hours=self.retention_hours),
            created_at=now,
            updated_at=now,
        )
        with self.database.session() as session:
            session.add(record)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                existing = session.get(TurnJobRecord, identifier)
                if existing is None:
                    raise
                return existing, False
            session.refresh(record)
            return record, True

    def get(self, job_id: str, *, connection_id: str) -> TurnJobRecord | None:
        with self.database.session() as session:
            record = session.get(TurnJobRecord, job_id)
            if record is None or record.connection_id != connection_id:
                return None
            expired_retention = _is_due(record.expires_at, datetime.now(UTC))
            expired = record.status in {"queued", "running"} and _is_due(
                record.deadline_at, datetime.now(UTC)
            )
        if expired_retention:
            self.cleanup()
            return None
        if expired:
            self.fail(job_id, status="timed_out", error_code="deadline_exceeded")
            with self.database.session() as session:
                return session.get(TurnJobRecord, job_id)
        return record

    def mark_running(self, job_id: str) -> TurnJobRecord | None:
        now = datetime.now(UTC)
        with self.database.session() as session:
            record = session.get(TurnJobRecord, job_id)
            if record is None or record.status != "queued":
                return None
            if _is_due(record.deadline_at, now):
                result = session.execute(
                    update(TurnJobRecord)
                    .where(TurnJobRecord.job_id == job_id, TurnJobRecord.status == "queued")
                    .values(
                        status="timed_out",
                        error_code="deadline_exceeded",
                        completed_at=now,
                        updated_at=now,
                    )
                )
                if _rowcount(result) != 1:
                    return None
            else:
                result = session.execute(
                    update(TurnJobRecord)
                    .where(TurnJobRecord.job_id == job_id, TurnJobRecord.status == "queued")
                    .values(status="running", updated_at=now)
                )
                if _rowcount(result) != 1:
                    return None
            session.commit()
            session.expire_all()
            record = session.get(TurnJobRecord, job_id)
            return record

    def complete(self, job_id: str, *, field: str, value: str) -> None:
        now = datetime.now(UTC)
        with self.database.session() as session:
            record = session.get(TurnJobRecord, job_id)
            if record is None or record.status != "running":
                return
            if _is_due(record.deadline_at, now):
                session.rollback()
                self.fail(job_id, status="timed_out", error_code="deadline_exceeded")
                return
            values: dict[str, object] = {
                "request_json": "{}",
                "status": "succeeded",
                "completed_at": now,
                "updated_at": now,
            }
            values["reply_json" if field == "reply" else "social_step_json"] = value
            response = json.loads(value)
            step_id = response.get("step_id", "") if isinstance(response, dict) else ""
            values["runtime_step_id"] = step_id if isinstance(step_id, str) else ""
            transitioned = session.execute(
                update(TurnJobRecord)
                .where(TurnJobRecord.job_id == job_id, TurnJobRecord.status == "running")
                .values(**values)
            )
            if _rowcount(transitioned) != 1:
                return
            session.commit()

    def is_running(self, job_id: str) -> bool:
        """A cheap durable gate for progress and publication callbacks."""
        with self.database.session() as session:
            return bool(
                session.scalar(
                    select(TurnJobRecord.job_id).where(
                        TurnJobRecord.job_id == job_id,
                        TurnJobRecord.status == "running",
                        TurnJobRecord.deadline_at > datetime.now(UTC),
                    )
                )
            )

    def cancel(
        self,
        job_id: str,
        *,
        owner_id: str,
        connection_id: str,
        reason: str,
    ) -> bool:
        """Terminalize a scoped job without replaying or undoing external effects."""
        with self.database.session() as session:
            record = session.get(TurnJobRecord, job_id)
            if (
                record is None
                or record.owner_id != owner_id
                or record.connection_id != connection_id
                or record.status in TERMINAL
            ):
                return False
        return self.fail(job_id, status="cancelled", error_code=reason)

    def cancel_matching_request(
        self,
        *,
        owner_id: str,
        connection_id: str,
        deployment_id: str,
        guild_id: str,
        channel_id: str,
        thread_id: str,
        category_id: str,
        source_message_id: str,
        source_author_id: str,
        reason: str,
    ) -> list[str]:
        """Cancel only the named author's active request at its exact deployment destination.

        A completed job is still cancellable only while its durable Runtime step remains
        ``generated``.  That compare-and-set wins or loses against the Connector's final
        delivery claim, so cancellation never pretends to undo a claimed Discord send.
        """
        with self.database.session() as session:
            records = list(
                session.scalars(
                    select(TurnJobRecord).where(
                        TurnJobRecord.owner_id == owner_id,
                        TurnJobRecord.connection_id == connection_id,
                        TurnJobRecord.deployment_id == deployment_id,
                        TurnJobRecord.guild_id == guild_id,
                        TurnJobRecord.channel_id == channel_id,
                        TurnJobRecord.thread_id == thread_id,
                        TurnJobRecord.category_id == category_id,
                        TurnJobRecord.source_message_id == source_message_id,
                        TurnJobRecord.source_author_id == source_author_id,
                        TurnJobRecord.status.in_(("queued", "running", "succeeded")),
                    )
                )
            )
        cancelled: list[str] = []
        for record in records:
            if record.status in {"queued", "running"}:
                if self.cancel(
                    record.job_id,
                    owner_id=owner_id,
                    connection_id=connection_id,
                    reason=reason,
                ):
                    cancelled.append(record.job_id)
                    continue
                # Generation can complete between the candidate query and the
                # active-job transition.  Re-read it so cancellation still gets
                # the generated-before-delivery compare-and-set opportunity.
                with self.database.session() as session:
                    completed = session.get(TurnJobRecord, record.job_id)
                if (
                    completed is not None
                    and completed.status == "succeeded"
                    and self._cancel_generated_delivery(completed, reason=reason)
                ):
                    cancelled.append(record.job_id)
            elif self._cancel_generated_delivery(record, reason=reason):
                cancelled.append(record.job_id)
        return cancelled

    def _cancel_generated_delivery(self, record: TurnJobRecord, *, reason: str) -> bool:
        """Atomically remove a generated final before the Connector can claim it."""
        if not record.runtime_step_id:
            return False
        now = datetime.now(UTC)
        with self.database.session() as session:
            step = session.get(RuntimeStepRecord, record.runtime_step_id)
            if step is None or step.deployment_id != record.deployment_id:
                return False
            operation = session.get(RuntimeOperationRecord, step.operation_id)
            if operation is None or operation not in self._runtime_operations(session, record):
                return False
            step_transitioned = session.execute(
                update(RuntimeStepRecord)
                .where(
                    RuntimeStepRecord.step_id == step.step_id,
                    RuntimeStepRecord.status == "generated",
                )
                .values(
                    status="failed",
                    response_json="{}",
                    last_error="turn_job_cancelled_before_delivery",
                    updated_at=now,
                )
            )
            if _rowcount(step_transitioned) != 1:
                return False
            job_transitioned = session.execute(
                update(TurnJobRecord)
                .where(
                    TurnJobRecord.job_id == record.job_id,
                    TurnJobRecord.status == "succeeded",
                )
                .values(
                    request_json="{}",
                    reply_json="",
                    social_step_json="",
                    status="cancelled",
                    error_code=reason[:80],
                    completed_at=now,
                    updated_at=now,
                )
            )
            if _rowcount(job_transitioned) != 1:
                session.rollback()
                return False
            operation.status = "failed"
            operation.last_error = "turn_job_cancelled_before_delivery"
            operation.updated_at = now
            session.commit()
            return True

    def fail(self, job_id: str, *, status: str, error_code: str) -> bool:
        now = datetime.now(UTC)
        with self.database.session() as session:
            record = session.get(TurnJobRecord, job_id)
            if record is None or record.status in TERMINAL:
                return False
            transitioned = session.execute(
                update(TurnJobRecord)
                .where(
                    TurnJobRecord.job_id == job_id,
                    TurnJobRecord.status.in_(("queued", "running")),
                )
                .values(
                    request_json="{}",
                    status=status,
                    error_code=error_code[:80],
                    completed_at=now,
                    updated_at=now,
                )
            )
            if _rowcount(transitioned) != 1:
                return False
            if status in {"timed_out", "stopped", "cancelled"}:
                operations = self._runtime_operations(session, record)
                for operation in operations:
                    operation.status = "uncertain"
                    operation.last_error = "turn_job_interrupted"
                    for step in session.scalars(
                        select(RuntimeStepRecord).where(
                            RuntimeStepRecord.operation_id == operation.operation_id,
                            RuntimeStepRecord.status == "generating",
                        )
                    ):
                        step.status = "uncertain"
                        step.last_error = "turn_job_interrupted"
            session.commit()
            return True

    def publish_progress(self, job_id: str, text: str) -> bool:
        normalized = " ".join(text.split())[:500]
        if not normalized:
            return False
        with self.database.session() as session:
            job = session.get(TurnJobRecord, job_id)
            if job is None or job.status not in {"queued", "running"}:
                return False
            count = len(
                list(
                    session.scalars(
                        select(TurnJobProgressRecord.id).where(
                            TurnJobProgressRecord.job_id == job_id
                        )
                    )
                )
            )
            if count >= 3:
                return False
            session.add(TurnJobProgressRecord(job_id=job_id, ordinal=count, text=normalized))
            session.commit()
            return True

    def list_progress(self, job_id: str) -> list[TurnJobProgressRecord]:
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(TurnJobProgressRecord)
                    .where(TurnJobProgressRecord.job_id == job_id)
                    .order_by(TurnJobProgressRecord.ordinal)
                )
            )

    def claim_progress(self, job_id: str, *, nonce: str) -> TurnJobProgressRecord | None:
        if not nonce or len(nonce) > 64:
            return None
        with self.database.session() as session:
            job = session.get(TurnJobRecord, job_id)
            if job is None or job.status not in {"queued", "running", "succeeded"}:
                return None
            records = list(
                session.scalars(
                    select(TurnJobProgressRecord)
                    .where(TurnJobProgressRecord.job_id == job_id)
                    .order_by(TurnJobProgressRecord.ordinal)
                )
            )
            for record in records:
                if record.acknowledged_at is not None:
                    continue
                if record.claim_nonce == nonce:
                    return record
                if record.claim_nonce:
                    return None  # uncertain external delivery is never replayed under a new claim
                claimed = session.execute(
                    update(TurnJobProgressRecord)
                    .where(
                        TurnJobProgressRecord.id == record.id,
                        TurnJobProgressRecord.claim_nonce == "",
                        TurnJobProgressRecord.acknowledged_at.is_(None),
                    )
                    .values(claim_nonce=nonce)
                )
                if _rowcount(claimed) != 1:
                    return None
                session.commit()
                session.refresh(record)
                return record
            return None

    def acknowledge_progress(self, job_id: str, progress_id: int, *, nonce: str) -> bool:
        with self.database.session() as session:
            record = session.get(TurnJobProgressRecord, progress_id)
            if (
                record is None
                or record.job_id != job_id
                or not nonce
                or record.claim_nonce != nonce
            ):
                return False
            if record.acknowledged_at is None:
                record.acknowledged_at = datetime.now(UTC)
                session.commit()
            return True

    def stop_jobs(self, job_ids: set[str]) -> None:
        for job_id in job_ids:
            self.fail(job_id, status="stopped", error_code="service_stopped")

    def expire_deadlines(self) -> int:
        with self.database.session() as session:
            identifiers = list(
                session.scalars(
                    select(TurnJobRecord.job_id).where(
                        TurnJobRecord.status.in_(("queued", "running")),
                        TurnJobRecord.deadline_at < datetime.now(UTC),
                    )
                )
            )
        for job_id in identifiers:
            self.fail(job_id, status="timed_out", error_code="deadline_exceeded")
        return len(identifiers)

    @staticmethod
    def _runtime_operations(
        session: Session, record: TurnJobRecord
    ) -> list[RuntimeOperationRecord]:
        candidates = list(
            session.scalars(
                select(RuntimeOperationRecord).where(
                    RuntimeOperationRecord.connection_id == record.connection_id,
                    RuntimeOperationRecord.owner_id == record.owner_id,
                    RuntimeOperationRecord.source_message_id == record.source_message_id,
                    RuntimeOperationRecord.guild_id == record.guild_id,
                    RuntimeOperationRecord.channel_id == record.channel_id,
                    RuntimeOperationRecord.thread_id == record.thread_id,
                    RuntimeOperationRecord.status.in_(("active", "awaiting_delivery")),
                )
            )
        )
        selected: list[RuntimeOperationRecord] = []
        for operation in candidates:
            try:
                deployment_ids = json.loads(operation.initial_deployment_ids_json)
            except json.JSONDecodeError:
                continue
            if isinstance(deployment_ids, list) and record.deployment_id in deployment_ids:
                selected.append(operation)
        return selected

    def cleanup(self) -> int:
        with self.database.session() as session:
            expired = list(
                session.scalars(
                    select(TurnJobRecord.job_id).where(TurnJobRecord.expires_at < datetime.now(UTC))
                )
            )
            if not expired:
                return 0
            session.execute(
                delete(TurnJobProgressRecord).where(TurnJobProgressRecord.job_id.in_(expired))
            )
            result = session.execute(delete(TurnJobRecord).where(TurnJobRecord.job_id.in_(expired)))
            session.commit()
            return _rowcount(result)

    def delete_owner(self, owner_id: str) -> int:
        with self.database.session() as session:
            ids = list(
                session.scalars(
                    select(TurnJobRecord.job_id).where(TurnJobRecord.owner_id == owner_id)
                )
            )
            if not ids:
                return 0
            session.execute(
                delete(TurnJobProgressRecord).where(TurnJobProgressRecord.job_id.in_(ids))
            )
            result = session.execute(delete(TurnJobRecord).where(TurnJobRecord.job_id.in_(ids)))
            session.commit()
            return _rowcount(result)

    def list_recoverable(
        self, *, connection_id: str, limit: int = 50, after_job_id: str = ""
    ) -> list[TurnJobRecord]:
        """Filter delivery state in SQL before LIMIT so old successes cannot hide lost work."""
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(TurnJobRecord)
                    .outerjoin(
                        RuntimeStepRecord,
                        and_(
                            RuntimeStepRecord.step_id == TurnJobRecord.runtime_step_id,
                            RuntimeStepRecord.deployment_id == TurnJobRecord.deployment_id,
                        ),
                    )
                    .outerjoin(
                        RuntimeOperationRecord,
                        and_(
                            RuntimeOperationRecord.operation_id == RuntimeStepRecord.operation_id,
                            RuntimeOperationRecord.owner_id == TurnJobRecord.owner_id,
                            RuntimeOperationRecord.connection_id == TurnJobRecord.connection_id,
                        ),
                    )
                    .where(
                        TurnJobRecord.connection_id == connection_id,
                        TurnJobRecord.kind == "message",
                        TurnJobRecord.job_id > after_job_id,
                        TurnJobRecord.expires_at > datetime.now(UTC),
                        or_(
                            TurnJobRecord.status.in_(("queued", "running")),
                            and_(
                                TurnJobRecord.status == "succeeded",
                                RuntimeStepRecord.status == "generated",
                                RuntimeOperationRecord.status.in_(("active", "awaiting_delivery")),
                            ),
                            and_(
                                TurnJobRecord.status.in_(("failed", "timed_out", "stopped")),
                                TurnJobRecord.final_notice_ack_at.is_(None),
                            ),
                        ),
                    )
                    .order_by(TurnJobRecord.job_id.asc())
                    .limit(max(1, min(limit, 100)))
                )
            )

    def acknowledge_final_notice(self, job_id: str, *, connection_id: str) -> bool:
        """Consume the single terminal-notice attempt BEFORE sending; never replay ambiguity."""
        with self.database.session() as session:
            result = session.execute(
                update(TurnJobRecord)
                .where(
                    TurnJobRecord.job_id == job_id,
                    TurnJobRecord.connection_id == connection_id,
                    TurnJobRecord.status.in_(("failed", "timed_out", "stopped")),
                    TurnJobRecord.final_notice_ack_at.is_(None),
                )
                .values(final_notice_ack_at=datetime.now(UTC))
            )
            session.commit()
            return _rowcount(result) == 1
