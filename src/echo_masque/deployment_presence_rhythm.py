"""Deterministic, LLM-free daily Presence rhythm for Deployment runtime instances."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from echo_masque.persistence.database import Database
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord
from echo_masque.persistence.deployment_presence_repository import DeploymentPresenceRepository
from echo_masque.persistence.deployment_presence_rhythm_models import (
    DeploymentPresenceRhythmRecord,
)
from echo_masque.persistence.server_runtime_repository import ServerRuntimeRepository


@dataclass(frozen=True, slots=True)
class DeploymentPresenceRhythmView:
    deployment_id: str
    enabled: bool
    preferred_sleep_start_minute: int
    sleep_duration_min_minutes: int
    sleep_duration_max_minutes: int
    variation_minutes: int
    config_version: int
    schedule_local_date: str
    schedule_timezone: str
    scheduled_sleep_at: datetime | None
    scheduled_wake_at: datetime | None
    next_transition_at: datetime | None
    next_state: str
    last_transition_at: datetime | None
    last_transition_reason: str


@dataclass(frozen=True, slots=True)
class MaterializedPresenceSchedule:
    local_date: date
    timezone: str
    sleep_at: datetime
    wake_at: datetime


class DeploymentPresenceRhythmService:
    """Generate/reconcile persisted sleep schedules without any model/provider dependency."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self.presence = DeploymentPresenceRepository(database)
        self.server_runtime = ServerRuntimeRepository(database)

    @staticmethod
    def _view(record: DeploymentPresenceRhythmRecord) -> DeploymentPresenceRhythmView:
        return DeploymentPresenceRhythmView(
            deployment_id=record.deployment_id,
            enabled=record.enabled,
            preferred_sleep_start_minute=record.preferred_sleep_start_minute,
            sleep_duration_min_minutes=record.sleep_duration_min_minutes,
            sleep_duration_max_minutes=record.sleep_duration_max_minutes,
            variation_minutes=record.variation_minutes,
            config_version=record.config_version,
            schedule_local_date=record.schedule_local_date,
            schedule_timezone=record.schedule_timezone,
            scheduled_sleep_at=record.scheduled_sleep_at,
            scheduled_wake_at=record.scheduled_wake_at,
            next_transition_at=record.next_transition_at,
            next_state=record.next_state,
            last_transition_at=record.last_transition_at,
            last_transition_reason=record.last_transition_reason,
        )

    @staticmethod
    def _stable_int(*parts: object) -> int:
        digest = hashlib.sha256("|".join(str(part) for part in parts).encode()).digest()
        return int.from_bytes(digest[:8], "big", signed=False)

    @classmethod
    def _bounded_offset(cls, *, maximum: int, seed_parts: tuple[object, ...]) -> int:
        if maximum <= 0:
            return 0
        width = maximum * 2 + 1
        return cls._stable_int(*seed_parts) % width - maximum

    @classmethod
    def materialize_schedule(
        cls,
        *,
        deployment_id: str,
        local_date: date,
        timezone: str,
        preferred_sleep_start_minute: int,
        sleep_duration_min_minutes: int,
        sleep_duration_max_minutes: int,
        variation_minutes: int,
        config_version: int,
    ) -> MaterializedPresenceSchedule:
        zone = ZoneInfo(timezone)
        start_minute = max(0, min(preferred_sleep_start_minute, 23 * 60 + 59))
        variation = max(0, min(variation_minutes, 180))
        start_offset = cls._bounded_offset(
            maximum=variation,
            seed_parts=(deployment_id, local_date.isoformat(), config_version, "sleep-start"),
        )
        varied_start = max(0, min(start_minute + start_offset, 23 * 60 + 59))

        duration_min = max(60, min(sleep_duration_min_minutes, 16 * 60))
        duration_max = max(duration_min, min(sleep_duration_max_minutes, 16 * 60))
        span = duration_max - duration_min
        duration = duration_min
        if span:
            duration += cls._stable_int(
                deployment_id,
                local_date.isoformat(),
                config_version,
                "sleep-duration",
            ) % (span + 1)

        local_sleep = datetime.combine(
            local_date,
            time(hour=varied_start // 60, minute=varied_start % 60),
            tzinfo=zone,
        )
        local_wake = local_sleep + timedelta(minutes=duration)
        return MaterializedPresenceSchedule(
            local_date=local_date,
            timezone=timezone,
            sleep_at=local_sleep.astimezone(UTC),
            wake_at=local_wake.astimezone(UTC),
        )

    def get(
        self,
        *,
        owner_id: str,
        deployment_id: str,
    ) -> DeploymentPresenceRhythmView | None:
        with self.database.session() as session:
            deployment = session.get(CharacterDeploymentRecord, deployment_id)
            if deployment is None or deployment.owner_id != owner_id:
                return None
            record = session.get(DeploymentPresenceRhythmRecord, deployment_id)
            if record is None:
                record = DeploymentPresenceRhythmRecord(
                    deployment_id=deployment_id,
                    owner_id=owner_id,
                    enabled=False,
                )
                session.add(record)
                session.commit()
                session.refresh(record)
            return self._view(record)

    def configure(
        self,
        *,
        owner_id: str,
        deployment_id: str,
        enabled: bool,
        preferred_sleep_start_minute: int,
        sleep_duration_min_minutes: int,
        sleep_duration_max_minutes: int,
        variation_minutes: int,
        now: datetime | None = None,
    ) -> DeploymentPresenceRhythmView | None:
        if not 0 <= preferred_sleep_start_minute <= 1439:
            raise ValueError("preferred_sleep_start_minute must be between 0 and 1439.")
        if not 60 <= sleep_duration_min_minutes <= 960:
            raise ValueError("sleep_duration_min_minutes must be between 60 and 960.")
        if not sleep_duration_min_minutes <= sleep_duration_max_minutes <= 960:
            raise ValueError(
                "sleep_duration_max_minutes must be >= minimum and <= 960."
            )
        if not 0 <= variation_minutes <= 180:
            raise ValueError("variation_minutes must be between 0 and 180.")

        current = (now or datetime.now(UTC)).astimezone(UTC)
        with self.database.session() as session:
            deployment = session.get(CharacterDeploymentRecord, deployment_id)
            if deployment is None or deployment.owner_id != owner_id:
                return None
            record = session.get(DeploymentPresenceRhythmRecord, deployment_id)
            if record is None:
                # SQLAlchemy column defaults are applied at INSERT time, not when the Python
                # object is constructed. Seed config_version explicitly because configuration
                # comparison/invalidation happens before the first flush.
                record = DeploymentPresenceRhythmRecord(
                    deployment_id=deployment_id,
                    owner_id=owner_id,
                    config_version=0,
                )
                session.add(record)
            changed = any(
                (
                    record.enabled != enabled,
                    record.preferred_sleep_start_minute != preferred_sleep_start_minute,
                    record.sleep_duration_min_minutes != sleep_duration_min_minutes,
                    record.sleep_duration_max_minutes != sleep_duration_max_minutes,
                    record.variation_minutes != variation_minutes,
                )
            )
            record.enabled = enabled
            record.preferred_sleep_start_minute = preferred_sleep_start_minute
            record.sleep_duration_min_minutes = sleep_duration_min_minutes
            record.sleep_duration_max_minutes = sleep_duration_max_minutes
            record.variation_minutes = variation_minutes
            if changed:
                record.config_version = (record.config_version or 0) + 1
                record.schedule_local_date = ""
                record.schedule_timezone = ""
                record.scheduled_sleep_at = None
                record.scheduled_wake_at = None
                record.next_transition_at = None
                record.next_state = ""
            record.updated_at = current
            session.commit()

        if enabled:
            self.reconcile_deployment(
                owner_id=owner_id,
                deployment_id=deployment_id,
                now=current,
            )
        else:
            # A rhythm-owned sleeping state must not survive after the rhythm is disabled.
            # Manual/other Presence states remain authoritative and are never reset here.
            presence = self.presence.get(
                owner_id=owner_id,
                deployment_id=deployment_id,
            )
            if presence is not None and presence.state == "sleeping" and presence.source == "rhythm":
                self.presence.set_state(
                    owner_id=owner_id,
                    deployment_id=deployment_id,
                    state="idle",
                    source="rhythm",
                    reason="scheduled_rhythm_disabled",
                    now=current,
                )
        return self.get(owner_id=owner_id, deployment_id=deployment_id)

    def _deployment_timezone(self, deployment: CharacterDeploymentRecord) -> str:
        return self.server_runtime.resolve_timezone(
            owner_id=deployment.owner_id,
            connection_id=deployment.connection_id,
            guild_id=deployment.workspace_id,
        )

    @staticmethod
    def _stored_schedule_matches(
        record: DeploymentPresenceRhythmRecord,
        *,
        local_date: date,
        timezone: str,
    ) -> bool:
        return (
            record.schedule_local_date == local_date.isoformat()
            and record.schedule_timezone == timezone
            and record.scheduled_sleep_at is not None
            and record.scheduled_wake_at is not None
        )

    def _store_schedule(
        self,
        *,
        record: DeploymentPresenceRhythmRecord,
        schedule: MaterializedPresenceSchedule,
        now: datetime,
    ) -> None:
        record.schedule_local_date = schedule.local_date.isoformat()
        record.schedule_timezone = schedule.timezone
        record.scheduled_sleep_at = schedule.sleep_at
        record.scheduled_wake_at = schedule.wake_at
        record.updated_at = now

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)

    def _materialize_for_record(
        self,
        *,
        deployment: CharacterDeploymentRecord,
        record: DeploymentPresenceRhythmRecord,
        local_date: date,
        timezone: str,
    ) -> MaterializedPresenceSchedule:
        return self.materialize_schedule(
            deployment_id=deployment.id,
            local_date=local_date,
            timezone=timezone,
            preferred_sleep_start_minute=record.preferred_sleep_start_minute,
            sleep_duration_min_minutes=record.sleep_duration_min_minutes,
            sleep_duration_max_minutes=record.sleep_duration_max_minutes,
            variation_minutes=record.variation_minutes,
            config_version=record.config_version or 0,
        )

    def _schedule_for_now(
        self,
        *,
        deployment: CharacterDeploymentRecord,
        record: DeploymentPresenceRhythmRecord,
        current: datetime,
        timezone: str,
    ) -> MaterializedPresenceSchedule:
        """Select the schedule that owns `current`, including previous-day sleep windows."""

        zone = ZoneInfo(timezone)
        local_date = current.astimezone(zone).date()

        # Prefer a persisted active schedule first. This is important after a process restart
        # between midnight and wake-up: the record can legitimately belong to yesterday.
        if (
            record.schedule_timezone == timezone
            and record.schedule_local_date
            and record.scheduled_sleep_at is not None
            and record.scheduled_wake_at is not None
        ):
            stored_sleep = self._as_utc(record.scheduled_sleep_at)
            stored_wake = self._as_utc(record.scheduled_wake_at)
            if stored_sleep <= current < stored_wake:
                try:
                    stored_date = date.fromisoformat(record.schedule_local_date)
                except ValueError:
                    stored_date = local_date - timedelta(days=1)
                return MaterializedPresenceSchedule(
                    local_date=stored_date,
                    timezone=timezone,
                    sleep_at=stored_sleep,
                    wake_at=stored_wake,
                )

        previous = self._materialize_for_record(
            deployment=deployment,
            record=record,
            local_date=local_date - timedelta(days=1),
            timezone=timezone,
        )
        if previous.sleep_at <= current < previous.wake_at:
            return previous

        today = self._materialize_for_record(
            deployment=deployment,
            record=record,
            local_date=local_date,
            timezone=timezone,
        )
        if current < today.wake_at:
            return today

        return self._materialize_for_record(
            deployment=deployment,
            record=record,
            local_date=local_date + timedelta(days=1),
            timezone=timezone,
        )

    def reconcile_deployment(
        self,
        *,
        owner_id: str,
        deployment_id: str,
        now: datetime | None = None,
    ) -> DeploymentPresenceRhythmView | None:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        with self.database.session() as session:
            deployment = session.get(CharacterDeploymentRecord, deployment_id)
            if deployment is None or deployment.owner_id != owner_id:
                return None
            record = session.get(DeploymentPresenceRhythmRecord, deployment_id)
            if record is None or not record.enabled:
                return self._view(record) if record is not None else None

            timezone = self._deployment_timezone(deployment)
            schedule = self._schedule_for_now(
                deployment=deployment,
                record=record,
                current=current,
                timezone=timezone,
            )
            if not self._stored_schedule_matches(
                record,
                local_date=schedule.local_date,
                timezone=timezone,
            ):
                self._store_schedule(record=record, schedule=schedule, now=current)

            sleep_at = schedule.sleep_at
            wake_at = schedule.wake_at
            if current < sleep_at:
                record.next_transition_at = sleep_at
                record.next_state = "sleeping"
            elif current < wake_at:
                presence = self.presence.get_for_runtime(deployment)
                if presence.state != "sleeping" or presence.source != "rhythm":
                    self.presence.set_state(
                        owner_id=owner_id,
                        deployment_id=deployment_id,
                        state="sleeping",
                        source="rhythm",
                        reason="scheduled_sleep_window",
                        expected_end_at=wake_at,
                        now=current,
                    )
                    record.last_transition_at = current
                    record.last_transition_reason = "scheduled_sleep_window"
                record.next_transition_at = wake_at
                record.next_state = "idle"
            else:
                # Defensive fallback. _schedule_for_now normally returns tomorrow once the
                # current day's wake has passed, so this branch should be unreachable.
                next_schedule = self._materialize_for_record(
                    deployment=deployment,
                    record=record,
                    local_date=current.astimezone(ZoneInfo(timezone)).date() + timedelta(days=1),
                    timezone=timezone,
                )
                self._store_schedule(record=record, schedule=next_schedule, now=current)
                record.next_transition_at = next_schedule.sleep_at
                record.next_state = "sleeping"

            presence = self.presence.get_for_runtime(deployment)
            if (
                current >= wake_at
                and presence.state == "sleeping"
                and presence.source == "rhythm"
            ):
                self.presence.set_state(
                    owner_id=owner_id,
                    deployment_id=deployment_id,
                    state="idle",
                    source="rhythm",
                    reason="scheduled_wake",
                    now=current,
                )
                record.last_transition_at = current
                record.last_transition_reason = "scheduled_wake"

            # When _schedule_for_now has already advanced to a future sleep window, an older
            # rhythm-owned sleep row may still need to be released after a missed wake poll.
            if current < sleep_at:
                presence = self.presence.get_for_runtime(deployment)
                if presence.state == "sleeping" and presence.source == "rhythm":
                    self.presence.set_state(
                        owner_id=owner_id,
                        deployment_id=deployment_id,
                        state="idle",
                        source="rhythm",
                        reason="scheduled_wake",
                        now=current,
                    )
                    record.last_transition_at = current
                    record.last_transition_reason = "scheduled_wake"

            record.updated_at = current
            session.commit()
            session.refresh(record)
            return self._view(record)

    def run_once(self, *, now: datetime | None = None, limit: int = 200) -> int:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        with self.database.session() as session:
            rows = list(
                session.scalars(
                    select(DeploymentPresenceRhythmRecord)
                    .where(DeploymentPresenceRhythmRecord.enabled.is_(True))
                    .order_by(DeploymentPresenceRhythmRecord.updated_at)
                    .limit(max(1, min(limit, 1000)))
                )
            )
            identities = [(row.owner_id, row.deployment_id) for row in rows]
        processed = 0
        for owner_id, deployment_id in identities:
            if self.reconcile_deployment(
                owner_id=owner_id,
                deployment_id=deployment_id,
                now=current,
            ) is not None:
                processed += 1
        return processed


__all__ = [
    "DeploymentPresenceRhythmService",
    "DeploymentPresenceRhythmView",
    "MaterializedPresenceSchedule",
]
