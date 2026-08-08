"""Persistence operations for deployment-scoped scheduled reminders."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import delete, select

from echo_masque.persistence.database import Database
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord
from echo_masque.persistence.scheduled_reminder_models import ScheduledReminderRecord


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class ScheduledReminderRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create(
        self,
        *,
        owner_id: str,
        deployment_id: str,
        channel_id: str,
        thread_id: str,
        target_user_id: str,
        reminder_text: str,
        scheduled_at: datetime,
    ) -> ScheduledReminderRecord:
        with self.database.session() as session:
            deployment = session.get(CharacterDeploymentRecord, deployment_id)
            if deployment is None or deployment.owner_id != owner_id:
                raise KeyError("deployment")
            record = ScheduledReminderRecord(
                id=str(uuid4()),
                owner_id=owner_id,
                deployment_id=deployment_id,
                connection_id=deployment.connection_id,
                platform=deployment.platform,
                channel_id=channel_id,
                thread_id=thread_id,
                target_user_id=target_user_id,
                reminder_text=reminder_text,
                scheduled_at=_utc(scheduled_at),
                status="pending",
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def list_for_deployment(
        self,
        *,
        owner_id: str,
        deployment_id: str,
        limit: int = 20,
        include_finished: bool = False,
    ) -> list[ScheduledReminderRecord]:
        with self.database.session() as session:
            query = select(ScheduledReminderRecord).where(
                ScheduledReminderRecord.owner_id == owner_id,
                ScheduledReminderRecord.deployment_id == deployment_id,
            )
            if not include_finished:
                query = query.where(
                    ScheduledReminderRecord.status.in_(("pending", "processing"))
                )
            return list(
                session.scalars(
                    query.order_by(
                        ScheduledReminderRecord.scheduled_at,
                        ScheduledReminderRecord.created_at,
                    ).limit(min(max(limit, 1), 50))
                )
            )

    def cancel(
        self,
        *,
        owner_id: str,
        deployment_id: str,
        reminder_id: str,
    ) -> ScheduledReminderRecord | None:
        with self.database.session() as session:
            record = session.get(ScheduledReminderRecord, reminder_id)
            if (
                record is None
                or record.owner_id != owner_id
                or record.deployment_id != deployment_id
            ):
                return None
            if record.status not in {"pending", "processing"}:
                return record
            record.status = "cancelled"
            record.processing_started_at = None
            session.commit()
            session.refresh(record)
            return record

    def recover_interrupted(self, *, stale_seconds: int = 120) -> int:
        threshold = datetime.now(UTC) - timedelta(seconds=max(30, stale_seconds))
        recovered = 0
        with self.database.session() as session:
            records = list(
                session.scalars(
                    select(ScheduledReminderRecord).where(
                        ScheduledReminderRecord.status == "processing"
                    )
                )
            )
            for record in records:
                started = record.processing_started_at
                if started is None or _utc(started) <= threshold:
                    record.status = "pending"
                    record.processing_started_at = None
                    recovered += 1
            session.commit()
        return recovered

    def claim_due(self, *, limit: int = 20) -> list[ScheduledReminderRecord]:
        now = datetime.now(UTC)
        with self.database.session() as session:
            records = list(
                session.scalars(
                    select(ScheduledReminderRecord)
                    .where(
                        ScheduledReminderRecord.status == "pending",
                        ScheduledReminderRecord.scheduled_at <= now,
                    )
                    .order_by(ScheduledReminderRecord.scheduled_at)
                    .limit(min(max(limit, 1), 50))
                )
            )
            for record in records:
                record.status = "processing"
                record.attempt_count += 1
                record.processing_started_at = now
            session.commit()
            for record in records:
                session.refresh(record)
            return records

    def mark_delivered(self, reminder_id: str) -> None:
        with self.database.session() as session:
            record = session.get(ScheduledReminderRecord, reminder_id)
            if record is None:
                return
            record.status = "completed"
            record.delivered_at = datetime.now(UTC)
            record.processing_started_at = None
            record.last_error = ""
            session.commit()

    def mark_failure(
        self,
        reminder_id: str,
        error: str,
        *,
        max_attempts: int,
        retry_seconds: int,
    ) -> None:
        with self.database.session() as session:
            record = session.get(ScheduledReminderRecord, reminder_id)
            if record is None:
                return
            record.last_error = error[:2000]
            record.processing_started_at = None
            if record.attempt_count >= max(1, max_attempts):
                record.status = "failed"
            else:
                record.status = "pending"
                record.scheduled_at = datetime.now(UTC) + timedelta(
                    seconds=max(5, retry_seconds)
                )
            session.commit()

    def purge_orphans(self) -> int:
        with self.database.session() as session:
            deployment_ids = select(CharacterDeploymentRecord.id)
            result = session.execute(
                delete(ScheduledReminderRecord).where(
                    ScheduledReminderRecord.deployment_id.not_in(deployment_ids)
                )
            )
            session.commit()
            return int(getattr(result, "rowcount", 0) or 0)

    def delete_owner(self, owner_id: str) -> int:
        with self.database.session() as session:
            result = session.execute(
                delete(ScheduledReminderRecord).where(
                    ScheduledReminderRecord.owner_id == owner_id
                )
            )
            session.commit()
            return int(getattr(result, "rowcount", 0) or 0)
