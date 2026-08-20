"""Owner-facing observability for Intelligence Core v3 Conversation Structure."""

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from echo_masque.api.dependencies import CurrentUserDependency
from echo_masque.persistence.conversation_structure_repository import (
    ConversationStructureRepository,
)
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord

router = APIRouter(tags=["deployments"])


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
    # Temporary read aliases keep the existing Portal readable while Phase 9 replaces its UI.
    label: str
    summary: str
    keywords: list[str] = Field(default_factory=list)


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
    # Computed compatibility aliases. Segment storage no longer owns Thread assignment.
    semantic_thread_id: str
    thread_action: str
    thread_evidence: bool


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
    created_at: str


class DeploymentConversationStructureView(BaseModel):
    deployment_id: str
    threads: list[ConversationThreadObservation] = Field(default_factory=list)
    segments: list[ConversationSegmentObservation] = Field(default_factory=list)
    relations: list[MessageRelationObservation] = Field(default_factory=list)


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
    repository = ConversationStructureRepository(database)
    threads = repository.recent_threads_for_server(
        owner_id=user.id,
        connection_id=deployment.connection_id,
        guild_id=deployment.workspace_id,
        limit=20,
    )
    segments = repository.recent_segments(
        owner_id=user.id,
        connection_id=deployment.connection_id,
        guild_id=deployment.workspace_id,
        limit=limit,
    )
    relations = repository.recent_relations(
        owner_id=user.id,
        connection_id=deployment.connection_id,
        guild_id=deployment.workspace_id,
        limit=min(limit * 2, 300),
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
                label=item.canonical_label,
                summary=item.working_summary or item.anchor_summary,
                keywords=[],
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
                semantic_thread_id=item.semantic_thread_id,
                thread_action=item.thread_action,
                thread_evidence=item.thread_evidence,
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
                created_at=item.created_at.isoformat(),
            )
            for item in relations
        ],
    )


__all__ = ["router"]
