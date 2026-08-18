"""Complete Deployment Discovery runtime from browsing session through bounded social intent."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select

from echo_masque.config import Settings
from echo_masque.credentials import CredentialVault
from echo_masque.deployment_activity import DeploymentBrowsingActivityService
from echo_masque.deployment_discovery_intelligence import RankedDiscoveryCandidate
from echo_masque.deployment_discovery_service import DeploymentDiscoveryPreviewService
from echo_masque.discovery_contracts import DiscoveryAttentionLevel, DiscoveryMode
from echo_masque.discovery_media_inspection import (
    DiscoveryMediaContextService,
    DiscoveryMediaInspectionService,
)
from echo_masque.discovery_share import DiscoveryShareCoordinator, DiscoveryShareDeliveryService
from echo_masque.discovery_social_association import DiscoverySocialAssociationService
from echo_masque.persistence import AuthRepository, KeyGroupRepository, MediaAnalysisRepository
from echo_masque.persistence.database import Database
from echo_masque.persistence.deployment_activity_repository import DeploymentActivitySessionView
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord
from echo_masque.persistence.discovery_models import DeploymentDiscoveryProfileRecord
from echo_masque.provider_credentials import KeyGroupProviderCredentialResolver

logger = logging.getLogger(__name__)
_WATCH_RANK_THRESHOLD = 0.62
_ENGAGE_DEEP_THRESHOLD = 0.78


class CompleteDeploymentDiscoveryActivityService(DeploymentBrowsingActivityService):
    """One Deployment-scoped runtime from leisure session through bounded social intent."""

    def __init__(self, database: Database, settings: Settings) -> None:
        super().__init__(database, settings)
        self.preview_service = DeploymentDiscoveryPreviewService(database, settings)
        vault = CredentialVault(AuthRepository(database), settings)
        media_reader = DiscoveryMediaContextService(
            media_repository=MediaAnalysisRepository(database),
            credential_resolver=KeyGroupProviderCredentialResolver(
                KeyGroupRepository(database),
                vault,
            ),
            discord_bot_token=settings.discord_tool_bot_token,
        )
        self.media_inspection = DiscoveryMediaInspectionService(media_reader, settings)
        self.social_association = DiscoverySocialAssociationService(database, settings)
        self.share_coordinator = DiscoveryShareCoordinator(database, settings)

    def _available_platforms(
        self,
        *,
        profile: DeploymentDiscoveryProfileRecord,
    ) -> tuple[str, ...]:
        values: list[str] = []
        key = self.settings.youtube_data_api_key
        if profile.youtube_enabled and key is not None and key.get_secret_value().strip():
            values.append("youtube")
        if (
            profile.bilibili_enabled
            and self.settings.bilibili_discovery_experimental_enabled
        ):
            values.append("bilibili")
        return tuple(values)

    def _eligible_deployments(self) -> tuple[CharacterDeploymentRecord, ...]:
        with self.database.session() as session:
            pairs = list(
                session.execute(
                    select(CharacterDeploymentRecord, DeploymentDiscoveryProfileRecord)
                    .join(
                        DeploymentDiscoveryProfileRecord,
                        DeploymentDiscoveryProfileRecord.deployment_id
                        == CharacterDeploymentRecord.id,
                    )
                    .where(
                        CharacterDeploymentRecord.platform == "discord",
                        CharacterDeploymentRecord.status == "active",
                        DeploymentDiscoveryProfileRecord.mode.in_(
                            (
                                DiscoveryMode.SHADOW.value,
                                DiscoveryMode.REVIEW.value,
                                DiscoveryMode.AUTO.value,
                            )
                        ),
                    )
                    .order_by(CharacterDeploymentRecord.id)
                )
            )
        return tuple(
            deployment
            for deployment, profile in pairs
            if self._available_platforms(profile=profile)
        )

    def _profile_record(
        self,
        *,
        owner_id: str,
        deployment_id: str,
    ) -> DeploymentDiscoveryProfileRecord | None:
        with self.database.session() as session:
            record = session.get(DeploymentDiscoveryProfileRecord, deployment_id)
            if record is None or record.owner_id != owner_id:
                return None
            return record

    def ensure_daily_schedules(self, *, now: datetime | None = None) -> int:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        count = 0
        for deployment in self._eligible_deployments():
            profile = self._profile_record(
                owner_id=deployment.owner_id,
                deployment_id=deployment.id,
            )
            if profile is None:
                continue
            platforms = self._available_platforms(profile=profile)
            if not platforms:
                continue
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
            index = self._stable_int(
                deployment.id,
                local_date.isoformat(),
                "discovery-platform-v1",
            ) % len(platforms)
            platform = platforms[index]
            record = self.activities.ensure_scheduled(
                owner_id=deployment.owner_id,
                deployment_id=deployment.id,
                platform=platform,
                schedule_key=(
                    f"discovery:{platform}:{deployment.id}:{local_date.isoformat()}:v1"
                ),
                local_date=local_date.isoformat(),
                schedule_timezone=timezone,
                scheduled_start_at=opportunity.scheduled_start_at,
                latest_start_at=opportunity.latest_start_at,
                planned_duration_minutes=opportunity.duration_minutes,
                candidate_budget=self.settings.discovery_activity_candidate_budget,
                open_budget=self.settings.discovery_activity_open_budget,
                watch_budget=(
                    self.settings.discovery_activity_watch_budget
                    if self.settings.discovery_media_inspection_enabled
                    else 0
                ),
                share_intent_budget=(
                    0 if profile.mode == DiscoveryMode.SHADOW.value else 1
                ),
                exploration_percent=self.settings.discovery_activity_exploration_percent,
                now=current,
            )
            count += int(record is not None)
        return count

    def _profile_allows(self, *, owner_id: str, deployment_id: str) -> bool:
        profile = self._profile_record(owner_id=owner_id, deployment_id=deployment_id)
        return bool(
            profile is not None
            and profile.mode
            in {
                DiscoveryMode.SHADOW.value,
                DiscoveryMode.REVIEW.value,
                DiscoveryMode.AUTO.value,
            }
            and self._available_platforms(profile=profile)
        )

    async def _observe_candidates(
        self,
        *,
        owner_id: str,
        session: DeploymentActivitySessionView,
    ) -> None:
        preview = await self.preview_service.run(
            owner_id=owner_id,
            deployment_id=session.deployment_id,
            limit=session.candidate_budget,
            sources=(session.platform,),
        )
        with self.database.session() as db_session:
            deployment = db_session.get(CharacterDeploymentRecord, session.deployment_id)
            if deployment is None or deployment.owner_id != owner_id:
                return
            character_card_id = deployment.character_card_id

        open_remaining = session.open_budget
        share_remaining = session.share_intent_budget
        notice_count = 0
        open_count = 0
        watch_count = 0
        engage_count = 0
        open_candidates: list[tuple[int, RankedDiscoveryCandidate]] = []
        for position, ranked in enumerate(preview.ranked, start=1):
            if open_remaining > 0 and ranked.final_score >= 0.45:
                attention = DiscoveryAttentionLevel.OPEN
                open_remaining -= 1
                open_count += 1
                open_candidates.append((position, ranked))
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

        for position, ranked in open_candidates[: max(0, session.watch_budget)]:
            if ranked.final_score < _WATCH_RANK_THRESHOLD:
                continue
            try:
                inspection = await self.media_inspection.inspect(
                    owner_id=owner_id,
                    character_card_id=character_card_id,
                    url=ranked.candidate.url,
                    seeds=preview.seeds,
                )
            except Exception as exc:
                logger.warning(
                    "Discovery media inspection failed deployment=%s item=%s error=%s",
                    session.deployment_id,
                    ranked.discovery_item_id,
                    exc,
                )
                continue
            if inspection is None:
                continue
            combined = max(
                0.0,
                min(
                    1.0,
                    ranked.final_score * 0.55 + inspection.deep_relevance * 0.45,
                ),
            )
            if inspection.deep_relevance >= _ENGAGE_DEEP_THRESHOLD:
                attention = DiscoveryAttentionLevel.ENGAGE
                engage_count += 1
            else:
                attention = DiscoveryAttentionLevel.WATCH
                watch_count += 1
            open_count = max(0, open_count - 1)
            reason = (
                f"{inspection.reason};source={inspection.source_key};"
                f"deep={inspection.deep_relevance:.3f}"
            )
            self.activities.record_item(
                owner_id=owner_id,
                deployment_id=session.deployment_id,
                session_id=session.id,
                discovery_item_id=ranked.discovery_item_id,
                rank_position=position,
                attention_level=attention.value,
                score=combined,
                reason=reason,
            )
            self.discovery.record_exposure(
                owner_id=owner_id,
                deployment_id=session.deployment_id,
                discovery_item_id=ranked.discovery_item_id,
                attention_level=attention,
                interest_score=combined,
                subjective_reason=f"activity_session:{session.id};{reason}",
                increment_count=False,
            )
            try:
                association = self.social_association.evaluate(
                    owner_id=owner_id,
                    deployment_id=session.deployment_id,
                    discovery_item_id=ranked.discovery_item_id,
                )
                if (
                    association is not None
                    and association.would_share
                    and share_remaining > 0
                ):
                    proposal = await self.share_coordinator.maybe_propose(
                        owner_id=owner_id,
                        deployment_id=session.deployment_id,
                        discovery_item_id=ranked.discovery_item_id,
                        association=association,
                    )
                    if proposal is not None:
                        share_remaining -= 1
            except Exception as exc:
                logger.warning(
                    "Discovery social/share planning failed deployment=%s item=%s error=%s",
                    session.deployment_id,
                    ranked.discovery_item_id,
                    exc,
                )

        self.activities.update_counters(
            owner_id=owner_id,
            session_id=session.id,
            candidate_count=len(preview.ranked),
            notice_count=notice_count,
            open_count=open_count,
            watch_count=watch_count,
            engage_count=engage_count,
            reason=(
                "browsing_completed_with_social_intent"
                if watch_count or engage_count
                else "browsing_candidates_observed"
            ),
        )

    async def run_manual_discovery(
        self,
        *,
        owner_id: str,
        deployment_id: str,
        platform: str = "",
        allow_sharing: bool = False,
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
        profile = self._profile_record(owner_id=owner_id, deployment_id=deployment_id)
        if profile is None or profile.mode == DiscoveryMode.OFF.value:
            raise ValueError("Discovery is not enabled for this Deployment.")
        platforms = self._available_platforms(profile=profile)
        selected = platform.casefold().strip() or (platforms[0] if platforms else "")
        if selected not in platforms:
            raise ValueError(f"Discovery source {selected or 'none'} is unavailable.")
        activity = self.activities.create_manual(
            owner_id=owner_id,
            deployment_id=deployment_id,
            platform=selected,
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
            watch_budget=(
                self.settings.discovery_activity_watch_budget
                if self.settings.discovery_media_inspection_enabled
                else 0
            ),
            share_intent_budget=(
                1
                if allow_sharing and profile.mode != DiscoveryMode.SHADOW.value
                else 0
            ),
            exploration_percent=self.settings.discovery_activity_exploration_percent,
            now=current,
        )
        if activity is None:
            raise KeyError("deployment")
        result = await self.run_session(activity, now=current)
        if result is None:
            raise RuntimeError("Discovery browsing session could not be started.")
        return result


def upgrade_discovery_activity_service(
    service: DeploymentBrowsingActivityService,
) -> CompleteDeploymentDiscoveryActivityService | DeploymentBrowsingActivityService:
    if isinstance(service, CompleteDeploymentDiscoveryActivityService):
        return service
    if not service.settings.discovery_complete_runtime_enabled:
        return service
    return CompleteDeploymentDiscoveryActivityService(service.database, service.settings)


def build_discovery_share_delivery(
    service: DeploymentBrowsingActivityService,
) -> DiscoveryShareDeliveryService | None:
    if not service.settings.discovery_complete_runtime_enabled:
        return None
    return DiscoveryShareDeliveryService(service.database, service.settings)


__all__ = [
    "CompleteDeploymentDiscoveryActivityService",
    "build_discovery_share_delivery",
    "upgrade_discovery_activity_service",
]
