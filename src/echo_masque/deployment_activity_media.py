"""Media-aware promotion layer for Deployment browsing Activity Sessions."""

from __future__ import annotations

from typing import Protocol

from sqlalchemy import select

from echo_masque.config import Settings
from echo_masque.deployment_activity import (
    DeploymentBrowsingActivityService,
    DiscoveryPreviewRunner,
)
from echo_masque.deployment_discovery_intelligence import DeploymentDiscoverySeeds
from echo_masque.deployment_discovery_seeds_v3 import DeploymentDiscoverySeedBuilderV3
from echo_masque.discovery_contracts import DiscoveryAttentionLevel
from echo_masque.discovery_media_inspection import DiscoveryMediaInspection
from echo_masque.persistence.database import Database
from echo_masque.persistence.deployment_activity_repository import DeploymentActivitySessionView
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord
from echo_masque.persistence.discovery_models import DiscoveryItemRecord

_WATCH_RANK_THRESHOLD = 0.62
_ENGAGE_DEEP_THRESHOLD = 0.78


class DiscoveryMediaInspector(Protocol):
    async def inspect(
        self,
        *,
        owner_id: str,
        character_card_id: str,
        url: str,
        seeds: DeploymentDiscoverySeeds,
    ) -> DiscoveryMediaInspection | None: ...


class MediaAwareDeploymentBrowsingActivityService(DeploymentBrowsingActivityService):
    """Promote a small OPEN shortlist after real existing-runtime media inspection."""

    def __init__(
        self,
        database: Database,
        settings: Settings,
        *,
        media_inspector: DiscoveryMediaInspector,
        preview: DiscoveryPreviewRunner | None = None,
    ) -> None:
        super().__init__(database, settings, preview=preview)
        self.media_inspector = media_inspector
        self.seed_builder = DeploymentDiscoverySeedBuilderV3(database)

    async def _observe_candidates(
        self,
        *,
        owner_id: str,
        session: DeploymentActivitySessionView,
    ) -> None:
        await super()._observe_candidates(owner_id=owner_id, session=session)
        if session.watch_budget <= 0:
            return

        seeds = self.seed_builder.build(
            owner_id=owner_id,
            deployment_id=session.deployment_id,
        )
        if seeds is None or not seeds.seeds:
            return
        with self.database.session() as db_session:
            deployment = db_session.get(CharacterDeploymentRecord, session.deployment_id)
            if deployment is None or deployment.owner_id != owner_id:
                return
            session_items = self.activities.list_items(
                owner_id=owner_id,
                session_id=session.id,
            )
            open_items = [
                item
                for item in session_items
                if item.attention_level == DiscoveryAttentionLevel.OPEN.value
                and item.score >= _WATCH_RANK_THRESHOLD
            ][: session.watch_budget]
            if not open_items:
                return
            content_by_id = {
                record.id: record
                for record in db_session.scalars(
                    select(DiscoveryItemRecord).where(
                        DiscoveryItemRecord.id.in_(
                            [item.discovery_item_id for item in open_items]
                        )
                    )
                )
            }
            character_card_id = deployment.character_card_id

        watch_count = 0
        engage_count = 0
        for item in open_items:
            content = content_by_id.get(item.discovery_item_id)
            if content is None or not content.url:
                continue
            inspection = await self.media_inspector.inspect(
                owner_id=owner_id,
                character_card_id=character_card_id,
                url=content.url,
                seeds=seeds,
            )
            if inspection is None:
                continue
            combined_score = max(
                0.0,
                min(1.0, item.score * 0.55 + inspection.deep_relevance * 0.45),
            )
            if inspection.deep_relevance >= _ENGAGE_DEEP_THRESHOLD:
                attention = DiscoveryAttentionLevel.ENGAGE
                engage_count += 1
            else:
                attention = DiscoveryAttentionLevel.WATCH
                watch_count += 1
            short_reason = (
                f"{inspection.reason};source={inspection.source_key};"
                f"deep={inspection.deep_relevance:.3f}"
            )
            self.activities.record_item(
                owner_id=owner_id,
                deployment_id=session.deployment_id,
                session_id=session.id,
                discovery_item_id=item.discovery_item_id,
                rank_position=item.rank_position,
                attention_level=attention.value,
                score=combined_score,
                reason=short_reason,
            )
            self.discovery.record_exposure(
                owner_id=owner_id,
                deployment_id=session.deployment_id,
                discovery_item_id=item.discovery_item_id,
                attention_level=attention,
                interest_score=combined_score,
                subjective_reason=f"activity_session:{session.id};{short_reason}",
                increment_count=False,
            )

        current = self.activities.get(owner_id=owner_id, session_id=session.id)
        if current is None:
            return
        self.activities.update_counters(
            owner_id=owner_id,
            session_id=session.id,
            candidate_count=current.candidate_count,
            notice_count=current.notice_count,
            open_count=max(0, current.open_count - watch_count - engage_count),
            watch_count=watch_count,
            engage_count=engage_count,
            reason="browsing_media_shortlist_inspected",
        )


__all__ = [
    "DiscoveryMediaInspector",
    "MediaAwareDeploymentBrowsingActivityService",
]
