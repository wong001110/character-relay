"""Conversation Intelligence inspection and owner-scoped derived-data governance."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, cast

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from echo_masque.api.dependencies import CurrentUserDependency
from echo_masque.character_learned_state import CharacterLearnedStateService
from echo_masque.conversation_intelligence_governance import (
    ConversationIntelligenceGovernanceService,
    DerivedResetResult,
    TopicDerivedImpact,
)
from echo_masque.persistence import AuthRepository
from echo_masque.persistence.character_learned_state_models import CharacterLearnedStateRecord
from echo_masque.persistence.conversation_topic_repository import ConversationTopicRepository
from echo_masque.persistence.database import Database
from echo_masque.persistence.memory_vnext_models import ConversationMemoryVNextRecord
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
    subject_label: str = ""
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


class MemoryInspectionView(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    character_card_id: str
    connection_id: str
    guild_id: str
    scope_type: str
    subject_user_id: str
    topic_id: str
    memory_type: str
    content: str
    confidence: float
    importance: float
    status: str
    provenance_episode_ids: tuple[str, ...] = ()
    source_message_ids: tuple[str, ...] = ()
    supersedes_memory_id: str = ""
    use_count: int = 0
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    created_at: datetime
    updated_at: datetime
    last_used_at: datetime | None = None


class CharacterMemoryView(BaseModel):
    model_config = ConfigDict(frozen=True)

    character_card_id: str
    character_display_name: str
    connection_id: str
    guild_id: str
    items: tuple[MemoryInspectionView, ...] = ()


class TopicDeleteImpactView(BaseModel):
    model_config = ConfigDict(frozen=True)

    topic_id: str
    topic_found: bool
    topics: int
    episodes: int
    memories: int
    wiki_pages: int
    authority_edges: int
    checkpoints: int
    learned_states: int
    graph_nodes: int
    graph_edges: int
    semantic_vectors: int
    total_derived_records: int
    raw_source_messages_deleted: int = 0


class DerivedResetView(BaseModel):
    model_config = ConfigDict(frozen=True)

    topics: int = 0
    episodes: int = 0
    memories: int = 0
    wiki_pages: int = 0
    authority_edges: int = 0
    checkpoints: int = 0
    learned_states: int = 0
    graph_nodes: int = 0
    graph_edges: int = 0
    semantic_vectors: int = 0
    raw_source_messages_deleted: int = 0


class TopicScopeResetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connection_id: str = Field(min_length=1, max_length=64)
    guild_id: str = Field(min_length=1, max_length=200)
    channel_id: str = Field(min_length=1, max_length=200)
    thread_id: str = Field(default="", max_length=200)
    confirm: bool = False


class MemoryResetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connection_id: str = Field(min_length=1, max_length=64)
    guild_id: str = Field(min_length=1, max_length=200)
    confirm: bool = False


def _database(request: Request) -> Database:
    return cast(Database, request.app.state.database)


def _repository(request: Request) -> Repository:
    return cast(Repository, request.app.state.repository)


def _auth_repository(request: Request) -> AuthRepository:
    return cast(AuthRepository, request.app.state.auth_repository)


def _governance(request: Request) -> ConversationIntelligenceGovernanceService:
    return ConversationIntelligenceGovernanceService(_database(request))


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


def _subject_label(
    topics: ConversationTopicRepository,
    *,
    owner_id: str,
    subject_type: str,
    subject_key: str,
) -> str:
    if subject_type != "topic":
        return subject_key
    topic_id = subject_key.removeprefix("topic:").strip()
    if not topic_id:
        return subject_key
    topic = topics.get(topic_id, owner_id)
    if topic is None or not topic.topic_label.strip():
        return subject_key
    return topic.topic_label.strip()


def _memory_view(record: ConversationMemoryVNextRecord) -> MemoryInspectionView:
    return MemoryInspectionView(
        id=record.id,
        character_card_id=record.character_card_id,
        connection_id=record.connection_id,
        guild_id=record.guild_id,
        scope_type=record.scope_type,
        subject_user_id=record.subject_user_id,
        topic_id=record.topic_id,
        memory_type=record.memory_type,
        content=record.content,
        confidence=record.confidence,
        importance=record.importance,
        status=record.status,
        provenance_episode_ids=_json_list(record.provenance_episode_ids_json),
        source_message_ids=_json_list(record.source_message_ids_json),
        supersedes_memory_id=record.supersedes_memory_id,
        use_count=record.use_count,
        valid_from=_aware(record.valid_from),
        valid_to=_aware(record.valid_to),
        created_at=_aware(record.created_at) or record.created_at,
        updated_at=_aware(record.updated_at) or record.updated_at,
        last_used_at=_aware(record.last_used_at),
    )


def _impact_view(impact: TopicDerivedImpact) -> TopicDeleteImpactView:
    return TopicDeleteImpactView(
        topic_id=impact.topic_id,
        topic_found=impact.topic_found,
        topics=int(impact.topic_found),
        episodes=impact.episodes,
        memories=impact.memories,
        wiki_pages=impact.wiki_pages,
        authority_edges=impact.authority_edges,
        checkpoints=impact.checkpoints,
        learned_states=impact.learned_states,
        graph_nodes=impact.graph_nodes,
        graph_edges=impact.graph_edges,
        semantic_vectors=impact.semantic_vectors,
        total_derived_records=impact.total_derived_records,
    )


def _reset_view(result: DerivedResetResult) -> DerivedResetView:
    return DerivedResetView(**result.__dict__)


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
    topics = ConversationTopicRepository(database)
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
                subject_label=_subject_label(
                    topics,
                    owner_id=user.id,
                    subject_type=record.subject_type,
                    subject_key=record.subject_key,
                ),
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


@router.get(
    "/characters/{character_card_id}/memories",
    response_model=CharacterMemoryView,
)
def inspect_character_memories(
    character_card_id: str,
    request: Request,
    user: CurrentUserDependency,
    connection_id: str = Query(min_length=1, max_length=64),
    guild_id: str = Query(min_length=1, max_length=200),
    status: str = Query(default="", max_length=24),
    limit: int = Query(default=200, ge=1, le=500),
) -> CharacterMemoryView:
    card = _repository(request).get_character_card(character_card_id, user.id)
    if card is None:
        raise HTTPException(status_code=404, detail="Character Card not found.")
    records = _governance(request).list_character_memories(
        owner_id=user.id,
        character_card_id=character_card_id,
        connection_id=connection_id,
        guild_id=guild_id,
        status=status,
        limit=limit,
    )
    return CharacterMemoryView(
        character_card_id=character_card_id,
        character_display_name=card.display_name,
        connection_id=connection_id,
        guild_id=guild_id,
        items=tuple(_memory_view(item) for item in records),
    )


@router.post("/topics/{topic_id}/archive", response_model=TopicInspectionView)
def archive_topic(
    topic_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> TopicInspectionView:
    try:
        record = _governance(request).archive_topic(owner_id=user.id, topic_id=topic_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Topic not found.") from exc
    _auth_repository(request).audit(
        actor_user_id=user.id,
        action="conversation_intelligence.topic_archived",
        resource_type="conversation_topic",
        resource_id=topic_id,
    )
    return TopicInspectionView(
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


@router.get("/topics/{topic_id}/delete-impact", response_model=TopicDeleteImpactView)
def inspect_topic_delete_impact(
    topic_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> TopicDeleteImpactView:
    impact = _governance(request).topic_delete_impact(owner_id=user.id, topic_id=topic_id)
    if not impact.topic_found:
        raise HTTPException(status_code=404, detail="Topic not found.")
    return _impact_view(impact)


@router.delete("/topics/{topic_id}/derived", response_model=TopicDeleteImpactView)
def delete_topic_derived(
    topic_id: str,
    request: Request,
    user: CurrentUserDependency,
    confirm: bool = Query(default=False),
) -> TopicDeleteImpactView:
    if not confirm:
        raise HTTPException(
            status_code=409,
            detail="Set confirm=true after reviewing delete-impact. Raw Discord source messages are never deleted.",
        )
    impact = _governance(request).delete_topic_derived(owner_id=user.id, topic_id=topic_id)
    if not impact.topic_found:
        raise HTTPException(status_code=404, detail="Topic not found.")
    _auth_repository(request).audit(
        actor_user_id=user.id,
        action="conversation_intelligence.topic_derived_deleted",
        resource_type="conversation_topic",
        resource_id=topic_id,
        metadata={
            "derived_records": impact.total_derived_records,
            "raw_source_messages_deleted": 0,
        },
    )
    return _impact_view(impact)


@router.post("/memories/{memory_id}/invalidate", response_model=MemoryInspectionView)
def invalidate_memory(
    memory_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> MemoryInspectionView:
    try:
        memory = _governance(request).invalidate_memory(owner_id=user.id, memory_id=memory_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Memory not found.") from exc
    _auth_repository(request).audit(
        actor_user_id=user.id,
        action="conversation_intelligence.memory_invalidated",
        resource_type="conversation_memory_vnext",
        resource_id=memory_id,
    )
    return _memory_view(memory)


@router.delete("/memories/{memory_id}", status_code=204)
def delete_memory(
    memory_id: str,
    request: Request,
    user: CurrentUserDependency,
    confirm: bool = Query(default=False),
) -> None:
    if not confirm:
        raise HTTPException(status_code=409, detail="Set confirm=true to permanently delete this derived Memory.")
    if not _governance(request).delete_memory(owner_id=user.id, memory_id=memory_id):
        raise HTTPException(status_code=404, detail="Memory not found.")
    _auth_repository(request).audit(
        actor_user_id=user.id,
        action="conversation_intelligence.memory_deleted",
        resource_type="conversation_memory_vnext",
        resource_id=memory_id,
    )


@router.post(
    "/characters/{character_card_id}/memories/reset",
    response_model=DerivedResetView,
)
def reset_character_memories(
    character_card_id: str,
    payload: MemoryResetRequest,
    request: Request,
    user: CurrentUserDependency,
) -> DerivedResetView:
    if not payload.confirm:
        raise HTTPException(status_code=409, detail="Set confirm=true to reset derived Memories for this Character/server.")
    card = _repository(request).get_character_card(character_card_id, user.id)
    if card is None:
        raise HTTPException(status_code=404, detail="Character Card not found.")
    count = _governance(request).reset_character_memories(
        owner_id=user.id,
        character_card_id=character_card_id,
        connection_id=payload.connection_id,
        guild_id=payload.guild_id,
    )
    _auth_repository(request).audit(
        actor_user_id=user.id,
        action="conversation_intelligence.character_memories_reset",
        resource_type="character_card",
        resource_id=character_card_id,
        metadata={
            "connection_id": payload.connection_id,
            "guild_id": payload.guild_id,
            "memories": count,
            "raw_source_messages_deleted": 0,
        },
    )
    return DerivedResetView(memories=count)


@router.post("/topics/reset-scope", response_model=DerivedResetView)
def reset_topic_scope(
    payload: TopicScopeResetRequest,
    request: Request,
    user: CurrentUserDependency,
) -> DerivedResetView:
    if not payload.confirm:
        raise HTTPException(status_code=409, detail="Set confirm=true to reset derived Topic intelligence for this scope.")
    result = _governance(request).reset_topic_scope(
        owner_id=user.id,
        connection_id=payload.connection_id,
        guild_id=payload.guild_id,
        channel_id=payload.channel_id,
        thread_id=payload.thread_id,
    )
    _auth_repository(request).audit(
        actor_user_id=user.id,
        action="conversation_intelligence.topic_scope_reset",
        resource_type="discord_conversation_scope",
        resource_id=f"{payload.connection_id}:{payload.guild_id}:{payload.channel_id}:{payload.thread_id}",
        metadata={
            "topics": result.topics,
            "memories": result.memories,
            "raw_source_messages_deleted": 0,
        },
    )
    return _reset_view(result)


__all__ = ["router"]
