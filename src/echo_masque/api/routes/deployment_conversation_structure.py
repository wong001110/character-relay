"""Owner-facing observability for Burst Segments and concurrent Semantic Threads."""

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from echo_masque.api.dependencies import CurrentUserDependency
from echo_masque.persistence.conversation_segment_models import SemanticThreadRecord
from echo_masque.persistence.conversation_segment_repository import ConversationSegmentRepository
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord

router = APIRouter(tags=["deployments"])


class SemanticThreadObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    label: str
    summary: str
    keywords: list[str] = Field(default_factory=list)
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
    semantic_thread_id: str
    thread_action: str
    thread_evidence: bool
    confidence: float
    source: str
    created_at: str


class DeploymentConversationStructureView(BaseModel):
    deployment_id: str
    threads: list[SemanticThreadObservation] = Field(default_factory=list)
    segments: list[ConversationSegmentObservation] = Field(default_factory=list)


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
        thread_records = list(
            session.scalars(
                select(SemanticThreadRecord)
                .where(
                    SemanticThreadRecord.owner_id == user.id,
                    SemanticThreadRecord.connection_id == deployment.connection_id,
                    SemanticThreadRecord.guild_id == deployment.workspace_id,
                    SemanticThreadRecord.status != "archived",
                )
                .order_by(SemanticThreadRecord.last_active_at.desc())
                .limit(20)
            )
        )
    repository = ConversationSegmentRepository(database)
    threads = tuple(repository.thread_view(item) for item in thread_records)
    segments = repository.recent_segments(
        owner_id=user.id,
        connection_id=deployment.connection_id,
        guild_id=deployment.workspace_id,
        limit=limit,
    )
    return DeploymentConversationStructureView(
        deployment_id=deployment_id,
        threads=[
            SemanticThreadObservation(
                id=item.id,
                label=item.label,
                summary=item.summary,
                keywords=list(item.keywords),
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
                semantic_thread_id=item.semantic_thread_id,
                thread_action=item.thread_action,
                thread_evidence=item.thread_evidence,
                confidence=item.confidence,
                source=item.source,
                created_at=item.created_at.isoformat(),
            )
            for item in segments
        ],
    )


__all__ = ["router"]
