"""Owner-facing observability for Intelligence Core v3 conversation and knowledge state."""

import json

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, or_, select

from echo_masque.api.dependencies import CurrentUserDependency
from echo_masque.pagination import decode_time_cursor, encode_time_cursor
from echo_masque.persistence.belief_models import (
    BeliefEvidenceDependencyRecord,
    BeliefV3Record,
)
from echo_masque.persistence.conversation_runtime_repository import (
    ConversationRuntimeRepository,
)
from echo_masque.persistence.conversation_structure_repository import (
    ConversationStructureRepository,
)
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord
from echo_masque.persistence.entity_evidence_repository import EntityEvidenceRepository
from echo_masque.persistence.social_intelligence_models import (
    ImpressionV3Record,
    SocialEventV3Record,
)

router = APIRouter(tags=["deployments"])


def _decode(raw: str) -> list[str]:
    try:
        value = json.loads(raw or "[]")
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str)]


class ConversationThreadObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    canonical_label: str
    anchor_summary: str
    working_summary: str
    representative_segment_ids: list[str] = Field(default_factory=list)
    participant_ids: list[str] = Field(default_factory=list)
    active_entity_ids: list[str] = Field(default_factory=list)
    status: str
    last_active_at: str


class ConversationSegmentObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    burst_id: str
    message_ids: list[str] = Field(default_factory=list)
    participant_ids: list[str] = Field(default_factory=list)
    kind: str
    summary: str
    thread_id: str
    membership_relation: str
    membership_confidence: float
    confidence: float
    source: str
    created_at: str


class MessageRelationObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    source_message_id: str
    source_author_id: str
    source_author_display_name: str
    relation_class: str
    relation_type: str
    target_ref_type: str
    target_ref: str
    target_author_id: str
    target_author_display_name: str
    confidence: float
    source: str
    evidence_refs: list[str] = Field(default_factory=list)
    status: str
    supersedes_relation_id: str
    created_at: str


class EpisodeObservation(BaseModel):
    id: str
    conversation_thread_id: str
    segment_ids: list[str] = Field(default_factory=list)
    source_message_ids: list[str] = Field(default_factory=list)
    participant_ids: list[str] = Field(default_factory=list)
    entity_ids: list[str] = Field(default_factory=list)
    media_refs: list[str] = Field(default_factory=list)
    summary: str
    key_events: list[str] = Field(default_factory=list)
    status: str
    checkpoint_reason: str
    ended_at: str


class EntityObservation(BaseModel):
    id: str
    entity_type: str
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    status: str
    merged_into_entity_id: str
    metadata: dict[str, str] = Field(default_factory=dict)
    source_refs: list[str] = Field(default_factory=list)


class KnowledgeGapObservation(BaseModel):
    id: str
    entity_id: str
    missing_fields: list[str] = Field(default_factory=list)
    importance: float
    resolution_state: str
    discovery_requested: bool
    possible_sources: list[str] = Field(default_factory=list)
    resolution_evidence_refs: list[str] = Field(default_factory=list)


class BeliefObservation(BaseModel):
    id: str
    character_card_id: str
    subject_entity_id: str
    subject_ref: str
    predicate: str
    value_text: str
    authority_class: str
    authority_score: float
    confidence: float
    status: str
    authored: bool
    evidence_refs: list[str] = Field(default_factory=list)
    dependency_edge_ids: list[str] = Field(default_factory=list)
    supersedes_belief_id: str
    updated_at: str


class SocialEventObservation(BaseModel):
    id: str
    source_deployment_id: str
    target_type: str
    target_key: str
    event_type: str
    confidence: float
    status: str
    source_relation_id: str
    source_segment_id: str
    source_episode_id: str
    reason: str
    created_at: str


class ImpressionObservation(BaseModel):
    id: str
    source_deployment_id: str
    target_type: str
    target_key: str
    summary: str
    observations: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    confidence: float
    status: str
    supersedes_impression_id: str
    updated_at: str


class CursorPaginationView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    next_cursor: str | None = None
    has_more: bool = False


class ConversationStructurePaginationView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    threads: CursorPaginationView = Field(default_factory=CursorPaginationView)
    segments: CursorPaginationView = Field(default_factory=CursorPaginationView)
    relations: CursorPaginationView = Field(default_factory=CursorPaginationView)
    episodes: CursorPaginationView = Field(default_factory=CursorPaginationView)
    entities: CursorPaginationView = Field(default_factory=CursorPaginationView)
    knowledge_gaps: CursorPaginationView = Field(default_factory=CursorPaginationView)
    beliefs: CursorPaginationView = Field(default_factory=CursorPaginationView)
    social_events: CursorPaginationView = Field(default_factory=CursorPaginationView)
    impressions: CursorPaginationView = Field(default_factory=CursorPaginationView)


