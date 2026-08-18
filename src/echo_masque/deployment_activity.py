"""Deployment-scoped browsing Activity Runtime for Character Discovery."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo

from sqlalchemy import select

from echo_masque.config import Settings
from echo_masque.deployment_discovery_service import (
    DeploymentDiscoveryPreview,
    DeploymentDiscoveryPreviewService,
)
from echo_masque.discovery_contracts import DiscoveryAttentionLevel, DiscoveryMode
from echo_masque.persistence.database import Database
from echo_masque.persistence.deployment_activity_repository import (
    DeploymentActivityRepository,
    DeploymentActivitySessionView,
)
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord
from echo_masque.persistence.deployment_presence_repository import DeploymentPresenceRepository
from echo_masque.persistence.discovery_models import DeploymentDiscoveryProfileRecord
from echo_masque.persistence.discovery_repository import DiscoveryRepository
from echo_masque.persistence.server_runtime_repository import ServerRuntimeRepository

logger = logging.getLogger(__name__)
_ACTIVITY_ALGORITHM_VERSION = 1


class DiscoveryPreviewRunner(Protocol):
    async def run(
        self,
        *,
        owner_id: str,
        deployment_id: str,
        region: str = "",
        language: str = "",
        limit: int = 10,
    ) -> DeploymentDiscoveryPreview: ...


@dataclass(frozen=True, slots=True)
class MaterializedBrowsingOpportunity:
    deployment_id: str
    local_date: date
    timezone: str
    should_browse: bool
    scheduled_start_at: datetime | None
    latest_start_at: datetime | None
    duration_minutes: int


class DeploymentBrowsingActivityService:
    """Create and run bounded browsing sessions without Character-model participation."""

    def __init__(
        self,
        database: Database,
        settings: Settings,
        *,
        preview: DiscoveryPreviewRunner | None = None,
    ) -> None:
        self.database = database
        self.settings = settings
        self.activities = DeploymentActivityRepository(database)
        self.presence = DeploymentPresenceRepository(database)
        self.discovery = DiscoveryRepository(database)
        self.server_runtime = ServerRuntimeRepository(database)
        self.preview = preview or DeploymentDiscoveryPreviewService(database, settings)

    @staticmethod
    def _stable_int(*parts: object) -> int:
        digest = hashlib.sha256("|".join(str(part) for part in parts).encode()).digest()
        return int.from_bytes(digest[:8], "big", signed=False)

    @staticmethod
    def _aware(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @staticmethod
    def _local_at_minute(local_date: date, minute: int, zone: ZoneInfo) -> datetime:
        bounded = max(0, min(minute, 1440))
        if bounded == 1440:
            return datetime.combine(local_date + timedelta(days=1), time.min, tzinfo=zone)
        return datetime.combine(
            local_date,
            time(hour=bounded // 60, minute=bounded % 60),
            tzinfo=zone,
        )

    def materialize_opportunity(
        self,
        *,
        deployment_id: str,
        local_date: date,
        timezone: str,
    ) -> MaterializedBrowsingOpportunity:
        probability = self.settings.discovery_activity_session_probability_percent
        roll = self._stable_int(
            deployment_id,
            local_date.isoformat(),
            _ACTIVITY_ALGORITHM_VERSION,
            "browse-probability",
        ) % 100
        should_browse = roll < probability

        duration_min = self.settings.discovery_activity_duration_min_minutes
        duration_max = max(
            duration_min,
            self.settings.discovery_activity_duration_max_minutes,
        )
        duration_span = duration_max - duration_min
        duration = duration_min
        if duration_span:
            duration += self._stable_int(
                deployment_id,
                local_date.isoformat(),
                _ACTIVITY_ALGORITHM_VERSION,
                "browse-duration",
            ) % (duration_span + 1)

        if not should_browse:
            return MaterializedBrowsingOpportunity(
                deployment_id=deployment_id,
                local_date=local_date,
                timezone=timezone,
                should_browse=False,
                scheduled_start_at=None,
                latest_start_at=None,
                duration_minutes=duration,
            )

        start_minute = self.settings.discovery_activity_window_start_minute
        end_minute = self.settings.discovery_activity_window_end_minute
        if end_minute <= start_minute:
            end_minute = min(1440, start_minute + 60)
        span = max(1, end_minute - start_minute)
        minute = start_minute + self._stable_int(
            deployment_id,
            local_date.isoformat(),
            _ACTIVITY_ALGORITHM_VERSION,
            "browse-start",
        ) % span
        zone = ZoneInfo(timezone)
        local_start = self._local_at_minute(local_date, minute, zone)
        local_window_end = self._local_at_minute(local_date, end_minute, zone)
        latest = min(
            local_start
            + timedelta(minutes=self.settings.discovery_activity_latest_start_delay_minutes),
            local_window_end,
        )
        return MaterializedBrowsingOpportunity(
            deployment_id=deployment_id,
            local_date=local_date,
            timezone=timezone,
            should_browse=True,
            scheduled_start_at=local_start.astimezone(UTC),
            latest_start_at=latest.astimezone(UTC),
            duration_minutes=duration,
        )

    def _eligible_deployments(self) -> tuple[CharacterDeploymentRecord, ...]:
        if self.settings.youtube_data_api_key is None:
            return ()
        if not self.settings.youtube_data_api_key.get_secret_value().strip():
            return ()
        with self.database.session() as session:
            return tuple(
                session.scalars(
                    select(CharacterDeploymentRecord)
                    .join(
                        DeploymentDiscoveryProfileRecord,
                        DeploymentDiscoveryProfileRecord.deployment_id
                        == CharacterDeploymentRecord.id,
                    )
                    .where(
                        CharacterDeploymentRecord.platform == "discord",
                        CharacterDeploymentRecord.status == "active",
                        DeploymentDiscoveryProfileRecord.mode == DiscoveryMode.SHADOW.value,
                        DeploymentDiscoveryProfileRecord.youtube_enabled.is_(True),
                    )
                    .order_by(CharacterDeploymentRecord.id)
                )
            )

    def ensure_daily_schedules(self, *, now: datetime | None = None) -> int:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        created_or_existing = 0
        for deployment in self._eligible_deployments():
            timezone = self.server_runtime.resolve_timezone(
                owner_id=deployment.owner_id,
                connection_id=deployment.connection_id,
                guild_id=deployment.workspace_id,
            )
            local_date = current.astimezone(ZoneInfo(timezone)).date()
            opportunity = self.materialize_opportunity(
                deployment_id=deployment.id,
                local_date=local_date,
                timezone=timezone,
            )
            if (
                not opportunity.should_browse
                or opportunity.scheduled_start_at is None
                or opportunity.latest_start_at is None
            ):
                continue
            schedule_key = (
                f"discovery:youtube:{deployment.id}:{local_date.isoformat()}:"
                f"v{_ACTIVITY_ALGORITHM_VERSION}"
            )
            record = self.activities.ensure_scheduled(
                owner_id=deployment.owner_id,
                deployment_id=deployment.id,
                platform="youtube",
                schedule_key=schedule_key,
                local_date=local_date.isoformat(),
                schedule_timezone=timezone,
                scheduled_start_at=opportunity.scheduled_start_at,
                latest_start_at=opportunity.latest_start_at,
                planned_duration_minutes=opportunity.duration_minutes,
                candidate_budget=self.settings.discovery_activity_candidate_budget,
                open_budget=self.settings.discovery_activity_open_budget,
                watch_budget=self.settings.discovery_activity_watch_budget,
                share_intent_budget=0,
                exploration_percent=self.settings.discovery_activity_exploration_percent,
                now=current,
            )
            if record is not None:
                created_or_existing += 1
        return created_or_existing

    @staticmethod
    def _owns_presence(session: DeploymentActivitySessionView, source: str, reason: str) -> bool:
        return source == "discovery_activity" and reason == f"activity_session:{session.id}"

    def _restore_idle_if_owned(
        self,
        session: DeploymentActivitySessionView,
        *,
        now: datetime,
    ) -> None:
        presence = self.presence.get(
            owner_id=self._owner_id(session),
            deployment_id=session.deployment_id,
        )
        if (
            presence is not None
            and presence.state == "browsing"
            and self._owns_presence(session, presence.source, presence.reason)
        ):
            self.presence.set_state(
                owner_id=presence.owner_id,
                deployment_id=session.deployment_id,
                state="idle",
                source="discovery_activity",
                reason=f"activity_session_completed:{session.id}",
                now=now,
            )

    def _owner_id(self, session: DeploymentActivitySessionView) -> str:
        with self.database.session() as db_session:
            deployment = db_session.get(CharacterDeploymentRecord, session.deployment_id)
            return deployment.owner_id if deployment is not None else ""

    def _profile_allows(self, *, owner_id: str, deployment_id: str) -> bool:
        profile = self.discovery.get_profile(owner_id=owner_id, deployment_id=deployment_id)
        return bool(
            profile is not None
            and profile.mode is DiscoveryMode.SHADOW
            and profile.youtube_enabled
        )

    async def _observe_candidates(
        self,
        *,
        owner_id: str,
        session: DeploymentActivitySessionView,
    ) -> None:
        preview = await self.preview.run(
            owner_id=owner_id,
            deployment_id=session.deployment_id,
            limit=session.candidate_budget,
        )
        open_remaining = session.open_budget
        notice_count = 0
        open_count = 0
        for position, ranked in enumerate(preview.ranked, start=1):
            if open_remaining > 0 and ranked.final_score >= 0.45:
                attention = DiscoveryAttentionLevel.OPEN
                open_remaining -= 1
                open_count += 1
            elif ranked.final_score >= 0.32:
                attention = DiscoveryAttentionLevel.NOTICE
                notice_count += 1
            else:
                attention = DiscoveryAttentionLevel.SCROLL_PAST
            self.activities.record_item(
                owner_id=owner_id,
                deployment_id=session.deployment_id,
                session_id=session.id,
                discovery_item_id=ranked.discovery_item_id,
                rank_position=position,
                attention_level=attention.value,
                score=ranked.final_score,
                reason=ranked.reason,
            )
            self.discovery.record_exposure(
                owner_id=owner_id,
                deployment_id=session.deployment_id,
                discovery_item_id=ranked.discovery_item_id,
                attention_level=attention,
                interest_score=ranked.final_score,
                subjective_reason=(
                    f"activity_session:{session.id};rank_reason:{ranked.reason}"
                ),
            )
        self.activities.update_counters(
            owner_id=owner_id,
            session_id=session.id,
            candidate_count=len(preview.ranked),
            notice_count=notice_count,
            open_count=open_count,
            # WATCH/ENGAGE remain reserved for selective Media Understanding in Phase 7.
            watch_count=0,
            engage_count=0,
        )

    async def run_session(
        self,
        session: DeploymentActivitySessionView,
        *,
        now: datetime | None = None,
    ) -> DeploymentActivitySessionView | None:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        owner_id = self._owner_id(session)
        if not owner_id:
            return None
        refreshed = self.activities.get(owner_id=owner_id, session_id=session.id)
        if refreshed is None or refreshed.status != "scheduled":
            return refreshed
        latest_start = self._aware(refreshed.latest_start_at)
        if latest_start is not None and current > latest_start:
            return self.activities.finish(
                owner_id=owner_id,
                session_id=refreshed.id,
                status="skipped",
                reason="leisure_window_expired",
                now=current,
            )
        if not self._profile_allows(owner_id=owner_id, deployment_id=refreshed.deployment_id):
            return self.activities.finish(
                owner_id=owner_id,
                session_id=refreshed.id,
                status="skipped",
                reason="discovery_profile_no_longer_allows_browsing",
                now=current,
            )
        presence = self.presence.get(owner_id=owner_id, deployment_id=refreshed.deployment_id)
        if presence is None:
            return None
        if presence.state in {"sleeping", "busy"}:
            return refreshed
        if presence.state == "browsing":
            return refreshed
        if self.activities.active_for_deployment(
            owner_id=owner_id,
            deployment_id=refreshed.deployment_id,
        ) is not None:
            return refreshed

        expected_end = current + timedelta(minutes=refreshed.planned_duration_minutes)
        active = self.activities.start(
            owner_id=owner_id,
            session_id=refreshed.id,
            expected_end_at=expected_end,
            now=current,
        )
        if active is None or active.status != "active":
            return active
        self.presence.set_state(
            owner_id=owner_id,
            deployment_id=active.deployment_id,
            state="browsing",
            activity_type=active.platform,
            source="discovery_activity",
            reason=f"activity_session:{active.id}",
            expected_end_at=expected_end,
            now=current,
        )
        try:
            await self._observe_candidates(owner_id=owner_id, session=active)
        except Exception as exc:
            logger.warning(
                "Discovery browsing session failed deployment=%s session=%s error=%s",
                active.deployment_id,
                active.id,
                exc,
            )
            failed = self.activities.finish(
                owner_id=owner_id,
                session_id=active.id,
                status="failed",
                reason="candidate_collection_failed",
                error=str(exc),
                now=current,
            )
            self._restore_idle_if_owned(active, now=current)
            return failed
        return self.activities.get(owner_id=owner_id, session_id=active.id)

    def reconcile_active_sessions(self, *, now: datetime | None = None) -> int:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        processed = 0
        for activity in self.activities.list_active():
            owner_id = self._owner_id(activity)
            if not owner_id:
                continue
            presence = self.presence.get(
                owner_id=owner_id,
                deployment_id=activity.deployment_id,
            )
            if presence is None:
                continue
            expected_end = self._aware(activity.expected_end_at)
            if presence.state in {"sleeping", "busy"}:
                self.activities.finish(
                    owner_id=owner_id,
                    session_id=activity.id,
                    status="cancelled",
                    reason=f"interrupted_by_presence:{presence.state}",
                    now=current,
                )
                processed += 1
                continue
            if expected_end is not None and current >= expected_end:
                self.activities.finish(
                    owner_id=owner_id,
                    session_id=activity.id,
                    status="completed",
                    reason="planned_browsing_window_completed",
                    now=current,
                )
                self._restore_idle_if_owned(activity, now=current)
                processed += 1
                continue
            if presence.state == "idle":
                self.presence.set_state(
                    owner_id=owner_id,
                    deployment_id=activity.deployment_id,
                    state="browsing",
                    activity_type=activity.platform,
                    source="discovery_activity",
                    reason=f"activity_session:{activity.id}",
                    expected_end_at=expected_end,
                    now=current,
                )
                processed += 1
                continue
            if presence.state == "browsing" and not self._owns_presence(
                activity,
                presence.source,
                presence.reason,
            ):
                self.activities.finish(
                    owner_id=owner_id,
                    session_id=activity.id,
                    status="cancelled",
                    reason="superseded_by_other_browsing_activity",
                    now=current,
                )
                processed += 1
        return processed

    async def run_manual(
        self,
        *,
        owner_id: str,
        deployment_id: str,
        duration_minutes: int | None = None,
        candidate_budget: int | None = None,
        open_budget: int | None = None,
        now: datetime | None = None,
    ) -> DeploymentActivitySessionView:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        presence = self.presence.get(owner_id=owner_id, deployment_id=deployment_id)
        if presence is None:
            raise KeyError("deployment")
        if presence.state != "idle":
            raise ValueError(f"Browsing requires IDLE Presence; current={presence.state}.")
        if not self._profile_allows(owner_id=owner_id, deployment_id=deployment_id):
            raise ValueError("Browsing requires YouTube Discovery mode=shadow and enabled.")
        activity = self.activities.create_manual(
            owner_id=owner_id,
            deployment_id=deployment_id,
            platform="youtube",
            planned_duration_minutes=(
                duration_minutes or self.settings.discovery_activity_duration_min_minutes
            ),
            candidate_budget=(
                candidate_budget or self.settings.discovery_activity_candidate_budget
            ),
            open_budget=(
                open_budget
                if open_budget is not None
                else self.settings.discovery_activity_open_budget
            ),
            watch_budget=self.settings.discovery_activity_watch_budget,
            share_intent_budget=0,
            exploration_percent=self.settings.discovery_activity_exploration_percent,
            now=current,
        )
        if activity is None:
            raise KeyError("deployment")
        result = await self.run_session(activity, now=current)
        if result is None:
            raise RuntimeError("Browsing session could not be started.")
        return result

    async def run_once(self, *, now: datetime | None = None) -> int:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        processed = self.reconcile_active_sessions(now=current)
        self.ensure_daily_schedules(now=current)
        for activity in self.activities.list_due_scheduled(now=current):
            before = activity.status
            result = await self.run_session(activity, now=current)
            if result is not None and result.status != before:
                processed += 1
        return processed


__all__ = [
    "DeploymentBrowsingActivityService",
    "DiscoveryPreviewRunner",
    "MaterializedBrowsingOpportunity",
]
