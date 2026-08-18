"""Canonical relationship priors, lived Deployment relationship state, and Social Context."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from sqlalchemy import select

from echo_masque.persistence.character_relationship_models import (
    CharacterPersonImpressionRecord,
    CharacterRelationshipPriorRecord,
    DeploymentRelationshipEventRecord,
    DeploymentRelationshipStateRecord,
)
from echo_masque.persistence.database import Database
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord
from echo_masque.persistence.models import CharacterCardRecord

RelationshipDimension = Literal["familiarity", "affinity", "trust", "comfort"]
RelationshipTargetType = Literal["actor", "deployment"]
_DIMENSION_HALF_LIFE_DAYS: dict[RelationshipDimension, float] = {
    "familiarity": 180.0,
    "affinity": 45.0,
    "trust": 90.0,
    "comfort": 45.0,
}


def _clamp(value: float) -> float:
    return max(-1.0, min(1.0, float(value)))


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class RelationshipPriorView:
    id: str
    source_character_card_id: str
    target_character_card_id: str
    relationship_type: str
    description: str
    familiarity: float
    affinity: float
    trust: float
    comfort: float


@dataclass(frozen=True, slots=True)
class RelationshipStateView:
    id: str
    source_deployment_id: str
    target_type: RelationshipTargetType
    target_key: str
    familiarity: float
    affinity: float
    trust: float
    comfort: float
    familiarity_baseline: float
    affinity_baseline: float
    trust_baseline: float
    comfort_baseline: float
    last_evidence_at: datetime


@dataclass(frozen=True, slots=True)
class PersonImpressionView:
    target_type: RelationshipTargetType
    target_key: str
    summary: str
    observations: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    confidence: float


class CharacterRelationshipService:
    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def _prior_view(record: CharacterRelationshipPriorRecord) -> RelationshipPriorView:
        return RelationshipPriorView(
            id=record.id,
            source_character_card_id=record.source_character_card_id,
            target_character_card_id=record.target_character_card_id,
            relationship_type=record.relationship_type,
            description=record.description,
            familiarity=record.familiarity_baseline,
            affinity=record.affinity_baseline,
            trust=record.trust_baseline,
            comfort=record.comfort_baseline,
        )

    def upsert_prior(
        self,
        *,
        owner_id: str,
        source_character_card_id: str,
        target_character_card_id: str,
        relationship_type: str,
        description: str,
        familiarity: float,
        affinity: float,
        trust: float,
        comfort: float,
    ) -> RelationshipPriorView:
        if source_character_card_id == target_character_card_id:
            raise ValueError("A Character cannot define a canonical relationship to itself.")
        with self.database.session() as session:
            source = session.get(CharacterCardRecord, source_character_card_id)
            target = session.get(CharacterCardRecord, target_character_card_id)
            if source is None or target is None or source.owner_id != owner_id or target.owner_id != owner_id:
                raise KeyError("character")
            record = session.scalar(
                select(CharacterRelationshipPriorRecord).where(
                    CharacterRelationshipPriorRecord.owner_id == owner_id,
                    CharacterRelationshipPriorRecord.source_character_card_id == source_character_card_id,
                    CharacterRelationshipPriorRecord.target_character_card_id == target_character_card_id,
                )
            )
            if record is None:
                record = CharacterRelationshipPriorRecord(
                    id=str(uuid4()),
                    owner_id=owner_id,
                    source_character_card_id=source_character_card_id,
                    target_character_card_id=target_character_card_id,
                )
                session.add(record)
            record.relationship_type = " ".join(relationship_type.split())[:80] or "other"
            record.description = " ".join(description.split())[:4000]
            record.familiarity_baseline = _clamp(familiarity)
            record.affinity_baseline = _clamp(affinity)
            record.trust_baseline = _clamp(trust)
            record.comfort_baseline = _clamp(comfort)
            session.commit()
            session.refresh(record)
            return self._prior_view(record)

    def list_priors(self, *, owner_id: str, source_character_card_id: str) -> tuple[RelationshipPriorView, ...]:
        with self.database.session() as session:
            records = list(
                session.scalars(
                    select(CharacterRelationshipPriorRecord)
                    .where(
                        CharacterRelationshipPriorRecord.owner_id == owner_id,
                        CharacterRelationshipPriorRecord.source_character_card_id == source_character_card_id,
                    )
                    .order_by(CharacterRelationshipPriorRecord.updated_at.desc())
                )
            )
        return tuple(self._prior_view(item) for item in records)

    def get_prior(
        self,
        *,
        owner_id: str,
        source_character_card_id: str,
        target_character_card_id: str,
    ) -> RelationshipPriorView | None:
        with self.database.session() as session:
            record = session.scalar(
                select(CharacterRelationshipPriorRecord).where(
                    CharacterRelationshipPriorRecord.owner_id == owner_id,
                    CharacterRelationshipPriorRecord.source_character_card_id == source_character_card_id,
                    CharacterRelationshipPriorRecord.target_character_card_id == target_character_card_id,
                )
            )
        return self._prior_view(record) if record is not None else None

    @staticmethod
    def _effective(
        baseline: float,
        delta: float,
        *,
        dimension: RelationshipDimension,
        elapsed_days: float,
    ) -> float:
        factor = math.pow(0.5, max(0.0, elapsed_days) / _DIMENSION_HALF_LIFE_DAYS[dimension])
        return round(_clamp(baseline + delta * factor), 6)

    def _state_view(self, record: DeploymentRelationshipStateRecord, now: datetime) -> RelationshipStateView:
        elapsed_days = max(0.0, (now - _aware(record.last_evidence_at)).total_seconds() / 86400.0)
        return RelationshipStateView(
            id=record.id,
            source_deployment_id=record.source_deployment_id,
            target_type=record.target_type,  # type: ignore[arg-type]
            target_key=record.target_key,
            familiarity=self._effective(record.familiarity_baseline, record.familiarity_delta, dimension="familiarity", elapsed_days=elapsed_days),
            affinity=self._effective(record.affinity_baseline, record.affinity_delta, dimension="affinity", elapsed_days=elapsed_days),
            trust=self._effective(record.trust_baseline, record.trust_delta, dimension="trust", elapsed_days=elapsed_days),
            comfort=self._effective(record.comfort_baseline, record.comfort_delta, dimension="comfort", elapsed_days=elapsed_days),
            familiarity_baseline=record.familiarity_baseline,
            affinity_baseline=record.affinity_baseline,
            trust_baseline=record.trust_baseline,
            comfort_baseline=record.comfort_baseline,
            last_evidence_at=_aware(record.last_evidence_at),
        )

    def initialize_character_pair(
        self,
        *,
        owner_id: str,
        source_deployment_id: str,
        target_deployment_id: str,
        now: datetime | None = None,
    ) -> RelationshipStateView:
        current = now or datetime.now(UTC)
        with self.database.session() as session:
            source = session.get(CharacterDeploymentRecord, source_deployment_id)
            target = session.get(CharacterDeploymentRecord, target_deployment_id)
            if source is None or target is None or source.owner_id != owner_id or target.owner_id != owner_id:
                raise KeyError("deployment")
            if source.connection_id != target.connection_id or source.workspace_id != target.workspace_id:
                raise ValueError("Character Deployments must share one Server before initializing lived relationship state.")
            prior = session.scalar(
                select(CharacterRelationshipPriorRecord).where(
                    CharacterRelationshipPriorRecord.owner_id == owner_id,
                    CharacterRelationshipPriorRecord.source_character_card_id == source.character_card_id,
                    CharacterRelationshipPriorRecord.target_character_card_id == target.character_card_id,
                )
            )
            baseline = (
                (
                    prior.familiarity_baseline,
                    prior.affinity_baseline,
                    prior.trust_baseline,
                    prior.comfort_baseline,
                )
                if prior is not None
                else (0.0, 0.0, 0.0, 0.0)
            )
            record = self._get_or_create_state_record(
                session,
                owner_id=owner_id,
                source_deployment_id=source_deployment_id,
                target_type="deployment",
                target_key=target_deployment_id,
                baseline=baseline,
                now=current,
            )
            session.commit()
            session.refresh(record)
            return self._state_view(record, current)

    @staticmethod
    def _get_or_create_state_record(
        session: object,
        *,
        owner_id: str,
        source_deployment_id: str,
        target_type: RelationshipTargetType,
        target_key: str,
        baseline: tuple[float, float, float, float],
        now: datetime,
    ) -> DeploymentRelationshipStateRecord:
        record = session.scalar(  # type: ignore[attr-defined]
            select(DeploymentRelationshipStateRecord).where(
                DeploymentRelationshipStateRecord.source_deployment_id == source_deployment_id,
                DeploymentRelationshipStateRecord.target_type == target_type,
                DeploymentRelationshipStateRecord.target_key == target_key,
            )
        )
        if record is None:
            record = DeploymentRelationshipStateRecord(
                id=str(uuid4()),
                owner_id=owner_id,
                source_deployment_id=source_deployment_id,
                target_type=target_type,
                target_key=target_key,
                familiarity_baseline=baseline[0],
                affinity_baseline=baseline[1],
                trust_baseline=baseline[2],
                comfort_baseline=baseline[3],
                last_evidence_at=now,
            )
            session.add(record)  # type: ignore[attr-defined]
        return record

    def record_evidence(
        self,
        *,
        owner_id: str,
        source_deployment_id: str,
        target_type: RelationshipTargetType,
        target_key: str,
        dimension: RelationshipDimension,
        delta: float,
        confidence: float,
        reason_code: str,
        source_message_id: str = "",
        source_burst_id: str = "",
        now: datetime | None = None,
    ) -> RelationshipStateView:
        current = now or datetime.now(UTC)
        bounded_delta = _clamp(delta) * max(0.0, min(1.0, confidence))
        with self.database.session() as session:
            source = session.get(CharacterDeploymentRecord, source_deployment_id)
            if source is None or source.owner_id != owner_id:
                raise KeyError("deployment")
            baseline = (0.0, 0.0, 0.0, 0.0)
            if target_type == "deployment":
                target = session.get(CharacterDeploymentRecord, target_key)
                if target is None or target.owner_id != owner_id:
                    raise KeyError("target_deployment")
                prior = session.scalar(
                    select(CharacterRelationshipPriorRecord).where(
                        CharacterRelationshipPriorRecord.owner_id == owner_id,
                        CharacterRelationshipPriorRecord.source_character_card_id == source.character_card_id,
                        CharacterRelationshipPriorRecord.target_character_card_id == target.character_card_id,
                    )
                )
                if prior is not None:
                    baseline = (
                        prior.familiarity_baseline,
                        prior.affinity_baseline,
                        prior.trust_baseline,
                        prior.comfort_baseline,
                    )
            record = self._get_or_create_state_record(
                session,
                owner_id=owner_id,
                source_deployment_id=source_deployment_id,
                target_type=target_type,
                target_key=target_key[:200],
                baseline=baseline,
                now=current,
            )
            elapsed_days = max(0.0, (current - _aware(record.last_evidence_at)).total_seconds() / 86400.0)
            field = f"{dimension}_delta"
            previous_delta = float(getattr(record, field))
            decayed = previous_delta * math.pow(0.5, elapsed_days / _DIMENSION_HALF_LIFE_DAYS[dimension])
            setattr(record, field, round(_clamp(decayed + bounded_delta), 6))
            record.last_evidence_at = current
            record.updated_at = current
            session.add(
                DeploymentRelationshipEventRecord(
                    id=str(uuid4()),
                    state_id=record.id,
                    owner_id=owner_id,
                    source_deployment_id=source_deployment_id,
                    target_type=target_type,
                    target_key=target_key[:200],
                    dimension=dimension,
                    delta=round(delta, 6),
                    confidence=max(0.0, min(1.0, confidence)),
                    reason_code=reason_code[:120],
                    source_message_id=source_message_id[:200],
                    source_burst_id=source_burst_id[:80],
                    recorded_at=current,
                )
            )
            session.commit()
            session.refresh(record)
            return self._state_view(record, current)

    def record_interaction_familiarity(
        self,
        *,
        owner_id: str,
        source_deployment_id: str,
        target_type: RelationshipTargetType,
        target_key: str,
        source_message_id: str = "",
        source_burst_id: str = "",
    ) -> RelationshipStateView:
        return self.record_evidence(
            owner_id=owner_id,
            source_deployment_id=source_deployment_id,
            target_type=target_type,
            target_key=target_key,
            dimension="familiarity",
            delta=0.06,
            confidence=0.8,
            reason_code="direct_interaction_familiarity",
            source_message_id=source_message_id,
            source_burst_id=source_burst_id,
        )

    def get_state(
        self,
        *,
        owner_id: str,
        source_deployment_id: str,
        target_type: RelationshipTargetType,
        target_key: str,
        now: datetime | None = None,
    ) -> RelationshipStateView | None:
        current = now or datetime.now(UTC)
        with self.database.session() as session:
            record = session.scalar(
                select(DeploymentRelationshipStateRecord).where(
                    DeploymentRelationshipStateRecord.owner_id == owner_id,
                    DeploymentRelationshipStateRecord.source_deployment_id == source_deployment_id,
                    DeploymentRelationshipStateRecord.target_type == target_type,
                    DeploymentRelationshipStateRecord.target_key == target_key,
                )
            )
        return self._state_view(record, current) if record is not None else None

    def list_states(
        self,
        *,
        owner_id: str,
        source_deployment_id: str,
        now: datetime | None = None,
    ) -> tuple[RelationshipStateView, ...]:
        current = now or datetime.now(UTC)
        with self.database.session() as session:
            records = list(
                session.scalars(
                    select(DeploymentRelationshipStateRecord)
                    .where(
                        DeploymentRelationshipStateRecord.owner_id == owner_id,
                        DeploymentRelationshipStateRecord.source_deployment_id == source_deployment_id,
                    )
                    .order_by(DeploymentRelationshipStateRecord.updated_at.desc())
                    .limit(200)
                )
            )
        return tuple(self._state_view(item, current) for item in records)

    @staticmethod
    def _decode(raw: str) -> tuple[str, ...]:
        try:
            value = json.loads(raw or "[]")
        except (json.JSONDecodeError, TypeError):
            return ()
        return tuple(str(item) for item in value if isinstance(item, str) and item) if isinstance(value, list) else ()

    def upsert_impression(
        self,
        *,
        owner_id: str,
        source_deployment_id: str,
        target_type: RelationshipTargetType,
        target_key: str,
        summary: str,
        observations: tuple[str, ...],
        evidence_refs: tuple[str, ...],
        confidence: float,
    ) -> PersonImpressionView:
        with self.database.session() as session:
            source = session.get(CharacterDeploymentRecord, source_deployment_id)
            if source is None or source.owner_id != owner_id:
                raise KeyError("deployment")
            record = session.scalar(
                select(CharacterPersonImpressionRecord).where(
                    CharacterPersonImpressionRecord.source_deployment_id == source_deployment_id,
                    CharacterPersonImpressionRecord.target_type == target_type,
                    CharacterPersonImpressionRecord.target_key == target_key,
                )
            )
            if record is None:
                record = CharacterPersonImpressionRecord(
                    id=str(uuid4()),
                    owner_id=owner_id,
                    source_deployment_id=source_deployment_id,
                    target_type=target_type,
                    target_key=target_key[:200],
                )
                session.add(record)
            record.summary = " ".join(summary.split())[:2000]
            record.observations_json = json.dumps(
                [" ".join(item.split())[:400] for item in observations if item.strip()][:8],
                ensure_ascii=False,
            )
            record.evidence_refs_json = json.dumps(list(dict.fromkeys(evidence_refs))[:16], ensure_ascii=False)
            record.confidence = max(0.0, min(1.0, confidence))
            record.updated_at = datetime.now(UTC)
            session.commit()
            session.refresh(record)
            return PersonImpressionView(
                target_type=target_type,
                target_key=target_key,
                summary=record.summary,
                observations=self._decode(record.observations_json),
                evidence_refs=self._decode(record.evidence_refs_json),
                confidence=record.confidence,
            )

    def get_impression(
        self,
        *,
        owner_id: str,
        source_deployment_id: str,
        target_type: RelationshipTargetType,
        target_key: str,
    ) -> PersonImpressionView | None:
        with self.database.session() as session:
            record = session.scalar(
                select(CharacterPersonImpressionRecord).where(
                    CharacterPersonImpressionRecord.owner_id == owner_id,
                    CharacterPersonImpressionRecord.source_deployment_id == source_deployment_id,
                    CharacterPersonImpressionRecord.target_type == target_type,
                    CharacterPersonImpressionRecord.target_key == target_key,
                )
            )
        if record is None:
            return None
        return PersonImpressionView(
            target_type=target_type,
            target_key=target_key,
            summary=record.summary,
            observations=self._decode(record.observations_json),
            evidence_refs=self._decode(record.evidence_refs_json),
            confidence=record.confidence,
        )

    def social_prompt_guidance(
        self,
        *,
        owner_id: str,
        source_deployment_id: str,
        target_type: RelationshipTargetType,
        target_key: str,
        max_chars: int = 480,
    ) -> tuple[str, ...]:
        state = self.get_state(
            owner_id=owner_id,
            source_deployment_id=source_deployment_id,
            target_type=target_type,
            target_key=target_key,
        )
        impression = self.get_impression(
            owner_id=owner_id,
            source_deployment_id=source_deployment_id,
            target_type=target_type,
            target_key=target_key,
        )
        if state is None and impression is None:
            return ()
        parts: list[str] = ["Relevant social context for the current interaction:"]
        if state is not None:
            familiarity = "very familiar" if state.familiarity >= 0.65 else "familiar" if state.familiarity >= 0.25 else "not very familiar"
            affinity = "positive" if state.affinity >= 0.25 else "strained" if state.affinity <= -0.25 else "neutral"
            trust = "high trust" if state.trust >= 0.55 else "limited trust" if state.trust <= -0.15 else "moderate trust"
            comfort = "comfortable" if state.comfort >= 0.35 else "guarded" if state.comfort <= -0.2 else "somewhat reserved"
            parts.append(f"You are {familiarity} with this person; the relationship feels {affinity}, {trust}, and {comfort}.")
        if impression is not None and impression.confidence >= 0.55:
            observations = "; ".join(impression.observations[:2])
            if observations:
                parts.append(f"Observed impression: {observations}.")
            elif impression.summary:
                parts.append(f"Observed impression: {impression.summary[:220]}.")
        compact: list[str] = []
        remaining = max(120, max_chars)
        for part in parts:
            if len(part) > remaining:
                part = part[:remaining]
            if not part:
                break
            compact.append(part)
            remaining -= len(part)
            if remaining <= 0:
                break
        return tuple(compact)


__all__ = [
    "CharacterRelationshipService",
    "PersonImpressionView",
    "RelationshipDimension",
    "RelationshipPriorView",
    "RelationshipStateView",
    "RelationshipTargetType",
]