class DeploymentConversationStructureView(BaseModel):
    deployment_id: str
    threads: list[ConversationThreadObservation] = Field(default_factory=list)
    segments: list[ConversationSegmentObservation] = Field(default_factory=list)
    relations: list[MessageRelationObservation] = Field(default_factory=list)
    episodes: list[EpisodeObservation] = Field(default_factory=list)
    entities: list[EntityObservation] = Field(default_factory=list)
    knowledge_gaps: list[KnowledgeGapObservation] = Field(default_factory=list)
    beliefs: list[BeliefObservation] = Field(default_factory=list)
    social_events: list[SocialEventObservation] = Field(default_factory=list)
    impressions: list[ImpressionObservation] = Field(default_factory=list)
    pagination: ConversationStructurePaginationView = Field(
        default_factory=ConversationStructurePaginationView
    )


@router.get(
    "/deployments/{deployment_id}/conversation-structure",
    response_model=DeploymentConversationStructureView,
)
def deployment_conversation_structure(
    deployment_id: str,
    request: Request,
    user: CurrentUserDependency,
    limit: int = Query(default=50, ge=1, le=200),
    threads_cursor: str | None = Query(default=None, max_length=1000),
    segments_cursor: str | None = Query(default=None, max_length=1000),
    relations_cursor: str | None = Query(default=None, max_length=1000),
    episodes_cursor: str | None = Query(default=None, max_length=1000),
    entities_cursor: str | None = Query(default=None, max_length=1000),
    knowledge_gaps_cursor: str | None = Query(default=None, max_length=1000),
    beliefs_cursor: str | None = Query(default=None, max_length=1000),
    social_events_cursor: str | None = Query(default=None, max_length=1000),
    impressions_cursor: str | None = Query(default=None, max_length=1000),
) -> DeploymentConversationStructureView:
    database = request.app.state.deployment_repository.database
    with database.session() as session:
        deployment = session.get(CharacterDeploymentRecord, deployment_id)
        if deployment is None or deployment.owner_id != user.id:
            raise HTTPException(status_code=404, detail="Deployment not found.")
    structure = ConversationStructureRepository(database)
    runtime = ConversationRuntimeRepository(database)
    entity_repo = EntityEvidenceRepository(database)
    try:
        threads, threads_next_cursor = structure.recent_threads_for_server_page(
            owner_id=user.id,
            connection_id=deployment.connection_id,
            guild_id=deployment.workspace_id,
            limit=min(limit, 30),
            cursor=threads_cursor,
        )
        segments, segments_next_cursor = structure.recent_segments_page(
            owner_id=user.id,
            connection_id=deployment.connection_id,
            guild_id=deployment.workspace_id,
            limit=limit,
            cursor=segments_cursor,
        )
        relations, relations_next_cursor = structure.recent_relations_page(
            owner_id=user.id,
            connection_id=deployment.connection_id,
            guild_id=deployment.workspace_id,
            limit=min(limit * 2, 300),
            cursor=relations_cursor,
        )
        episodes, episodes_next_cursor = runtime.recent_episodes_page(
            owner_id=user.id,
            connection_id=deployment.connection_id,
            guild_id=deployment.workspace_id,
            limit=limit,
            cursor=episodes_cursor,
        )
        entities, entities_next_cursor = entity_repo.recent_entities_page(
            owner_id=user.id,
            connection_id=deployment.connection_id,
            guild_id=deployment.workspace_id,
            limit=limit,
            cursor=entities_cursor,
        )
        gaps, gaps_next_cursor = entity_repo.unresolved_gaps_page(
            owner_id=user.id,
            connection_id=deployment.connection_id,
            guild_id=deployment.workspace_id,
            limit=limit,
            cursor=knowledge_gaps_cursor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    with database.session() as session:
        belief_query = select(BeliefV3Record).where(
            BeliefV3Record.owner_id == user.id,
            BeliefV3Record.connection_id == deployment.connection_id,
            BeliefV3Record.guild_id == deployment.workspace_id,
            (BeliefV3Record.character_card_id == "")
            | (BeliefV3Record.character_card_id == deployment.character_card_id),
        )
        social_event_query = select(SocialEventV3Record).where(
            SocialEventV3Record.owner_id == user.id,
            SocialEventV3Record.source_deployment_id == deployment.id,
        )
        impression_query = select(ImpressionV3Record).where(
            ImpressionV3Record.owner_id == user.id,
            ImpressionV3Record.source_deployment_id == deployment.id,
        )
        try:
            if beliefs_cursor:
                updated_at, identifier = decode_time_cursor(beliefs_cursor)
                belief_query = belief_query.where(
                    or_(
                        BeliefV3Record.updated_at < updated_at,
                        and_(
                            BeliefV3Record.updated_at == updated_at,
                            BeliefV3Record.id < identifier,
                        ),
                    )
                )
            if social_events_cursor:
                created_at, identifier = decode_time_cursor(social_events_cursor)
                social_event_query = social_event_query.where(
                    or_(
                        SocialEventV3Record.created_at < created_at,
                        and_(
                            SocialEventV3Record.created_at == created_at,
                            SocialEventV3Record.id < identifier,
                        ),
                    )
                )
            if impressions_cursor:
                updated_at, identifier = decode_time_cursor(impressions_cursor)
                impression_query = impression_query.where(
                    or_(
                        ImpressionV3Record.updated_at < updated_at,
                        and_(
                            ImpressionV3Record.updated_at == updated_at,
                            ImpressionV3Record.id < identifier,
                        ),
                    )
                )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        belief_records = list(
            session.scalars(
                belief_query.order_by(
                    BeliefV3Record.updated_at.desc(), BeliefV3Record.id.desc()
                ).limit(limit + 1)
            )
        )
        beliefs_has_more = len(belief_records) > limit
        belief_records = belief_records[:limit]
        belief_ids = [item.id for item in belief_records]
        if belief_ids:
            dependencies = list(
                session.scalars(
                    select(BeliefEvidenceDependencyRecord).where(
                        BeliefEvidenceDependencyRecord.owner_id == user.id,
                        BeliefEvidenceDependencyRecord.belief_id.in_(belief_ids),
                    )
                )
            )
        else:
            dependencies = []
        dependency_map: dict[str, list[str]] = {}
        for item in dependencies:
            dependency_map.setdefault(item.belief_id, []).append(item.evidence_edge_id)
        social_events = list(
            session.scalars(
                social_event_query.order_by(
                    SocialEventV3Record.created_at.desc(), SocialEventV3Record.id.desc()
                ).limit(limit + 1)
            )
        )
        social_events_has_more = len(social_events) > limit
        social_events = social_events[:limit]
        impressions = list(
            session.scalars(
                impression_query.order_by(
                    ImpressionV3Record.updated_at.desc(), ImpressionV3Record.id.desc()
                ).limit(limit + 1)
            )
        )
        impressions_has_more = len(impressions) > limit
        impressions = impressions[:limit]
    beliefs_next_cursor = (
        encode_time_cursor(belief_records[-1].updated_at, belief_records[-1].id)
        if beliefs_has_more and belief_records
        else None
    )
    social_events_next_cursor = (
        encode_time_cursor(social_events[-1].created_at, social_events[-1].id)
        if social_events_has_more and social_events
        else None
    )
    impressions_next_cursor = (
        encode_time_cursor(impressions[-1].updated_at, impressions[-1].id)
        if impressions_has_more and impressions
        else None
    )
    return DeploymentConversationStructureView(
        deployment_id=deployment_id,
        threads=[
            ConversationThreadObservation(
                id=item.id,
                canonical_label=item.canonical_label,
                anchor_summary=item.anchor_summary,
                working_summary=item.working_summary,
                representative_segment_ids=list(item.representative_segment_ids),
                participant_ids=list(item.participant_ids),
                active_entity_ids=list(item.active_entity_ids),
                status=item.status,
                last_active_at=item.last_active_at.isoformat(),
            )
            for item in threads
        ],
        segments=[
            ConversationSegmentObservation(
                id=item.id,
                burst_id=item.burst_id,
                message_ids=list(item.message_ids),
                participant_ids=list(item.participant_ids),
                kind=item.kind,
                summary=item.summary,
                thread_id=item.thread_id,
                membership_relation=item.membership_relation,
                membership_confidence=item.membership_confidence,
                confidence=item.confidence,
                source=item.source,
                created_at=item.created_at.isoformat(),
            )
            for item in segments
        ],
        relations=[
            MessageRelationObservation(
                id=item.id,
                source_message_id=item.source_message_id,
                source_author_id=item.source_author_id,
                source_author_display_name=item.source_author_display_name,
                relation_class=item.relation_class,
                relation_type=item.relation_type,
                target_ref_type=item.target_ref_type,
                target_ref=item.target_ref,
                target_author_id=item.target_author_id,
                target_author_display_name=item.target_author_display_name,
                confidence=item.confidence,
                source=item.source,
                evidence_refs=list(item.evidence_refs),
                status=item.status,
                supersedes_relation_id=item.supersedes_relation_id,
                created_at=item.created_at.isoformat(),
            )
            for item in relations
        ],
        episodes=[
            EpisodeObservation(
                id=item.id,
                conversation_thread_id=item.conversation_thread_id,
                segment_ids=list(item.segment_ids),
                source_message_ids=list(item.source_message_ids),
                participant_ids=list(item.participant_ids),
                entity_ids=list(item.entity_ids),
                media_refs=list(item.media_refs),
                summary=item.summary,
                key_events=list(item.key_events),
                status=item.status,
                checkpoint_reason=item.checkpoint_reason,
                ended_at=item.ended_at.isoformat(),
            )
            for item in episodes
        ],
        entities=[
            EntityObservation(
                id=item.id,
                entity_type=item.entity_type,
                canonical_name=item.canonical_name,
                aliases=list(item.aliases),
                status=item.status,
                merged_into_entity_id=item.merged_into_entity_id,
                metadata=item.metadata,
                source_refs=list(item.source_refs),
            )
            for item in entities
        ],
        knowledge_gaps=[
            KnowledgeGapObservation(
                id=item.id,
                entity_id=item.entity_id,
                missing_fields=list(item.missing_fields),
                importance=item.importance,
                resolution_state=item.resolution_state,
                discovery_requested=item.discovery_requested,
                possible_sources=list(item.possible_sources),
                resolution_evidence_refs=list(item.resolution_evidence_refs),
            )
            for item in gaps
        ],
        beliefs=[
            BeliefObservation(
                id=item.id,
                character_card_id=item.character_card_id,
                subject_entity_id=item.subject_entity_id,
                subject_ref=item.subject_ref,
                predicate=item.predicate,
                value_text=item.value_text,
                authority_class=item.authority_class,
                authority_score=item.authority_score,
                confidence=item.confidence,
                status=item.status,
                authored=item.authored,
                evidence_refs=_decode(item.evidence_refs_json),
                dependency_edge_ids=dependency_map.get(item.id, []),
                supersedes_belief_id=item.supersedes_belief_id,
                updated_at=item.updated_at.isoformat(),
            )
            for item in belief_records
        ],
        social_events=[
            SocialEventObservation(
                id=item.id,
                source_deployment_id=item.source_deployment_id,
                target_type=item.target_type,
                target_key=item.target_key,
                event_type=item.event_type,
                confidence=item.confidence,
                status=item.status,
                source_relation_id=item.source_relation_id,
                source_segment_id=item.source_segment_id,
                source_episode_id=item.source_episode_id,
                reason=item.reason,
                created_at=item.created_at.isoformat(),
            )
            for item in social_events
        ],
        impressions=[
            ImpressionObservation(
                id=item.id,
                source_deployment_id=item.source_deployment_id,
                target_type=item.target_type,
                target_key=item.target_key,
                summary=item.summary,
                observations=_decode(item.observations_json),
                evidence_refs=_decode(item.evidence_refs_json),
                confidence=item.confidence,
                status=item.status,
                supersedes_impression_id=item.supersedes_impression_id,
                updated_at=item.updated_at.isoformat(),
            )
            for item in impressions
        ],
        pagination=ConversationStructurePaginationView(
            threads=CursorPaginationView(
                next_cursor=threads_next_cursor, has_more=threads_next_cursor is not None
            ),
            segments=CursorPaginationView(
                next_cursor=segments_next_cursor, has_more=segments_next_cursor is not None
            ),
            relations=CursorPaginationView(
                next_cursor=relations_next_cursor, has_more=relations_next_cursor is not None
            ),
            episodes=CursorPaginationView(
                next_cursor=episodes_next_cursor, has_more=episodes_next_cursor is not None
            ),
            entities=CursorPaginationView(
                next_cursor=entities_next_cursor, has_more=entities_next_cursor is not None
            ),
            knowledge_gaps=CursorPaginationView(
                next_cursor=gaps_next_cursor, has_more=gaps_next_cursor is not None
            ),
            beliefs=CursorPaginationView(
                next_cursor=beliefs_next_cursor, has_more=beliefs_next_cursor is not None
            ),
            social_events=CursorPaginationView(
                next_cursor=social_events_next_cursor,
                has_more=social_events_next_cursor is not None,
            ),
            impressions=CursorPaginationView(
                next_cursor=impressions_next_cursor, has_more=impressions_next_cursor is not None
            ),
        ),
    )


__all__ = ["router"]
