"""SocialEvent projection, relationship evidence, and revisable subjective Impressions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from sqlalchemy import select

from echo_masque.character_relationships import (
    CharacterRelationshipService,
    RelationshipStateView,
)
from echo_masque.persistence.database import Database
from echo_masque.persistence.social_intelligence_models import (
    ImpressionV3Record,
    SocialEventV3Record,
)

SocialEventType = Literal[
    "direct_interaction",
    "support",
    "help",
    "insult",
    "teasing",
    "apology",
    "betrayal",
    "praise",
    "conflict",
]
SocialTargetType = Literal["actor", "deployment"]

_EVENT_DELTAS: dict[SocialEventType, tuple[float, float, float, float]] = {
    "direct_interaction": (0.05, 0.0, 0.0, 0.01),
    "support": (0.03, 0.08, 0.08, 0.06),
    "help": (0.04, 0.06, 0.1, 0.05),
    "insult": (0.02, -0.12, -0.05, -0.12),
    "teasing": (0.03, 0.01, 0.0, -0.02),
    "apology": (0.03, 0.04, 0.06, 0.06),
    "betrayal": (0.02, -0.18, -0.3, -0.18),
    "praise": (0.03, 0.1, 0.02, 0.04),
    "conflict": (0.04, -0.08, -0.08, -0.1),
}


def _decode(raw: str) -> tuple[str, ...]:
    try:
        value = json.loads(raw or "[]")
    except (json.JSONDecodeError, TypeError):
        return ()
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value if isinstance(item, str) and item)


def _encode(values: tuple[str, ...], *, limit: int = 32) -> str:
    clean = list(dict.fromkeys(item for item in values if item))[-limit:]
    return json.dumps(clean, ensure_ascii=False)


@dataclass(frozen=True, slots=True)
class SocialEventV3View:
    id: str
    source_deployment_id: str
    target_type: str
    target_key: str
    event_type: str
    familiarity_delta: float
    affinity_delta: float
    trust_delta: float
    comfort_delta: float
    confidence: float
    source_relation_id: str
    source_segment_id: str
    source_episode_id: str
    source_message_ids: tuple[str, ...]
    status: str
    reason: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ImpressionV3View:
    id: str
    source_deployment_id: str
    target_type: str
    target_key: str
    summary: str
    observations: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    confidence: float
    status: str
    supersedes_impression_id: str
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class SocialEventApplication:
    event: SocialEventV3View
    relationship: RelationshipStateView | None
    applied: bool


class SocialIntelligenceV3Service:
    """Only lived, target-resolved interaction evidence can change relationship state."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self.relationships = CharacterRelationshipService(database)

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

    @classmethod
    def event_view(cls, record: SocialEventV3Record) -> SocialEventV3View:
        return SocialEventV3View(
            id=record.id,
            source_deployment_id=record.source_deployment_id,
            target_type=record.target_type,
            target_key=record.target_key,
            event_type=record.event_type,
            familiarity_delta=record.familiarity_delta,
            affinity_delta=record.affinity_delta,
            trust_delta=record.trust_delta,
            comfort_delta=record.comfort_delta,
            confidence=record.confidence,
            source_relation_id=record.source_relation_id,
            source_segment_id=record.source_segment_id,
            source_episode_id=record.source_episode_id,
            source_message_ids=_decode(record.source_message_ids_json),
            status=record.status,
            reason=record.reason,
            created_at=cls._aware(record.created_at),
        )

    @classmethod
    def impression_view(cls, record: ImpressionV3Record) -> ImpressionV3View:
        return ImpressionV3View(
            id=record.id,
            source_deployment_id=record.source_deployment_id,
            target_type=record.target_type,
            target_key=record.target_key,
            summary=record.summary,
            observations=_decode(record.observations_json),
            evidence_refs=_decode(record.evidence_refs_json),
            confidence=record.confidence,
            status=record.status,
            supersedes_impression_id=record.supersedes_impression_id,
            updated_at=cls._aware(record.updated_at),
        )

    def record_event(
        self,
        *,
        owner_id: str,
        source_deployment_id: str,
        target_type: SocialTargetType,
        target_key: str,
        event_type: SocialEventType,
        confidence: float,
        source_relation_id: str = "",
        relation_resolved: bool = False,
        source_segment_id: str = "",
        source_episode_id: str = "",
        source_message_ids: tuple[str, ...] = (),
        reason: str = "",
        now: datetime | None = None,
    ) -> SocialEventApplication:
        current = now or datetime.now(UTC)
        deltas = _EVENT_DELTAS[event_type]
        resolved_target = bool(target_key) and relation_resolved
        record = SocialEventV3Record(
            id=str(uuid4()),
            owner_id=owner_id,
            source_deployment_id=source_deployment_id,
            target_type=target_type,
            target_key=target_key[:200],
            event_type=event_type,
            familiarity_delta=deltas[0],
            affinity_delta=deltas[1],
            trust_delta=deltas[2],
            comfort_delta=deltas[3],
            confidence=max(0.0, min(float(confidence), 1.0)),
            source_relation_id=source_relation_id[:64],
            source_segment_id=source_segment_id[:64],
            source_episode_id=source_episode_id[:64],
            source_message_ids_json=_encode(source_message_ids),
            status="active" if resolved_target else "unresolved",
            reason=" ".join(reason.split())[:500],
            created_at=current,
            updated_at=current,
        )
        with self.database.session() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
        relationship: RelationshipStateView | None = None
        if resolved_target:
            relationship = self._apply_event(record)
        return SocialEventApplication(
            event=self.event_view(record),
            relationship=relationship,
            applied=relationship is not None,
        )

    def _apply_event(self, event: SocialEventV3Record) -> RelationshipStateView | None:
        dimensions = (
            ("familiarity", event.familiarity_delta),
            ("affinity", event.affinity_delta),
            ("trust", event.trust_delta),
            ("comfort", event.comfort_delta),
        )
        latest: RelationshipStateView | None = None
        source_message_ids = _decode(event.source_message_ids_json)
        source_message_id = source_message_ids[0] if source_message_ids else ""
        for dimension, delta in dimensions:
            if delta == 0.0:
                continue
            try:
                latest = self.relationships.record_evidence(
                    owner_id=event.owner_id,
                    source_deployment_id=event.source_deployment_id,
                    target_type=event.target_type,  # type: ignore[arg-type]
                    target_key=event.target_key,
                    dimension=dimension,  # type: ignore[arg-type]
                    delta=delta,
                    confidence=event.confidence,
                    reason_code=f"social_event:{event.event_type}",
                    source_message_id=source_message_id,
                    source_burst_id="",
                )
            except (KeyError, ValueError):
                return None
        return latest

    def resolve_event_target(
        self,
        *,
        owner_id: str,
        event_id: str,
        target_type: SocialTargetType,
        target_key: str,
        confidence: float | None = None,
        now: datetime | None = None,
    ) -> SocialEventApplication:
        current = now or datetime.now(UTC)
        with self.database.session() as session:
            record = session.get(SocialEventV3Record, event_id)
            if record is None or record.owner_id != owner_id:
                raise KeyError("Social Event not found.")
            if record.status == "rejected":
                raise ValueError("Rejected Social Event cannot be resolved in place.")
            record.target_type = target_type
            record.target_key = target_key[:200]
            if confidence is not None:
                record.confidence = max(0.0, min(float(confidence), 1.0))
            record.status = "active"
            record.updated_at = current
            session.commit()
            session.refresh(record)
        relationship = self._apply_event(record)
        return SocialEventApplication(
            event=self.event_view(record),
            relationship=relationship,
            applied=relationship is not None,
        )

    def reject_event(
        self,
        *,
        owner_id: str,
        event_id: str,
        now: datetime | None = None,
    ) -> SocialEventV3View:
        current = now or datetime.now(UTC)
        with self.database.session() as session:
            record = session.get(SocialEventV3Record, event_id)
            if record is None or record.owner_id != owner_id:
                raise KeyError("Social Event not found.")
            if record.status == "active":
                # Relationship state is evidence-accumulated and decaying. Reversal requires an
                # explicit compensating SocialEvent; silently subtracting history would destroy
                # provenance.
                record.reason = (record.reason + " | rejected_after_application")[:500]
            record.status = "rejected"
            record.updated_at = current
            session.commit()
            session.refresh(record)
            return self.event_view(record)

    def revise_impression(
        self,
        *,
        owner_id: str,
        source_deployment_id: str,
        target_type: SocialTargetType,
        target_key: str,
        summary: str,
        observations: tuple[str, ...],
        evidence_refs: tuple[str, ...],
        confidence: float,
        now: datetime | None = None,
    ) -> ImpressionV3View:
        current = now or datetime.now(UTC)
        with self.database.session() as session:
            previous = session.scalar(
                select(ImpressionV3Record)
                .where(
                    ImpressionV3Record.owner_id == owner_id,
                    ImpressionV3Record.source_deployment_id == source_deployment_id,
                    ImpressionV3Record.target_type == target_type,
                    ImpressionV3Record.target_key == target_key,
                    ImpressionV3Record.status == "active",
                )
                .order_by(ImpressionV3Record.updated_at.desc())
                .limit(1)
            )
            previous_id = ""
            if previous is not None:
                previous.status = "superseded"
                previous.updated_at = current
                previous_id = previous.id
            clean_observations = tuple(
                " ".join(item.split())[:500] for item in observations if item.strip()
            )
            record = ImpressionV3Record(
                id=str(uuid4()),
                owner_id=owner_id,
                source_deployment_id=source_deployment_id,
                target_type=target_type,
                target_key=target_key[:200],
                summary=" ".join(summary.split())[:2400],
                observations_json=_encode(clean_observations, limit=12),
                evidence_refs_json=_encode(evidence_refs, limit=48),
                confidence=max(0.0, min(float(confidence), 1.0)),
                status="active",
                supersedes_impression_id=previous_id,
                created_at=current,
                updated_at=current,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return self.impression_view(record)

    def impression(
        self,
        *,
        owner_id: str,
        source_deployment_id: str,
        target_type: SocialTargetType,
        target_key: str,
    ) -> ImpressionV3View | None:
        with self.database.session() as session:
            record = session.scalar(
                select(ImpressionV3Record)
                .where(
                    ImpressionV3Record.owner_id == owner_id,
                    ImpressionV3Record.source_deployment_id == source_deployment_id,
                    ImpressionV3Record.target_type == target_type,
                    ImpressionV3Record.target_key == target_key,
                    ImpressionV3Record.status == "active",
                )
                .order_by(ImpressionV3Record.updated_at.desc())
                .limit(1)
            )
        return self.impression_view(record) if record is not None else None

    def prompt_context(
        self,
        *,
        owner_id: str,
        source_deployment_id: str,
        target_type: SocialTargetType,
        target_key: str,
        max_chars: int = 650,
    ) -> tuple[str, ...]:
        state = self.relationships.get_state(
            owner_id=owner_id,
            source_deployment_id=source_deployment_id,
            target_type=target_type,
            target_key=target_key,
        )
        impression = self.impression(
            owner_id=owner_id,
            source_deployment_id=source_deployment_id,
            target_type=target_type,
            target_key=target_key,
        )
        if state is None and impression is None:
            return ()
        parts = ["Relevant lived social context (subjective, not factual canon):"]
        if state is not None:
            parts.append(
                "Relationship signals: "
                f"familiarity={state.familiarity:.2f}, affinity={state.affinity:.2f}, "
                f"trust={state.trust:.2f}, comfort={state.comfort:.2f}."
            )
        if impression is not None and impression.confidence >= 0.5:
            detail = "; ".join(impression.observations[:2]) or impression.summary
            if detail:
                parts.append(f"Current impression: {detail[:300]}")
        compact: list[str] = []
        remaining = max(120, max_chars)
        for part in parts:
            if remaining <= 0:
                break
            value = part[:remaining]
            compact.append(value)
            remaining -= len(value)
        return tuple(compact)


__all__ = [
    "ImpressionV3View",
    "SocialEventApplication",
    "SocialEventType",
    "SocialEventV3View",
    "SocialIntelligenceV3Service",
    "SocialTargetType",
]
