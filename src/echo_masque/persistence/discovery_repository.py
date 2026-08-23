"""Persistence boundary for shared Discovery content and Deployment-scoped experience."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import uuid4

from sqlalchemy import and_, delete, exists, or_, select
from sqlalchemy.engine import CursorResult

from echo_masque.discovery_contracts import (
    DiscoveryAttentionLevel,
    DiscoveryCandidate,
    DiscoveryDecision,
    DiscoveryMode,
)
from echo_masque.pagination import decode_time_cursor, encode_time_cursor
from echo_masque.persistence.database import Database
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord
from echo_masque.persistence.discovery_models import (
    DeploymentDiscoveryDecisionRecord,
    DeploymentDiscoveryExposureRecord,
    DeploymentDiscoveryProfileRecord,
    DiscoveryItemRecord,
)

_ATTENTION_RANK = {
    DiscoveryAttentionLevel.SCROLL_PAST.value: 0,
    DiscoveryAttentionLevel.NOTICE.value: 1,
    DiscoveryAttentionLevel.OPEN.value: 2,
    DiscoveryAttentionLevel.WATCH.value: 3,
    DiscoveryAttentionLevel.ENGAGE.value: 4,
}


@dataclass(frozen=True, slots=True)
class DiscoveryProfileView:
    deployment_id: str
    mode: DiscoveryMode
    youtube_enabled: bool
    bilibili_enabled: bool


class DiscoveryRepository:
    """Keep objective content reusable while subjective experience stays Deployment-scoped."""

    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def _json(value: dict[str, Any]) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    def get_profile(self, *, owner_id: str, deployment_id: str) -> DiscoveryProfileView | None:
        with self.database.session() as session:
            deployment = session.get(CharacterDeploymentRecord, deployment_id)
            if deployment is None or deployment.owner_id != owner_id:
                return None
            record = session.get(DeploymentDiscoveryProfileRecord, deployment_id)
            if record is None:
                return DiscoveryProfileView(
                    deployment_id=deployment_id,
                    mode=DiscoveryMode.OFF,
                    youtube_enabled=False,
                    bilibili_enabled=False,
                )
            return DiscoveryProfileView(
                deployment_id=record.deployment_id,
                mode=DiscoveryMode(record.mode),
                youtube_enabled=record.youtube_enabled,
                bilibili_enabled=record.bilibili_enabled,
            )

    def set_profile(
        self,
        *,
        owner_id: str,
        deployment_id: str,
        mode: DiscoveryMode,
        youtube_enabled: bool,
        bilibili_enabled: bool,
    ) -> DiscoveryProfileView | None:
        with self.database.session() as session:
            deployment = session.get(CharacterDeploymentRecord, deployment_id)
            if deployment is None or deployment.owner_id != owner_id:
                return None
            record = session.get(DeploymentDiscoveryProfileRecord, deployment_id)
            if record is None:
                record = DeploymentDiscoveryProfileRecord(
                    deployment_id=deployment_id,
                    owner_id=owner_id,
                )
                session.add(record)
            record.mode = mode.value
            record.youtube_enabled = bool(youtube_enabled)
            # Bilibili remains disabled unless the explicitly experimental adapter is enabled.
            record.bilibili_enabled = bool(bilibili_enabled)
            session.commit()
            session.refresh(record)
        return self.get_profile(owner_id=owner_id, deployment_id=deployment_id)

    def upsert_item(
        self,
        candidate: DiscoveryCandidate,
        *,
        ttl: timedelta = timedelta(days=7),
        now: datetime | None = None,
    ) -> DiscoveryItemRecord:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        source = candidate.source.strip().casefold()[:32]
        canonical_key = candidate.canonical_key.strip()[:500]
        if not source or not canonical_key:
            raise ValueError("Discovery candidate requires source and canonical_key.")
        with self.database.session() as session:
            record = session.scalar(
                select(DiscoveryItemRecord).where(
                    DiscoveryItemRecord.source == source,
                    DiscoveryItemRecord.canonical_key == canonical_key,
                )
            )
            if record is None:
                record = DiscoveryItemRecord(
                    id=str(uuid4()),
                    source=source,
                    canonical_key=canonical_key,
                    first_seen_at=current,
                )
                session.add(record)
            record.content_kind = candidate.content_kind.strip()[:32] or "unknown"
            record.title = candidate.title.strip()[:2000]
            record.description = candidate.description.strip()[:12000]
            record.creator = candidate.creator.strip()[:240]
            record.url = candidate.url.strip()[:4000]
            record.thumbnail_url = candidate.thumbnail_url.strip()[:4000]
            record.published_at = candidate.published_at
            record.metadata_json = self._json(candidate.metadata)
            record.last_seen_at = current
            record.expires_at = current + max(ttl, timedelta(hours=1))
            record.updated_at = current
            session.commit()
            session.refresh(record)
            return record

    def record_exposure(
        self,
        *,
        owner_id: str,
        deployment_id: str,
        discovery_item_id: str,
        attention_level: DiscoveryAttentionLevel,
        interest_score: float = 0.0,
        subjective_reason: str = "",
        increment_count: bool = True,
        now: datetime | None = None,
    ) -> DeploymentDiscoveryExposureRecord | None:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        with self.database.session() as session:
            deployment = session.get(CharacterDeploymentRecord, deployment_id)
            item = session.get(DiscoveryItemRecord, discovery_item_id)
            if deployment is None or deployment.owner_id != owner_id or item is None:
                return None
            record = session.scalar(
                select(DeploymentDiscoveryExposureRecord).where(
                    DeploymentDiscoveryExposureRecord.deployment_id == deployment_id,
                    DeploymentDiscoveryExposureRecord.discovery_item_id == discovery_item_id,
                )
            )
            score = max(-1.0, min(float(interest_score), 1.0))
            if record is None:
                record = DeploymentDiscoveryExposureRecord(
                    id=str(uuid4()),
                    owner_id=owner_id,
                    deployment_id=deployment_id,
                    discovery_item_id=discovery_item_id,
                    attention_level=attention_level.value,
                    interest_score=score,
                    subjective_reason=subjective_reason.strip()[:2000],
                    exposure_count=1,
                    first_exposed_at=current,
                    last_exposed_at=current,
                    updated_at=current,
                )
                session.add(record)
            else:
                if _ATTENTION_RANK[attention_level.value] > _ATTENTION_RANK.get(
                    record.attention_level, -1
                ):
                    record.attention_level = attention_level.value
                record.interest_score = score
                record.subjective_reason = subjective_reason.strip()[:2000]
                if increment_count:
                    record.exposure_count += 1
                    record.last_exposed_at = current
                record.updated_at = current
            session.commit()
            session.refresh(record)
            return record

    def record_decision(
        self,
        *,
        owner_id: str,
        deployment_id: str,
        discovery_item_id: str,
        mode: DiscoveryMode,
        decision: DiscoveryDecision,
        motivation: str = "",
        confidence: float = 0.0,
        scores: dict[str, Any] | None = None,
        evidence: dict[str, Any] | None = None,
        now: datetime | None = None,
    ) -> DeploymentDiscoveryDecisionRecord | None:
        # Shadow mode is structurally incapable of recording an executed/proposed side effect.
        if mode is DiscoveryMode.SHADOW and decision in {
            DiscoveryDecision.PROPOSE_SHARE,
            DiscoveryDecision.SHARE,
        }:
            raise ValueError("Shadow Discovery cannot propose or execute a share.")
        current = (now or datetime.now(UTC)).astimezone(UTC)
        with self.database.session() as session:
            deployment = session.get(CharacterDeploymentRecord, deployment_id)
            item = session.get(DiscoveryItemRecord, discovery_item_id)
            exposure = session.scalar(
                select(DeploymentDiscoveryExposureRecord.id).where(
                    DeploymentDiscoveryExposureRecord.deployment_id == deployment_id,
                    DeploymentDiscoveryExposureRecord.discovery_item_id == discovery_item_id,
                )
            )
            if (
                deployment is None
                or deployment.owner_id != owner_id
                or item is None
                or exposure is None
            ):
                return None
            record = DeploymentDiscoveryDecisionRecord(
                id=str(uuid4()),
                owner_id=owner_id,
                deployment_id=deployment_id,
                discovery_item_id=discovery_item_id,
                mode=mode.value,
                decision=decision.value,
                motivation=motivation.strip()[:64],
                confidence=max(0.0, min(float(confidence), 1.0)),
                scores_json=self._json(scores or {}),
                evidence_json=self._json(evidence or {}),
                created_at=current,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def list_exposures(
        self,
        *,
        owner_id: str,
        deployment_id: str,
        limit: int = 100,
    ) -> tuple[DeploymentDiscoveryExposureRecord, ...]:
        with self.database.session() as session:
            return tuple(
                session.scalars(
                    select(DeploymentDiscoveryExposureRecord)
                    .where(
                        DeploymentDiscoveryExposureRecord.owner_id == owner_id,
                        DeploymentDiscoveryExposureRecord.deployment_id == deployment_id,
                    )
                    .order_by(DeploymentDiscoveryExposureRecord.last_exposed_at.desc())
                    .limit(max(1, min(limit, 500)))
                )
            )

    def list_exposures_page(
        self,
        *,
        owner_id: str,
        deployment_id: str,
        limit: int = 100,
        cursor: str | None = None,
    ) -> tuple[tuple[DeploymentDiscoveryExposureRecord, ...], str | None]:
        bounded_limit = max(1, min(limit, 500))
        with self.database.session() as session:
            query = select(DeploymentDiscoveryExposureRecord).where(
                DeploymentDiscoveryExposureRecord.owner_id == owner_id,
                DeploymentDiscoveryExposureRecord.deployment_id == deployment_id,
            )
            if cursor:
                last_exposed_at, identifier = decode_time_cursor(cursor)
                query = query.where(
                    or_(
                        DeploymentDiscoveryExposureRecord.last_exposed_at < last_exposed_at,
                        and_(
                            DeploymentDiscoveryExposureRecord.last_exposed_at == last_exposed_at,
                            DeploymentDiscoveryExposureRecord.id < identifier,
                        ),
                    )
                )
            records = list(
                session.scalars(
                    query.order_by(
                        DeploymentDiscoveryExposureRecord.last_exposed_at.desc(),
                        DeploymentDiscoveryExposureRecord.id.desc(),
                    ).limit(bounded_limit + 1)
                )
            )
        has_more = len(records) > bounded_limit
        items = records[:bounded_limit]
        next_cursor = (
            encode_time_cursor(items[-1].last_exposed_at, items[-1].id)
            if has_more and items
            else None
        )
        return tuple(items), next_cursor

    def list_decisions(
        self,
        *,
        owner_id: str,
        deployment_id: str,
        limit: int = 100,
    ) -> tuple[DeploymentDiscoveryDecisionRecord, ...]:
        with self.database.session() as session:
            return tuple(
                session.scalars(
                    select(DeploymentDiscoveryDecisionRecord)
                    .where(
                        DeploymentDiscoveryDecisionRecord.owner_id == owner_id,
                        DeploymentDiscoveryDecisionRecord.deployment_id == deployment_id,
                    )
                    .order_by(DeploymentDiscoveryDecisionRecord.created_at.desc())
                    .limit(max(1, min(limit, 500)))
                )
            )

    def list_decisions_page(
        self,
        *,
        owner_id: str,
        deployment_id: str,
        limit: int = 100,
        cursor: str | None = None,
    ) -> tuple[tuple[DeploymentDiscoveryDecisionRecord, ...], str | None]:
        bounded_limit = max(1, min(limit, 500))
        with self.database.session() as session:
            query = select(DeploymentDiscoveryDecisionRecord).where(
                DeploymentDiscoveryDecisionRecord.owner_id == owner_id,
                DeploymentDiscoveryDecisionRecord.deployment_id == deployment_id,
            )
            if cursor:
                created_at, identifier = decode_time_cursor(cursor)
                query = query.where(
                    or_(
                        DeploymentDiscoveryDecisionRecord.created_at < created_at,
                        and_(
                            DeploymentDiscoveryDecisionRecord.created_at == created_at,
                            DeploymentDiscoveryDecisionRecord.id < identifier,
                        ),
                    )
                )
            records = list(
                session.scalars(
                    query.order_by(
                        DeploymentDiscoveryDecisionRecord.created_at.desc(),
                        DeploymentDiscoveryDecisionRecord.id.desc(),
                    ).limit(bounded_limit + 1)
                )
            )
        has_more = len(records) > bounded_limit
        items = records[:bounded_limit]
        next_cursor = (
            encode_time_cursor(items[-1].created_at, items[-1].id) if has_more and items else None
        )
        return tuple(items), next_cursor

    def cleanup_expired_unexposed(self, *, now: datetime | None = None) -> int:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        exposed = exists().where(
            DeploymentDiscoveryExposureRecord.discovery_item_id == DiscoveryItemRecord.id
        )
        with self.database.session() as session:
            result = session.execute(
                delete(DiscoveryItemRecord).where(
                    DiscoveryItemRecord.expires_at < current,
                    ~exposed,
                )
            )
            session.commit()
            return int(cast(CursorResult[Any], result).rowcount or 0)


__all__ = ["DiscoveryProfileView", "DiscoveryRepository"]
