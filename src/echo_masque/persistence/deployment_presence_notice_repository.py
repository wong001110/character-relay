"""Persistent cooldown/idempotency queue for Deployment Presence system notices."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from echo_masque.persistence.database import Database
from echo_masque.persistence.deployment_presence_notice_models import (
    DeploymentPresenceNoticeRecord,
)


class DeploymentPresenceNoticeRepository:
    """Queue Bot-account notices without allowing repeated mentions to spam a channel."""

    def __init__(self, database: Database, *, cooldown_seconds: int = 180) -> None:
        self.database = database
        self.cooldown_seconds = max(1, cooldown_seconds)

    def enqueue_sleeping_notice(
        self,
        *,
        owner_id: str,
        deployment_id: str,
        connection_id: str,
        guild_id: str,
        channel_id: str,
        thread_id: str,
        source_message_id: str,
        character_display_name: str,
        now: datetime | None = None,
    ) -> bool:
        current = now or datetime.now(UTC)
        cutoff = current - timedelta(seconds=self.cooldown_seconds)
        with self.database.session() as session:
            recent = session.scalar(
                select(DeploymentPresenceNoticeRecord.id)
                .where(
                    DeploymentPresenceNoticeRecord.deployment_id == deployment_id,
                    DeploymentPresenceNoticeRecord.channel_id == channel_id,
                    DeploymentPresenceNoticeRecord.thread_id == thread_id,
                    DeploymentPresenceNoticeRecord.notice_type == "sleeping",
                    DeploymentPresenceNoticeRecord.created_at >= cutoff,
                    DeploymentPresenceNoticeRecord.status.in_(
                        ("pending", "delivering", "delivered")
                    ),
                )
                .limit(1)
            )
            if recent is not None:
                return False
            record = DeploymentPresenceNoticeRecord(
                id=str(uuid4()),
                owner_id=owner_id,
                deployment_id=deployment_id,
                connection_id=connection_id,
                guild_id=guild_id,
                channel_id=channel_id,
                thread_id=thread_id,
                source_message_id=source_message_id,
                notice_type="sleeping",
                character_display_name=character_display_name.strip()[:160] or "Character",
                status="pending",
                attempt_count=0,
                last_error="",
                available_at=current,
                created_at=current,
                updated_at=current,
            )
            session.add(record)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                return False
            return True

    def claim_due(
        self,
        *,
        limit: int = 20,
        now: datetime | None = None,
    ) -> tuple[DeploymentPresenceNoticeRecord, ...]:
        current = now or datetime.now(UTC)
        with self.database.session() as session:
            records = list(
                session.scalars(
                    select(DeploymentPresenceNoticeRecord)
                    .where(
                        DeploymentPresenceNoticeRecord.status == "pending",
                        DeploymentPresenceNoticeRecord.available_at <= current,
                    )
                    .order_by(
                        DeploymentPresenceNoticeRecord.available_at,
                        DeploymentPresenceNoticeRecord.created_at,
                    )
                    .limit(max(1, min(limit, 100)))
                )
            )
            for record in records:
                record.status = "delivering"
                record.attempt_count += 1
                record.updated_at = current
            session.commit()
            return tuple(records)

    def mark_delivered(
        self,
        notice_id: str,
        *,
        now: datetime | None = None,
    ) -> None:
        current = now or datetime.now(UTC)
        with self.database.session() as session:
            record = session.get(DeploymentPresenceNoticeRecord, notice_id)
            if record is None:
                return
            record.status = "delivered"
            record.last_error = ""
            record.delivered_at = current
            record.updated_at = current
            session.commit()

    def mark_failure(
        self,
        notice_id: str,
        error: str,
        *,
        max_attempts: int,
        retry_seconds: int,
        now: datetime | None = None,
    ) -> None:
        current = now or datetime.now(UTC)
        with self.database.session() as session:
            record = session.get(DeploymentPresenceNoticeRecord, notice_id)
            if record is None:
                return
            record.last_error = str(error)[:2000]
            record.updated_at = current
            if record.attempt_count >= max(1, max_attempts):
                record.status = "failed"
            else:
                record.status = "pending"
                record.available_at = current + timedelta(seconds=max(1, retry_seconds))
            session.commit()

    def recover_interrupted(self) -> int:
        with self.database.session() as session:
            records = list(
                session.scalars(
                    select(DeploymentPresenceNoticeRecord).where(
                        DeploymentPresenceNoticeRecord.status == "delivering"
                    )
                )
            )
            for record in records:
                record.status = "pending"
                record.last_error = "Recovered interrupted Presence notice delivery."
            session.commit()
            return len(records)


__all__ = ["DeploymentPresenceNoticeRepository"]
