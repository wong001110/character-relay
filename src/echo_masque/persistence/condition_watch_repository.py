"""Persistence operations for Tool Calling V2 condition watches."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import delete, select, update

from echo_masque.persistence.condition_watch_models import ConditionWatchRecord
from echo_masque.persistence.database import Database
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class ConditionWatchRepository:
    """Store bounded, owner-scoped future condition checks."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def create(
        self,
        *,
        owner_id: str,
        deployment_id: str,
        condition_text: str,
        notification_text: str,
        check_interval_seconds: int,
        expires_at: datetime,
        max_attempts: int,
        next_check_at: datetime | None = None,
    ) -> ConditionWatchRecord:
        now = datetime.now(UTC)
        with self.database.session() as session:
            deployment = session.get(CharacterDeploymentRecord, deployment_id)
            if deployment is None or deployment.owner_id != owner_id:
                raise KeyError("deployment")
            record = ConditionWatchRecord(
                id=str(uuid4()),
                owner_id=owner_id,
                deployment_id=deployment_id,
                character_card_id=deployment.character_card_id,
                condition_text=condition_text.strip(),
                notification_text=notification_text.strip(),
                status="active",
                check_interval_seconds=check_interval_seconds,
                attempt_count=0,
                max_attempts=max_attempts,
                next_check_at=_utc(next_check_at or now),
                expires_at=_utc(expires_at),
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def get(self, *, owner_id: str, watch_id: str) -> ConditionWatchRecord | None:
        with self.database.session() as session:
            record = session.get(ConditionWatchRecord, watch_id)
            if record is None or record.owner_id != owner_id:
                return None
            return record

    def list_for_deployment(
        self,
        *,
        owner_id: str,
        deployment_id: str,
        limit: int = 20,
        include_finished: bool = False,
    ) -> list[ConditionWatchRecord]:
        bounded = min(max(limit, 1), 50)
        with self.database.session() as session:
            query = select(ConditionWatchRecord).where(
                ConditionWatchRecord.owner_id == owner_id,
                ConditionWatchRecord.deployment_id == deployment_id,
            )
            if not include_finished:
                query = query.where(ConditionWatchRecord.status == "active")
            return list(
                session.scalars(
                    query.order_by(
                        ConditionWatchRecord.created_at.desc(),
                        ConditionWatchRecord.id.desc(),
                    ).limit(bounded)
                )
            )

    def cancel(
        self,
        *,
        owner_id: str,
        deployment_id: str,
        watch_id: str,
    ) -> ConditionWatchRecord | None:
        with self.database.session() as session:
            record = session.get(ConditionWatchRecord, watch_id)
            if (
                record is None
                or record.owner_id != owner_id
                or record.deployment_id != deployment_id
            ):
                return None
            if record.status == "active":
                record.status = "cancelled"
                session.commit()
                session.refresh(record)
            return record

    def claim_due(self, *, limit: int = 20) -> list[ConditionWatchRecord]:
        """Reserve due watches by moving their next check before returning them.

        The record remains `active`; advancing `next_check_at` is the lease that prevents a
        fast second poll from immediately selecting the same watch again.
        """

        now = datetime.now(UTC)
        bounded = min(max(limit, 1), 50)
        with self.database.session() as session:
            expired = list(
                session.scalars(
                    select(ConditionWatchRecord).where(
                        ConditionWatchRecord.status == "active",
                        ConditionWatchRecord.expires_at <= now,
                    )
                )
            )
            for record in expired:
                record.status = "expired"

            records = list(
                session.scalars(
                    select(ConditionWatchRecord)
                    .where(
                        ConditionWatchRecord.status == "active",
                        ConditionWatchRecord.next_check_at <= now,
                        ConditionWatchRecord.expires_at > now,
                        ConditionWatchRecord.attempt_count
                        < ConditionWatchRecord.max_attempts,
                    )
                    .order_by(
                        ConditionWatchRecord.next_check_at,
                        ConditionWatchRecord.created_at,
                    )
                    .limit(bounded)
                )
            )
            for record in records:
                record.attempt_count += 1
                record.last_checked_at = now
                record.next_check_at = now + timedelta(
                    seconds=max(60, record.check_interval_seconds)
                )
                record.last_error = ""
            session.commit()
            for record in records:
                session.refresh(record)
            return records

    def mark_not_met(self, watch_id: str) -> None:
        with self.database.session() as session:
            record = session.get(ConditionWatchRecord, watch_id)
            if record is None or record.status != "active":
                return
            if record.attempt_count >= record.max_attempts:
                record.status = "expired"
            session.commit()

    def mark_triggered(self, watch_id: str) -> None:
        with self.database.session() as session:
            record = session.get(ConditionWatchRecord, watch_id)
            if record is None or record.status != "active":
                return
            record.status = "triggered"
            record.triggered_at = datetime.now(UTC)
            record.last_error = ""
            session.commit()

    def mark_failure(self, watch_id: str, error: str) -> None:
        with self.database.session() as session:
            record = session.get(ConditionWatchRecord, watch_id)
            if record is None or record.status != "active":
                return
            record.last_error = error[:2000]
            if record.attempt_count >= record.max_attempts:
                record.status = "failed"
            session.commit()

    def purge_orphans(self) -> int:
        with self.database.session() as session:
            deployment_ids = select(CharacterDeploymentRecord.id)
            result = session.execute(
                delete(ConditionWatchRecord).where(
                    ConditionWatchRecord.deployment_id.not_in(deployment_ids)
                )
            )
            session.commit()
            return int(getattr(result, "rowcount", 0) or 0)

    def claim_owner(self, source_owner_id: str, target_owner_id: str) -> int:
        with self.database.session() as session:
            result = session.execute(
                update(ConditionWatchRecord)
                .where(ConditionWatchRecord.owner_id == source_owner_id)
                .values(owner_id=target_owner_id)
            )
            session.commit()
            return int(getattr(result, "rowcount", 0) or 0)

    def delete_owner(self, owner_id: str) -> int:
        with self.database.session() as session:
            result = session.execute(
                delete(ConditionWatchRecord).where(
                    ConditionWatchRecord.owner_id == owner_id
                )
            )
            session.commit()
            return int(getattr(result, "rowcount", 0) or 0)
