"""Persistence boundary for Deployment-scoped Activity Sessions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select

from echo_masque.persistence.database import Database
from echo_masque.persistence.deployment_activity_models import (
    DeploymentActivitySessionItemRecord,
    DeploymentActivitySessionRecord,
)
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord

_TERMINAL_STATES = frozenset({"completed", "skipped", "failed", "cancelled"})


@dataclass(frozen=True, slots=True)
class DeploymentActivitySessionView:
    id: str
    deployment_id: str
    activity_type: str
    platform: str
    status: str
    source: str
    local_date: str
    schedule_timezone: str
    scheduled_start_at: datetime | None
    latest_start_at: datetime | None
    started_at: datetime | None
    expected_end_at: datetime | None
    ended_at: datetime | None
    candidate_budget: int
    open_budget: int
    watch_budget: int
    share_intent_budget: int
    exploration_percent: int
    candidate_count: int
    notice_count: int
    open_count: int
    watch_count: int
    engage_count: int
    reason: str
    error: str


class DeploymentActivityRepository:
    """Store bounded activities without moving lived state onto Character Card."""

    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def _aware(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @classmethod
    def _view(cls, record: DeploymentActivitySessionRecord) -> DeploymentActivitySessionView:
        return DeploymentActivitySessionView(
            id=record.id,
            deployment_id=record.deployment_id,
            activity_type=record.activity_type,
            platform=record.platform,
            status=record.status,
            source=record.source,
            local_date=record.local_date,
            schedule_timezone=record.schedule_timezone,
            scheduled_start_at=cls._aware(record.scheduled_start_at),
            latest_start_at=cls._aware(record.latest_start_at),
            started_at=cls._aware(record.started_at),
            expected_end_at=cls._aware(record.expected_end_at),
            ended_at=cls._aware(record.ended_at),
            candidate_budget=record.candidate_budget,
            open_budget=record.open_budget,
            watch_budget=record.watch_budget,
            share_intent_budget=record.share_intent_budget,
            exploration_percent=record.exploration_percent,
            candidate_count=record.candidate_count,
            notice_count=record.notice_count,
            open_count=record.open_count,
            watch_count=record.watch_count,
            engage_count=record.engage_count,
            reason=record.reason,
            error=record.error,
        )

    def ensure_scheduled(
        self,
        *,
        owner_id: str,
        deployment_id: str,
        platform: str,
        schedule_key: str,
        local_date: str,
        schedule_timezone: str,
        scheduled_start_at: datetime,
        latest_start_at: datetime,
        candidate_budget: int,
        open_budget: int,
        watch_budget: int,
        share_intent_budget: int,
        exploration_percent: int,
        now: datetime | None = None,
    ) -> DeploymentActivitySessionView | None:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        with self.database.session() as session:
            deployment = session.get(CharacterDeploymentRecord, deployment_id)
            if deployment is None or deployment.owner_id != owner_id:
                return None
            record = session.scalar(
                select(DeploymentActivitySessionRecord).where(
                    DeploymentActivitySessionRecord.schedule_key == schedule_key
                )
            )
            if record is None:
                record = DeploymentActivitySessionRecord(
                    id=str(uuid4()),
                    owner_id=owner_id,
                    deployment_id=deployment_id,
                    activity_type="discovery_browsing",
                    platform=platform[:32],
                    status="scheduled",
                    source="scheduler",
                    schedule_key=schedule_key[:160],
                    local_date=local_date[:10],
                    schedule_timezone=schedule_timezone[:120],
                    scheduled_start_at=scheduled_start_at,
                    latest_start_at=latest_start_at,
                    candidate_budget=max(1, min(candidate_budget, 50)),
                    open_budget=max(0, min(open_budget, 20)),
                    watch_budget=max(0, min(watch_budget, 10)),
                    share_intent_budget=max(0, min(share_intent_budget, 5)),
                    exploration_percent=max(0, min(exploration_percent, 100)),
                    reason="daily_leisure_opportunity",
                    created_at=current,
                    updated_at=current,
                )
                session.add(record)
                session.commit()
                session.refresh(record)
            return self._view(record)

    def create_manual(
        self,
        *,
        owner_id: str,
        deployment_id: str,
        platform: str,
        candidate_budget: int,
        open_budget: int,
        watch_budget: int,
        share_intent_budget: int,
        exploration_percent: int,
        now: datetime | None = None,
    ) -> DeploymentActivitySessionView | None:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        with self.database.session() as session:
            deployment = session.get(CharacterDeploymentRecord, deployment_id)
            if deployment is None or deployment.owner_id != owner_id:
                return None
            record = DeploymentActivitySessionRecord(
                id=str(uuid4()),
                owner_id=owner_id,
                deployment_id=deployment_id,
                activity_type="discovery_browsing",
                platform=platform[:32],
                status="scheduled",
                source="manual",
                schedule_key=None,
                scheduled_start_at=current,
                latest_start_at=current,
                candidate_budget=max(1, min(candidate_budget, 50)),
                open_budget=max(0, min(open_budget, 20)),
                watch_budget=max(0, min(watch_budget, 10)),
                share_intent_budget=max(0, min(share_intent_budget, 5)),
                exploration_percent=max(0, min(exploration_percent, 100)),
                reason="manual_shadow_browsing",
                created_at=current,
                updated_at=current,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return self._view(record)

    def get(
        self,
        *,
        owner_id: str,
        session_id: str,
    ) -> DeploymentActivitySessionView | None:
        with self.database.session() as session:
            record = session.get(DeploymentActivitySessionRecord, session_id)
            if record is None or record.owner_id != owner_id:
                return None
            return self._view(record)

    def active_for_deployment(
        self,
        *,
        owner_id: str,
        deployment_id: str,
    ) -> DeploymentActivitySessionView | None:
        with self.database.session() as session:
            record = session.scalar(
                select(DeploymentActivitySessionRecord)
                .where(
                    DeploymentActivitySessionRecord.owner_id == owner_id,
                    DeploymentActivitySessionRecord.deployment_id == deployment_id,
                    DeploymentActivitySessionRecord.status == "active",
                )
                .order_by(DeploymentActivitySessionRecord.started_at.desc())
                .limit(1)
            )
            return self._view(record) if record is not None else None

    def list_for_deployment(
        self,
        *,
        owner_id: str,
        deployment_id: str,
        limit: int = 50,
    ) -> tuple[DeploymentActivitySessionView, ...]:
        with self.database.session() as session:
            records = list(
                session.scalars(
                    select(DeploymentActivitySessionRecord)
                    .where(
                        DeploymentActivitySessionRecord.owner_id == owner_id,
                        DeploymentActivitySessionRecord.deployment_id == deployment_id,
                    )
                    .order_by(DeploymentActivitySessionRecord.created_at.desc())
                    .limit(max(1, min(limit, 200)))
                )
            )
        return tuple(self._view(record) for record in records)

    def list_due_scheduled(
        self,
        *,
        now: datetime,
        limit: int = 50,
    ) -> tuple[DeploymentActivitySessionView, ...]:
        current = now.astimezone(UTC)
        with self.database.session() as session:
            records = list(
                session.scalars(
                    select(DeploymentActivitySessionRecord)
                    .where(
                        DeploymentActivitySessionRecord.status == "scheduled",
                        DeploymentActivitySessionRecord.scheduled_start_at.is_not(None),
                        DeploymentActivitySessionRecord.scheduled_start_at <= current,
                    )
                    .order_by(DeploymentActivitySessionRecord.scheduled_start_at)
                    .limit(max(1, min(limit, 200)))
                )
            )
        return tuple(self._view(record) for record in records)

    def start(
        self,
        *,
        owner_id: str,
        session_id: str,
        expected_end_at: datetime,
        now: datetime | None = None,
    ) -> DeploymentActivitySessionView | None:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        with self.database.session() as session:
            record = session.get(DeploymentActivitySessionRecord, session_id)
            if record is None or record.owner_id != owner_id:
                return None
            if record.status in _TERMINAL_STATES:
                return self._view(record)
            if record.status != "scheduled":
                return self._view(record)
            record.status = "active"
            record.started_at = current
            record.expected_end_at = expected_end_at
            record.reason = "browsing_session_started"
            record.updated_at = current
            session.commit()
            session.refresh(record)
            return self._view(record)

    def record_item(
        self,
        *,
        owner_id: str,
        deployment_id: str,
        session_id: str,
        discovery_item_id: str,
        rank_position: int,
        attention_level: str,
        score: float,
        reason: str,
        now: datetime | None = None,
    ) -> DeploymentActivitySessionItemRecord | None:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        with self.database.session() as session:
            activity = session.get(DeploymentActivitySessionRecord, session_id)
            if (
                activity is None
                or activity.owner_id != owner_id
                or activity.deployment_id != deployment_id
            ):
                return None
            record = session.scalar(
                select(DeploymentActivitySessionItemRecord).where(
                    DeploymentActivitySessionItemRecord.session_id == session_id,
                    DeploymentActivitySessionItemRecord.discovery_item_id == discovery_item_id,
                )
            )
            if record is None:
                record = DeploymentActivitySessionItemRecord(
                    id=str(uuid4()),
                    owner_id=owner_id,
                    deployment_id=deployment_id,
                    session_id=session_id,
                    discovery_item_id=discovery_item_id,
                    rank_position=max(1, rank_position),
                    attention_level=attention_level[:24],
                    score=max(0.0, min(float(score), 1.0)),
                    reason=reason[:1000],
                    created_at=current,
                )
                session.add(record)
                session.commit()
                session.refresh(record)
            return record

    def list_items(
        self,
        *,
        owner_id: str,
        session_id: str,
    ) -> tuple[DeploymentActivitySessionItemRecord, ...]:
        with self.database.session() as session:
            activity = session.get(DeploymentActivitySessionRecord, session_id)
            if activity is None or activity.owner_id != owner_id:
                return ()
            return tuple(
                session.scalars(
                    select(DeploymentActivitySessionItemRecord)
                    .where(DeploymentActivitySessionItemRecord.session_id == session_id)
                    .order_by(DeploymentActivitySessionItemRecord.rank_position)
                )
            )

    def finish(
        self,
        *,
        owner_id: str,
        session_id: str,
        status: str = "completed",
        reason: str = "browsing_session_completed",
        error: str = "",
        candidate_count: int = 0,
        notice_count: int = 0,
        open_count: int = 0,
        watch_count: int = 0,
        engage_count: int = 0,
        now: datetime | None = None,
    ) -> DeploymentActivitySessionView | None:
        if status not in _TERMINAL_STATES:
            raise ValueError("Activity session finish status must be terminal.")
        current = (now or datetime.now(UTC)).astimezone(UTC)
        with self.database.session() as session:
            record = session.get(DeploymentActivitySessionRecord, session_id)
            if record is None or record.owner_id != owner_id:
                return None
            record.status = status
            record.ended_at = current
            record.candidate_count = max(0, candidate_count)
            record.notice_count = max(0, notice_count)
            record.open_count = max(0, open_count)
            record.watch_count = max(0, watch_count)
            record.engage_count = max(0, engage_count)
            record.reason = reason[:1000]
            record.error = error[:2000]
            record.updated_at = current
            session.commit()
            session.refresh(record)
            return self._view(record)


__all__ = [
    "DeploymentActivityRepository",
    "DeploymentActivitySessionView",
]
