"""Owner-facing observability for Intelligence Core v3 conversation and knowledge state."""

import json

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from echo_masque.api.dependencies import CurrentUserDependency
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
    relation_class: str
    relation_type: str
    target_ref_type: str
    target_ref: str
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
    metadata: dict[str, object] = Field(default_factory=dict)
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


@router.get(
    "/deployments/{deployment_id}/conversation-structure",
    response_model=DeploymentConversationStructureView,
)
def deployment_conversation_structure(
    deployment_id: str,
    request: Request,
    user: CurrentUserDependency,
    limit: int = Query(default=50, ge=1, le=200),
) -> DeploymentConversationStructureView:
    database = request.app.state.deployment_repository.database
    with database.session() as session:
        deployment = session.get(CharacterDeploymentRecord, deployment_id)
        if deployment is None or deployment.owner_id != user.id:
            raise HTTPException(status_code=404, detail="Deployment not found.")
    structure = ConversationStructureRepository(database)
    runtime = ConversationRuntimeRepository(database)
    entity_repo = EntityEvidenceRepository(database)
    threads = structure.recent_threads_for_server(
        owner_id=user.id,
        connection_id=deployment.connection_id,
        guild_id=deployment.workspace_id,
        limit=30,
    )
    segments = structure.recent_segments(
        owner_id=user.id,
        connection_id=deployment.connection_id,
        guild_id=deployment.workspace_id,
        limit=limit,
    )
    relations = structure.recent_relations(
        owner_id=user.id,
        connection_id=deployment.connection_id,
        guild_id=deployment.workspace_id,
        limit=min(limit * 2, 300),
    )
    episodes = runtime.recent_episodes(
        owner_id=user.id,
        connection_id=deployment.connection_id,
        guild_id=deployment.workspace_id,
        limit=limit,
    )
    entities = entity_repo.recent_entities(
        owner_id=user.id,
        connection_id=deployment.connection_id,
        guild_id=deployment.workspace_id,
        limit=limit,
    )
    gaps = entity_repo.unresolved_gaps(
        owner_id=user.id,
        connection_id=deployment.connection_id,
        guild_id=deployment.workspace_id,
        limit=limit,
    )
    with database.session() as session:
        belief_records = list(
            session.scalars(
                select(BeliefV3Record)
                .where(
                    BeliefV3Record.owner_id == user.id,
                    BeliefV3Record.connection_id == deployment.connection_id,
                    BeliefV3Record.guild_id == deployment.workspace_id,
                    (BeliefV3Record.character_card_id == "")
                    | (BeliefV3Record.character_card_id == deployment.character_card_id),
                )
                .order_by(BeliefV3Record.updated_at.desc())
                .limit(limit)
            )
        )
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
                select(SocialEventV3Record)
                .where(
                    SocialEventV3Record.owner_id == user.id,
                    SocialEventV3Record.source_deployment_id == deployment.id,
                )
                .order_by(SocialEventV3Record.created_at.desc())
                .limit(limit)
            )
        )
        impressions = list(
            session.scalars(
                select(ImpressionV3Record)
                .where(
                    ImpressionV3Record.owner_id == user.id,
                    ImpressionV3Record.source_deployment_id == deployment.id,
                )
                .order_by(ImpressionV3Record.updated_at.desc())
                .limit(limit)
            )
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
                relation_class=item.relation_class,
                relation_type=item.relation_type,
                target_ref_type=item.target_ref_type,
                target_ref=item.target_ref,
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
    )


__all__ = ["router"]
