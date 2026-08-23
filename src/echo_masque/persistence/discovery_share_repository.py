"""Persistence boundary for Discovery review/auto share policy and durable outbox."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError

from echo_masque.pagination import decode_time_cursor, encode_time_cursor
from echo_masque.persistence.database import Database
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord
from echo_masque.persistence.discovery_share_models import (
    DeploymentDiscoverySharePolicyRecord,
    DeploymentDiscoveryShareRecord,
)

_TERMINAL = frozenset({"delivered", "rejected", "failed", "cancelled"})


@dataclass(frozen=True, slots=True)
class DiscoverySharePolicyView:
    deployment_id: str
    auto_share_enabled: bool
    daily_share_budget: int
    share_cooldown_minutes: int


class DiscoveryShareRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def _now(value: datetime | None = None) -> datetime:
        return (value or datetime.now(UTC)).astimezone(UTC)

    def get_policy(self, *, owner_id: str, deployment_id: str) -> DiscoverySharePolicyView | None:
        with self.database.session() as session:
            deployment = session.get(CharacterDeploymentRecord, deployment_id)
            if deployment is None or deployment.owner_id != owner_id:
                return None
            record = session.get(DeploymentDiscoverySharePolicyRecord, deployment_id)
            if record is None:
                return DiscoverySharePolicyView(deployment_id, False, 1, 180)
            return DiscoverySharePolicyView(
                deployment_id=record.deployment_id,
                auto_share_enabled=record.auto_share_enabled,
                daily_share_budget=record.daily_share_budget,
                share_cooldown_minutes=record.share_cooldown_minutes,
            )

    def set_policy(
        self,
        *,
        owner_id: str,
        deployment_id: str,
        auto_share_enabled: bool,
        daily_share_budget: int,
        share_cooldown_minutes: int,
    ) -> DiscoverySharePolicyView | None:
        budget = max(0, min(int(daily_share_budget), 8))
        cooldown = max(15, min(int(share_cooldown_minutes), 24 * 60))
        with self.database.session() as session:
            deployment = session.get(CharacterDeploymentRecord, deployment_id)
            if deployment is None or deployment.owner_id != owner_id:
                return None
            record = session.get(DeploymentDiscoverySharePolicyRecord, deployment_id)
            if record is None:
                record = DeploymentDiscoverySharePolicyRecord(
                    deployment_id=deployment_id,
                    owner_id=owner_id,
                )
                session.add(record)
            record.auto_share_enabled = bool(auto_share_enabled)
            record.daily_share_budget = budget
            record.share_cooldown_minutes = cooldown
            session.commit()
        return self.get_policy(owner_id=owner_id, deployment_id=deployment_id)

    def create_proposal(
        self,
        *,
        owner_id: str,
        deployment_id: str,
        discovery_item_id: str,
        source_decision_id: str,
        mode: str,
        status: str,
        motivation: str,
        confidence: float,
        conversation_thread_id: str,
        relationship_subject_key: str,
        channel_id: str,
        thread_id: str,
        draft_text: str,
        now: datetime | None = None,
    ) -> DeploymentDiscoveryShareRecord | None:
        current = self._now(now)
        with self.database.session() as session:
            deployment = session.get(CharacterDeploymentRecord, deployment_id)
            if deployment is None or deployment.owner_id != owner_id:
                return None
            existing = session.scalar(
                select(DeploymentDiscoveryShareRecord).where(
                    DeploymentDiscoveryShareRecord.deployment_id == deployment_id,
                    DeploymentDiscoveryShareRecord.discovery_item_id == discovery_item_id,
                )
            )
            if existing is not None:
                return existing
            record = DeploymentDiscoveryShareRecord(
                id=str(uuid4()),
                owner_id=owner_id,
                deployment_id=deployment_id,
                discovery_item_id=discovery_item_id,
                source_decision_id=source_decision_id[:64],
                mode=mode[:24],
                status=status[:32],
                motivation=motivation[:64],
                confidence=max(0.0, min(float(confidence), 1.0)),
                conversation_thread_id=conversation_thread_id[:64],
                relationship_subject_key=relationship_subject_key[:320],
                channel_id=channel_id[:200],
                thread_id=thread_id[:200],
                draft_text=draft_text.strip()[:1900],
                next_attempt_at=current if status == "queued" else None,
                queued_at=current if status == "queued" else None,
                created_at=current,
                updated_at=current,
            )
            session.add(record)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                return session.scalar(
                    select(DeploymentDiscoveryShareRecord).where(
                        DeploymentDiscoveryShareRecord.deployment_id == deployment_id,
                        DeploymentDiscoveryShareRecord.discovery_item_id == discovery_item_id,
                    )
                )
            session.refresh(record)
            return record

    def get(self, *, owner_id: str, share_id: str) -> DeploymentDiscoveryShareRecord | None:
        with self.database.session() as session:
            record = session.get(DeploymentDiscoveryShareRecord, share_id)
            return record if record is not None and record.owner_id == owner_id else None

    def list_for_deployment(
        self, *, owner_id: str, deployment_id: str, limit: int = 100
    ) -> tuple[DeploymentDiscoveryShareRecord, ...]:
        with self.database.session() as session:
            return tuple(
                session.scalars(
                    select(DeploymentDiscoveryShareRecord)
                    .where(
                        DeploymentDiscoveryShareRecord.owner_id == owner_id,
                        DeploymentDiscoveryShareRecord.deployment_id == deployment_id,
                    )
                    .order_by(DeploymentDiscoveryShareRecord.created_at.desc())
                    .limit(max(1, min(limit, 500)))
                )
            )

    def list_for_deployment_page(
        self,
        *,
        owner_id: str,
        deployment_id: str,
        limit: int = 100,
        cursor: str | None = None,
    ) -> tuple[tuple[DeploymentDiscoveryShareRecord, ...], str | None]:
        bounded_limit = max(1, min(limit, 500))
        with self.database.session() as session:
            query = select(DeploymentDiscoveryShareRecord).where(
                DeploymentDiscoveryShareRecord.owner_id == owner_id,
                DeploymentDiscoveryShareRecord.deployment_id == deployment_id,
            )
            if cursor:
                created_at, identifier = decode_time_cursor(cursor)
                query = query.where(
                    or_(
                        DeploymentDiscoveryShareRecord.created_at < created_at,
                        and_(
                            DeploymentDiscoveryShareRecord.created_at == created_at,
                            DeploymentDiscoveryShareRecord.id < identifier,
                        ),
                    )
                )
            records = list(
                session.scalars(
                    query.order_by(
                        DeploymentDiscoveryShareRecord.created_at.desc(),
                        DeploymentDiscoveryShareRecord.id.desc(),
                    ).limit(bounded_limit + 1)
                )
            )
        has_more = len(records) > bounded_limit
        items = records[:bounded_limit]
        next_cursor = (
            encode_time_cursor(items[-1].created_at, items[-1].id) if has_more and items else None
        )
        return tuple(items), next_cursor

    def approve(
        self, *, owner_id: str, share_id: str, now: datetime | None = None
    ) -> DeploymentDiscoveryShareRecord | None:
        current = self._now(now)
        with self.database.session() as session:
            record = session.get(DeploymentDiscoveryShareRecord, share_id)
            if record is None or record.owner_id != owner_id:
                return None
            if record.status != "pending_review":
                return record
            record.status = "queued"
            record.approved_at = current
            record.queued_at = current
            record.next_attempt_at = current
            record.updated_at = current
            session.commit()
            session.refresh(record)
            return record

    def reject(
        self, *, owner_id: str, share_id: str, now: datetime | None = None
    ) -> DeploymentDiscoveryShareRecord | None:
        current = self._now(now)
        with self.database.session() as session:
            record = session.get(DeploymentDiscoveryShareRecord, share_id)
            if record is None or record.owner_id != owner_id:
                return None
            if record.status in _TERMINAL:
                return record
            record.status = "rejected"
            record.rejected_at = current
            record.next_attempt_at = None
            record.updated_at = current
            session.commit()
            session.refresh(record)
            return record

    def recover_interrupted(self) -> int:
        with self.database.session() as session:
            rows = list(
                session.scalars(
                    select(DeploymentDiscoveryShareRecord).where(
                        DeploymentDiscoveryShareRecord.status == "delivering"
                    )
                )
            )
            now = datetime.now(UTC)
            for row in rows:
                row.status = "queued"
                row.next_attempt_at = now
                row.updated_at = now
            session.commit()
            return len(rows)

    def claim_due(
        self, *, now: datetime | None = None, limit: int = 10
    ) -> tuple[DeploymentDiscoveryShareRecord, ...]:
        current = self._now(now)
        with self.database.session() as session:
            rows = list(
                session.scalars(
                    select(DeploymentDiscoveryShareRecord)
                    .where(
                        DeploymentDiscoveryShareRecord.status == "queued",
                        DeploymentDiscoveryShareRecord.next_attempt_at.is_not(None),
                        DeploymentDiscoveryShareRecord.next_attempt_at <= current,
                    )
                    .order_by(DeploymentDiscoveryShareRecord.next_attempt_at)
                    .limit(max(1, min(limit, 50)))
                )
            )
            for row in rows:
                row.status = "delivering"
                row.attempt_count += 1
                row.updated_at = current
            session.commit()
            for row in rows:
                session.refresh(row)
            return tuple(rows)

    def defer(self, *, share_id: str, minutes: int = 5, reason: str = "") -> None:
        now = datetime.now(UTC)
        with self.database.session() as session:
            record = session.get(DeploymentDiscoveryShareRecord, share_id)
            if record is None:
                return
            record.status = "queued"
            record.next_attempt_at = now + timedelta(minutes=max(1, minutes))
            record.last_error = reason[:1000]
            record.updated_at = now
            session.commit()

    def mark_delivered(self, *, share_id: str, message_id: str) -> None:
        now = datetime.now(UTC)
        with self.database.session() as session:
            record = session.get(DeploymentDiscoveryShareRecord, share_id)
            if record is None:
                return
            record.status = "delivered"
            record.discord_message_id = message_id[:200]
            record.delivered_at = now
            record.next_attempt_at = None
            record.last_error = ""
            record.updated_at = now
            session.commit()

    def mark_failure(self, *, share_id: str, error: str, max_attempts: int = 3) -> None:
        now = datetime.now(UTC)
        with self.database.session() as session:
            record = session.get(DeploymentDiscoveryShareRecord, share_id)
            if record is None:
                return
            record.last_error = error[:2000]
            if record.attempt_count >= max(1, max_attempts):
                record.status = "failed"
                record.next_attempt_at = None
            else:
                record.status = "queued"
                record.next_attempt_at = now + timedelta(minutes=2**record.attempt_count)
            record.updated_at = now
            session.commit()

    def cancel(self, *, share_id: str, reason: str) -> None:
        with self.database.session() as session:
            record = session.get(DeploymentDiscoveryShareRecord, share_id)
            if record is None or record.status in _TERMINAL:
                return
            record.status = "cancelled"
            record.last_error = reason[:2000]
            record.next_attempt_at = None
            record.updated_at = datetime.now(UTC)
            session.commit()

    def recent_delivery_count(
        self,
        *,
        owner_id: str,
        deployment_id: str,
        since: datetime,
    ) -> int:
        with self.database.session() as session:
            value = session.scalar(
                select(func.count())
                .select_from(DeploymentDiscoveryShareRecord)
                .where(
                    DeploymentDiscoveryShareRecord.owner_id == owner_id,
                    DeploymentDiscoveryShareRecord.deployment_id == deployment_id,
                    DeploymentDiscoveryShareRecord.status.in_(
                        ("queued", "delivering", "delivered")
                    ),
                    DeploymentDiscoveryShareRecord.created_at >= since,
                )
            )
            return int(value or 0)

    def latest_delivery_time(self, *, owner_id: str, deployment_id: str) -> datetime | None:
        with self.database.session() as session:
            return session.scalar(
                select(func.max(DeploymentDiscoveryShareRecord.delivered_at)).where(
                    DeploymentDiscoveryShareRecord.owner_id == owner_id,
                    DeploymentDiscoveryShareRecord.deployment_id == deployment_id,
                    DeploymentDiscoveryShareRecord.status == "delivered",
                )
            )


__all__ = ["DiscoverySharePolicyView", "DiscoveryShareRepository"]
