"""Deterministic, provenance-first Character Learned State.

This module does not infer interests, expertise, stance, relationships, ownership, salience, or
fatigue by itself. Callers must supply bounded evidence from an authoritative/observed source.
Learned state is derived and may never overwrite Character Card truth.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, cast
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.engine import CursorResult

from echo_masque.persistence.character_learned_state_event_models import (
    CharacterLearnedStateEventRecord,
)
from echo_masque.persistence.character_learned_state_models import CharacterLearnedStateRecord
from echo_masque.persistence.database import Database

LearnedStateType = Literal[
    "interest",
    "expertise",
    "stance",
    "relationship",
    "conversation_ownership",
    "salience",
    "participation_fatigue",
]
LearnedSubjectType = Literal["topic", "concept", "actor", "character", "event", "media"]

_MAX_PROVENANCE = 8
_LEARNING_RATE = 0.25
_CONTRADICTION_MINIMUM = 0.15
_MIN_RETENTION_SECONDS = 24 * 60 * 60
_MAX_RETENTION_SECONDS = 180 * 24 * 60 * 60
_RETENTION_HALF_LIVES = 8

_HALF_LIFE_SECONDS: dict[LearnedStateType, int] = {
    "interest": 30 * 24 * 60 * 60,
    "expertise": 60 * 24 * 60 * 60,
    "stance": 30 * 24 * 60 * 60,
    "relationship": 90 * 24 * 60 * 60,
    "conversation_ownership": 30 * 60,
    "salience": 6 * 60 * 60,
    "participation_fatigue": 2 * 60 * 60,
}


@dataclass(frozen=True, slots=True)
class LearnedStateEvidence:
    owner_id: str
    character_card_id: str
    state_type: LearnedStateType
    subject_type: LearnedSubjectType
    subject_key: str
    delta: float
    confidence: float
    source_type: str
    source_message_id: str = ""
    source_burst_id: str = ""
    reason_code: str = ""
    connection_id: str = ""
    guild_id: str = ""
    channel_id: str = ""
    topic_id: str = ""


@dataclass(frozen=True, slots=True)
class LearnedStateView:
    id: str
    owner_id: str
    character_card_id: str
    state_type: LearnedStateType
    subject_type: LearnedSubjectType
    subject_key: str
    value: float
    confidence: float
    positive_evidence_count: int
    negative_evidence_count: int
    contradiction_count: int
    evidence_count: int
    half_life_seconds: int
    last_evidence_at: datetime
    expires_at: datetime | None


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, float(value)))


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _canonical(value: str, maximum: int = 240) -> str:
    return " ".join(value.casefold().split())[:maximum]


def _compact(value: str, maximum: int) -> str:
    return " ".join(value.split())[:maximum]


def _decay_factor(elapsed_seconds: float, half_life_seconds: int) -> float:
    if elapsed_seconds <= 0:
        return 1.0
    return math.pow(0.5, elapsed_seconds / max(1, half_life_seconds))


def _retention_seconds(half_life_seconds: int) -> int:
    return max(
        _MIN_RETENTION_SECONDS,
        min(_MAX_RETENTION_SECONDS, half_life_seconds * _RETENTION_HALF_LIVES),
    )


def _provenance(value: str) -> list[dict[str, Any]]:
    try:
        decoded = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(decoded, list):
        return []
    return [item for item in decoded if isinstance(item, dict)][-_MAX_PROVENANCE:]


class CharacterLearnedStateService:
    """Update/read decaying derived Character state without inventing evidence."""

    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def half_life_seconds(state_type: LearnedStateType) -> int:
        return _HALF_LIFE_SECONDS[state_type]

    @staticmethod
    def _effective_values(
        record: CharacterLearnedStateRecord,
        now: datetime,
    ) -> tuple[float, float]:
        last = _aware(record.last_evidence_at)
        factor = _decay_factor(
            max(0.0, (now - last).total_seconds()),
            record.half_life_seconds,
        )
        return record.value * factor, record.confidence * factor

    def record_evidence(
        self,
        evidence: LearnedStateEvidence,
        *,
        now: datetime | None = None,
    ) -> LearnedStateView:
        current = _aware(now) if now is not None else datetime.now(UTC)
        owner_id = _compact(evidence.owner_id, 120)
        character_card_id = _compact(evidence.character_card_id, 64)
        subject_key = _canonical(evidence.subject_key)
        source_type = _compact(evidence.source_type, 40)
        if not owner_id or not character_card_id or not subject_key or not source_type:
            raise ValueError(
                "Learned State evidence requires owner, character, subject, and source."
            )
        delta = _clamp(evidence.delta, -1.0, 1.0)
        evidence_confidence = _clamp(evidence.confidence, 0.0, 1.0)
        if delta == 0.0 or evidence_confidence == 0.0:
            raise ValueError("Learned State evidence must carry non-zero bounded signal.")
        half_life = self.half_life_seconds(evidence.state_type)
        retention_seconds = _retention_seconds(half_life)

        with self.database.session() as session:
            record = session.scalar(
                select(CharacterLearnedStateRecord).where(
                    CharacterLearnedStateRecord.owner_id == owner_id,
                    CharacterLearnedStateRecord.character_card_id == character_card_id,
                    CharacterLearnedStateRecord.state_type == evidence.state_type,
                    CharacterLearnedStateRecord.subject_type == evidence.subject_type,
                    CharacterLearnedStateRecord.subject_key == subject_key,
                )
            )
            if record is None:
                record = CharacterLearnedStateRecord(
                    id=str(uuid4()),
                    owner_id=owner_id,
                    character_card_id=character_card_id,
                    state_type=evidence.state_type,
                    subject_type=evidence.subject_type,
                    subject_key=subject_key,
                    value=0.0,
                    confidence=0.0,
                    positive_evidence_count=0,
                    negative_evidence_count=0,
                    contradiction_count=0,
                    provenance_json="[]",
                    half_life_seconds=half_life,
                    last_evidence_at=current,
                )
                session.add(record)
                prior_value = 0.0
                prior_confidence = 0.0
            else:
                prior_value, prior_confidence = self._effective_values(record, current)

            contradiction = abs(prior_value) >= _CONTRADICTION_MINIMUM and (
                (prior_value > 0.0 and delta < 0.0) or (prior_value < 0.0 and delta > 0.0)
            )
            record.value = round(
                _clamp(
                    prior_value + delta * evidence_confidence * _LEARNING_RATE,
                    -1.0,
                    1.0,
                ),
                6,
            )
            record.confidence = round(
                _clamp(
                    prior_confidence + evidence_confidence * _LEARNING_RATE,
                    0.0,
                    1.0,
                ),
                6,
            )
            record.half_life_seconds = half_life
            if delta > 0:
                record.positive_evidence_count += 1
            else:
                record.negative_evidence_count += 1
            if contradiction:
                record.contradiction_count += 1
            values = _provenance(record.provenance_json)
            values.append(
                {
                    "source_type": source_type,
                    "source_message_id": _compact(evidence.source_message_id, 200),
                    "source_burst_id": _compact(evidence.source_burst_id, 80),
                    "reason_code": _compact(evidence.reason_code, 120),
                    "delta": round(delta, 6),
                    "confidence": round(evidence_confidence, 6),
                    "recorded_at": current.isoformat(),
                    "contradiction": contradiction,
                }
            )
            record.provenance_json = json.dumps(
                values[-_MAX_PROVENANCE:],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            record.last_evidence_at = current
            record.updated_at = current
            record.expires_at = current + timedelta(seconds=retention_seconds)
            session.add(
                CharacterLearnedStateEventRecord(
                    id=str(uuid4()),
                    state_id=record.id,
                    owner_id=owner_id,
                    character_card_id=character_card_id,
                    state_type=evidence.state_type,
                    subject_type=evidence.subject_type,
                    subject_key=subject_key,
                    connection_id=_compact(evidence.connection_id, 64),
                    guild_id=_compact(evidence.guild_id, 200),
                    channel_id=_compact(evidence.channel_id, 200),
                    topic_id=_compact(evidence.topic_id, 64),
                    delta=round(delta, 6),
                    evidence_confidence=round(evidence_confidence, 6),
                    value_before=round(prior_value, 6),
                    value_after=record.value,
                    confidence_before=round(prior_confidence, 6),
                    confidence_after=record.confidence,
                    contradiction=contradiction,
                    source_type=source_type,
                    source_message_id=_compact(evidence.source_message_id, 200),
                    source_burst_id=_compact(evidence.source_burst_id, 80),
                    reason_code=_compact(evidence.reason_code, 120),
                    recorded_at=current,
                )
            )
            session.commit()
            session.refresh(record)
            return self._view(record, current)

    def get(
        self,
        *,
        owner_id: str,
        character_card_id: str,
        state_type: LearnedStateType,
        subject_type: LearnedSubjectType,
        subject_key: str,
        now: datetime | None = None,
    ) -> LearnedStateView | None:
        current = _aware(now) if now is not None else datetime.now(UTC)
        with self.database.session() as session:
            record = session.scalar(
                select(CharacterLearnedStateRecord).where(
                    CharacterLearnedStateRecord.owner_id == _compact(owner_id, 120),
                    CharacterLearnedStateRecord.character_card_id
                    == _compact(character_card_id, 64),
                    CharacterLearnedStateRecord.state_type == state_type,
                    CharacterLearnedStateRecord.subject_type == subject_type,
                    CharacterLearnedStateRecord.subject_key == _canonical(subject_key),
                )
            )
            if record is None:
                return None
            if record.expires_at is not None and _aware(record.expires_at) <= current:
                return None
            return self._view(record, current)

    def list_for_character(
        self,
        *,
        owner_id: str,
        character_card_id: str,
        state_types: tuple[LearnedStateType, ...] = (),
        minimum_absolute_value: float = 0.0,
        limit: int = 50,
        now: datetime | None = None,
    ) -> tuple[LearnedStateView, ...]:
        current = _aware(now) if now is not None else datetime.now(UTC)
        with self.database.session() as session:
            query = select(CharacterLearnedStateRecord).where(
                CharacterLearnedStateRecord.owner_id == _compact(owner_id, 120),
                CharacterLearnedStateRecord.character_card_id == _compact(character_card_id, 64),
            )
            if state_types:
                query = query.where(CharacterLearnedStateRecord.state_type.in_(state_types))
            records = list(
                session.scalars(
                    query.order_by(CharacterLearnedStateRecord.last_evidence_at.desc()).limit(
                        max(1, min(limit, 200))
                    )
                )
            )
        minimum = _clamp(minimum_absolute_value, 0.0, 1.0)
        values: list[LearnedStateView] = []
        for record in records:
            if record.expires_at is not None and _aware(record.expires_at) <= current:
                continue
            view = self._view(record, current)
            if abs(view.value) < minimum:
                continue
            values.append(view)
        return tuple(values)

    def list_events_for_character(
        self,
        *,
        owner_id: str,
        character_card_id: str,
        connection_id: str = "",
        guild_id: str = "",
        state_types: tuple[LearnedStateType, ...] = (),
        limit: int = 200,
    ) -> tuple[CharacterLearnedStateEventRecord, ...]:
        with self.database.session() as session:
            query = select(CharacterLearnedStateEventRecord).where(
                CharacterLearnedStateEventRecord.owner_id == _compact(owner_id, 120),
                CharacterLearnedStateEventRecord.character_card_id
                == _compact(character_card_id, 64),
            )
            if connection_id:
                query = query.where(
                    CharacterLearnedStateEventRecord.connection_id
                    == _compact(connection_id, 64)
                )
            if guild_id:
                query = query.where(
                    CharacterLearnedStateEventRecord.guild_id == _compact(guild_id, 200)
                )
            if state_types:
                query = query.where(CharacterLearnedStateEventRecord.state_type.in_(state_types))
            records = list(
                session.scalars(
                    query.order_by(CharacterLearnedStateEventRecord.recorded_at.desc()).limit(
                        max(1, min(limit, 500))
                    )
                )
            )
        return tuple(records)

    def cleanup_expired(self, *, now: datetime | None = None) -> int:
        current = _aware(now) if now is not None else datetime.now(UTC)
        with self.database.session() as session:
            result = session.execute(
                delete(CharacterLearnedStateRecord).where(
                    CharacterLearnedStateRecord.expires_at.is_not(None),
                    CharacterLearnedStateRecord.expires_at <= current,
                )
            )
            session.commit()
            rowcount = cast(CursorResult[Any], result).rowcount or 0
            return int(rowcount)

    @classmethod
    def _view(
        cls,
        record: CharacterLearnedStateRecord,
        now: datetime,
    ) -> LearnedStateView:
        value, confidence = cls._effective_values(record, now)
        return LearnedStateView(
            id=record.id,
            owner_id=record.owner_id,
            character_card_id=record.character_card_id,
            state_type=record.state_type,  # type: ignore[arg-type]
            subject_type=record.subject_type,  # type: ignore[arg-type]
            subject_key=record.subject_key,
            value=round(_clamp(value, -1.0, 1.0), 6),
            confidence=round(_clamp(confidence, 0.0, 1.0), 6),
            positive_evidence_count=record.positive_evidence_count,
            negative_evidence_count=record.negative_evidence_count,
            contradiction_count=record.contradiction_count,
            evidence_count=record.positive_evidence_count + record.negative_evidence_count,
            half_life_seconds=record.half_life_seconds,
            last_evidence_at=_aware(record.last_evidence_at),
            expires_at=_aware(record.expires_at) if record.expires_at is not None else None,
        )


__all__ = [
    "CharacterLearnedStateService",
    "LearnedStateEvidence",
    "LearnedStateType",
    "LearnedStateView",
    "LearnedSubjectType",
]
