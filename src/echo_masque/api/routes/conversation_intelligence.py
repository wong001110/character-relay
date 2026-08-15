"""Read-only Conversation Intelligence inspection for Portal diagnostics."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from echo_masque.api.dependencies import CurrentUserDependency
from echo_masque.character_learned_state import CharacterLearnedStateService
from echo_masque.persistence.character_learned_state_models import CharacterLearnedStateRecord
from echo_masque.persistence.conversation_topic_repository import ConversationTopicRepository
from echo_masque.persistence.database import Database
from echo_masque.persistence.repository import Repository

router = APIRouter(prefix="/api/conversation-intelligence", tags=["conversation-intelligence"])


class LearnedStateProvenanceView(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_type: str = ""
    source_message_id: str = ""
    source_burst_id: str = ""
    reason_code: str = ""
    delta: float = 0.0
    confidence: float = 0.0
    recorded_at: datetime | None = None
    contradiction: bool = False


class LearnedStateInspectionView(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    state_type: str
    subject_type: str
    subject_key: str
    stored_value: float
    current_value: float
    stored_confidence: float
    current_confidence: float
    positive_evidence_count: int
    negative_evidence_count: int
    contradiction_count: int
    evidence_count: int
    half_life_seconds: int
    last_evidence_at: datetime
    expires_at: datetime | None = None
    provenance: tuple[LearnedStateProvenanceView, ...] = ()


class CharacterIntelligenceView(BaseModel):
    model_config = ConfigDict(frozen=True)

    character_card_id: str
    character_display_name: str
    items: tuple[LearnedStateInspectionView, ...] = ()


class TopicInspectionView(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    topic_label: str
    summary: str
    keywords: tuple[str, ...] = ()
    open_loops: tuple[str, ...] = ()
    participants: tuple[str, ...] = ()
    status: str
    message_count: int
    capsule_version: int
    last_message_id: str
    started_at: datetime
    last_active_at: datetime
    closed_at: datetime | None = None


class TopicTimelineView(BaseModel):
    model_config = ConfigDict(frozen=True)

    current_topic_id: str = ""
    items: tuple[TopicInspectionView, ...] = ()


def _database(request: Request) -> Database:
    return request.app.state.database


def _repository(request: Request) -> Repository:
    return request.app.state.repository


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _json_list(raw: str) -> tuple[str, ...]:
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return ()
    if not isinstance(parsed, list):
        return ()
    return tuple(str(item).strip() for item in parsed if str(item).strip())


def _provenance(raw: str) -> tuple[LearnedStateProvenanceView, ...]:
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return ()
    if not isinstance(parsed, list):
        return ()
    values: list[LearnedStateProvenanceView] = []
    for item in parsed[-8:]:
        if not isinstance(item, dict):
            continue
        value: dict[str, Any] = item
        recorded_at: datetime | None = None
        raw_time = value.get("recorded_at")
        if isinstance(raw_time, str) and raw_time:
            try:
                recorded_at = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
            except ValueError:
                recorded_at = None
        values.append(
            LearnedStateProvenanceView(
                source_type=str(value.get("source_type", "")),
                source_message_id=str(value.get("source_message_id", "")),
                source_burst_id=str(value.get("source_burst_id", "")),
                reason_code=str(value.get("reason_code", "")),
                delta=float(value.get("delta", 0.0) or 0.0),
                confidence=float(value.get("confidence", 0.0) or 0.0),
                recorded_at=recorded_at,
                contradiction=bool(value.get("contradiction", False)),
            )
        )
    return tuple(values)


@router.get(
    "/characters/{character_card_id}",
    response_model=CharacterIntelligenceView,
)
def inspect_character_intelligence(
    character_card_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> CharacterIntelligenceView:
    card = _repository(request).get_character_card(character_card_id, user.id)
    if card is None:
        raise HTTPException(status_code=404, detail="Character Card not found.")

    database = _database(request)
    service = CharacterLearnedStateService(database)
    effective = {
        item.id: item
        for item in service.list_for_character(
            owner_id=user.id,
            character_card_id=character_card_id,
            limit=200,
        )
    }
    with database.session() as session:
        records = list(
            session.scalars(
                select(CharacterLearnedStateRecord)
                .where(
                    CharacterLearnedStateRecord.owner_id == user.id,
                    CharacterLearnedStateRecord.character_card_id == character_card_id,
                )
                .order_by(CharacterLearnedStateRecord.last_evidence_at.desc())
            )
        )

    items: list[LearnedStateInspectionView] = []
    for record in records:
        current = effective.get(record.id)
        if current is None:
            continue
        items.append(
            LearnedStateInspectionView(
                id=record.id,
                state_type=record.state_type,
                subject_type=record.subject_type,
                subject_key=record.subject_key,
                stored_value=record.value,
                current_value=current.value,
                stored_confidence=record.confidence,
                current_confidence=current.confidence,
                positive_evidence_count=record.positive_evidence_count,
                negative_evidence_count=record.negative_evidence_count,
                contradiction_count=record.contradiction_count,
                evidence_count=current.evidence_count,
                half_life_seconds=record.half_life_seconds,
                last_evidence_at=current.last_evidence_at,
                expires_at=current.expires_at,
                provenance=_provenance(record.provenance_json),
            )
        )
    return CharacterIntelligenceView(
        character_card_id=card.id,
        character_display_name=card.display_name,
        items=tuple(items),
    )


@router.get("/topics", response_model=TopicTimelineView)
def inspect_topic_timeline(
    request: Request,
    user: CurrentUserDependency,
    connection_id: str = Query(min_length=1, max_length=64),
    guild_id: str = Query(min_length=1, max_length=200),
    channel_id: str = Query(min_length=1, max_length=200),
    thread_id: str = Query(default="", max_length=200),
    limit: int = Query(default=20, ge=1, le=20),
) -> TopicTimelineView:
    records = ConversationTopicRepository(_database(request)).recent_for_scope(
        owner_id=user.id,
        platform="discord",
        connection_id=connection_id,
        guild_id=guild_id,
        channel_id=channel_id,
        thread_id=thread_id,
        limit=limit,
    )
    items = tuple(
        TopicInspectionView(
            id=record.id,
            topic_label=record.topic_label,
            summary=record.summary,
            keywords=_json_list(record.keywords_json),
            open_loops=_json_list(record.open_loops_json),
            participants=_json_list(record.participants_json),
            status=record.status,
            message_count=record.message_count,
            capsule_version=record.capsule_version,
            last_message_id=record.last_message_id,
            started_at=_aware(record.started_at) or record.started_at,
            last_active_at=_aware(record.last_active_at) or record.last_active_at,
            closed_at=_aware(record.closed_at),
        )
        for record in records
    )
    current = next((item.id for item in items if item.status == "active"), "")
    return TopicTimelineView(current_topic_id=current, items=items)


__all__ = ["router"]
