"""Owner-facing observability for Intelligence Core v3 conversation and knowledge state."""

import json
from typing import Literal, cast

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, or_, select

from echo_masque.api.dependencies import CurrentUserDependency
from echo_masque.belief_revision_v3 import BeliefRevisionService
from echo_masque.knowledge_gap_discovery_v3 import KnowledgeGapEvidenceAcceptance
from echo_masque.pagination import decode_time_cursor, encode_time_cursor
from echo_masque.persistence.belief_models import (
    BeliefEvidenceDependencyRecord,
    BeliefV3Record,
)
from echo_masque.persistence.belief_repository import BeliefRepository, BeliefV3View
from echo_masque.persistence.conversation_runtime_repository import (
    ConversationRuntimeRepository,
)
from echo_masque.persistence.conversation_structure_repository import (
    ConversationStructureRepository,
)
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord
from echo_masque.persistence.entity_evidence_repository import (
    EntityEvidenceRepository,
    KnowledgeGapCandidateView,
    KnowledgeGapView,
)
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


class KnowledgeGapCandidateObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    gap_id: str
    discovery_item_id: str
    source: str
    canonical_key: str
    content_kind: str
    title: str
    creator: str
    url: str
    score: float
    rank_reason: str
    status: str
    validation_method: str
    validated_evidence_ref: str
    reviewed_by: str
    reviewed_at: str | None
    expires_at: str


class KnowledgeGapCandidateListView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[KnowledgeGapCandidateObservation] = Field(default_factory=list)


class KnowledgeGapCandidateReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["accept", "reject"]
    validated_evidence_ref: str = Field(default="", min_length=0, max_length=320)
    resolved_fields: list[str] = Field(default_factory=list, max_length=32)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    canonical_entity: bool = False
    entity_metadata: dict[str, str] = Field(default_factory=dict)


class KnowledgeGapObservation(BaseModel):
    id: str
    entity_id: str
    missing_fields: list[str] = Field(default_factory=list)
    importance: float
    resolution_state: str
    discovery_requested: bool
    possible_sources: list[str] = Field(default_factory=list)
    resolution_evidence_refs: list[str] = Field(default_factory=list)


class KnowledgeGapCandidateReviewView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gap: KnowledgeGapObservation
    candidate: KnowledgeGapCandidateObservation


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


class ManagedBeliefView(BaseModel):
    """One scoped Belief plus the fields needed for an owner review decision."""

    model_config = ConfigDict(extra="forbid")

    id: str
    character_card_id: str
    subject_entity_id: str
    subject_ref: str
    predicate: str
    value_text: str
    scope: str
    authority_class: str
    authority_score: float
    origin: str
    confidence: float
    importance: float
    status: str
    authored: bool
    evidence_refs: list[str] = Field(default_factory=list)
    supersedes_belief_id: str
    valid_from: str | None = None
    valid_to: str | None = None
    stale_after: str | None = None
    updated_at: str

    @classmethod
    def from_belief(cls, belief: BeliefV3View) -> "ManagedBeliefView":
        return cls(
            id=belief.id,
            character_card_id=belief.character_card_id,
            subject_entity_id=belief.subject_entity_id,
            subject_ref=belief.subject_ref,
            predicate=belief.predicate,
            value_text=belief.value_text,
            scope=belief.scope,
            authority_class=belief.authority_class,
            authority_score=belief.authority_score,
            origin=belief.origin,
            confidence=belief.confidence,
            importance=belief.importance,
            status=belief.status,
            authored=belief.authored,
            evidence_refs=list(belief.evidence_refs),
            supersedes_belief_id=belief.supersedes_belief_id,
            valid_from=belief.valid_from.isoformat() if belief.valid_from is not None else None,
            valid_to=belief.valid_to.isoformat() if belief.valid_to is not None else None,
            stale_after=belief.stale_after.isoformat() if belief.stale_after is not None else None,
            updated_at=belief.updated_at.isoformat(),
        )


class BeliefCorrectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value_text: str = Field(min_length=1, max_length=8000)
    domain: Literal["personal", "canonical", "general"] = "general"
    reason: str = Field(min_length=1, max_length=500)
    confidence: float | None = Field(default=None, ge=0, le=1)


class BeliefReviewMutationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=500)


class BeliefMutationView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str
    belief: ManagedBeliefView
    previous_belief_ids: list[str] = Field(default_factory=list)


def _owned_deployment(
    *, deployment_id: str, request: Request, owner_id: str
) -> CharacterDeploymentRecord:
    database = request.app.state.deployment_repository.database
    with database.session() as session:
        deployment = session.get(CharacterDeploymentRecord, deployment_id)
    if deployment is None or deployment.owner_id != owner_id:
        raise HTTPException(status_code=404, detail="Deployment not found.")
    return cast(CharacterDeploymentRecord, deployment)


def _scoped_belief(
    *,
    deployment: CharacterDeploymentRecord,
    belief_id: str,
    request: Request,
    owner_id: str,
) -> tuple[BeliefRepository, BeliefV3View]:
    repository = BeliefRepository(request.app.state.deployment_repository.database)
    belief = repository.get_for_deployment_scope(
        owner_id=owner_id,
        belief_id=belief_id,
        character_card_id=deployment.character_card_id,
        connection_id=deployment.connection_id,
        guild_id=deployment.workspace_id,
    )
    if belief is None:
        # The same response deliberately covers a foreign owner, Character, or server scope.
        raise HTTPException(status_code=404, detail="Belief not found.")
    return repository, belief


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
    "/deployments/{deployment_id}/beliefs/{belief_id}",
    response_model=ManagedBeliefView,
)
def review_deployment_belief(
    deployment_id: str,
    belief_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> ManagedBeliefView:
    """Review one owner-owned Belief without widening deployment scope."""

    deployment = _owned_deployment(deployment_id=deployment_id, request=request, owner_id=user.id)
    _repository, belief = _scoped_belief(
        deployment=deployment, belief_id=belief_id, request=request, owner_id=user.id
    )
    return ManagedBeliefView.from_belief(belief)


@router.post(
    "/deployments/{deployment_id}/beliefs/{belief_id}/correct",
    response_model=BeliefMutationView,
)
def correct_deployment_belief(
    deployment_id: str,
    belief_id: str,
    payload: BeliefCorrectionRequest,
    request: Request,
    user: CurrentUserDependency,
) -> BeliefMutationView:
    """Record an owner correction through the normal revisable-Belief authority policy."""

    deployment = _owned_deployment(deployment_id=deployment_id, request=request, owner_id=user.id)
    repository, belief = _scoped_belief(
        deployment=deployment, belief_id=belief_id, request=request, owner_id=user.id
    )
    if belief.status not in {"active", "provisional", "disputed"}:
        raise HTTPException(status_code=409, detail="Only current Beliefs can be corrected.")
    result = BeliefRevisionService(repository).apply_claim(
        owner_id=user.id,
        character_card_id=deployment.character_card_id,
        connection_id=deployment.connection_id,
        guild_id=deployment.workspace_id,
        subject_entity_id=belief.subject_entity_id,
        subject_ref=belief.subject_ref,
        predicate=belief.predicate,
        value_text=payload.value_text,
        domain=payload.domain,
        source="user_correction",
        # A management correction is recorded as a revision event.  Do not manufacture a raw
        # evidence reference or claim that the old evidence supports the corrected value.
        evidence_refs=(),
        explicit_correction=True,
        candidate_belief_ids=(belief.id,),
        claim_confidence=payload.confidence,
        importance=belief.importance,
        scope=belief.scope,
    )
    if result.belief is None:
        raise HTTPException(status_code=409, detail="Belief correction could not be applied.")
    repository.record_revision_event(
        owner_id=user.id,
        belief_id=result.belief.id,
        previous_belief_id=belief.id,
        subject_ref=belief.subject_ref or belief.subject_entity_id,
        predicate=belief.predicate,
        action="owner_correct",
        reason=payload.reason,
    )
    return BeliefMutationView(
        action=result.action,
        belief=ManagedBeliefView.from_belief(result.belief),
        previous_belief_ids=list(result.previous_belief_ids),
    )


def _reject_or_forget_deployment_belief(
    *,
    action: Literal["reject", "forget"],
    deployment_id: str,
    belief_id: str,
    payload: BeliefReviewMutationRequest,
    request: Request,
    user: CurrentUserDependency,
) -> BeliefMutationView:
    deployment = _owned_deployment(deployment_id=deployment_id, request=request, owner_id=user.id)
    repository, belief = _scoped_belief(
        deployment=deployment, belief_id=belief_id, request=request, owner_id=user.id
    )
    already_rejected = belief.status == "rejected"
    try:
        updated = repository.reject_for_deployment_scope(
            owner_id=user.id,
            belief_id=belief.id,
            character_card_id=deployment.character_card_id,
            connection_id=deployment.connection_id,
            guild_id=deployment.workspace_id,
            # Explicit owner forgetting is permitted for authored memories, but remains a
            # non-destructive status transition.  Ordinary rejection still preserves authored
            # Beliefs against automatic/evidence-derived invalidation.
            allow_authored=action == "forget",
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not already_rejected:
        repository.record_revision_event(
            owner_id=user.id,
            belief_id=updated.id,
            previous_belief_id="",
            subject_ref=updated.subject_ref or updated.subject_entity_id,
            predicate=updated.predicate,
            action=f"owner_{action}",
            reason=payload.reason,
        )
    return BeliefMutationView(
        action=action,
        belief=ManagedBeliefView.from_belief(updated),
        previous_belief_ids=[],
    )


@router.post(
    "/deployments/{deployment_id}/beliefs/{belief_id}/reject",
    response_model=BeliefMutationView,
)
def reject_deployment_belief(
    deployment_id: str,
    belief_id: str,
    payload: BeliefReviewMutationRequest,
    request: Request,
    user: CurrentUserDependency,
) -> BeliefMutationView:
    return _reject_or_forget_deployment_belief(
        action="reject",
        deployment_id=deployment_id,
        belief_id=belief_id,
        payload=payload,
        request=request,
        user=user,
    )


@router.post(
    "/deployments/{deployment_id}/beliefs/{belief_id}/forget",
    response_model=BeliefMutationView,
)
def forget_deployment_belief(
    deployment_id: str,
    belief_id: str,
    payload: BeliefReviewMutationRequest,
    request: Request,
    user: CurrentUserDependency,
) -> BeliefMutationView:
    return _reject_or_forget_deployment_belief(
        action="forget",
        deployment_id=deployment_id,
        belief_id=belief_id,
        payload=payload,
        request=request,
        user=user,
    )


def _candidate_observation(item: KnowledgeGapCandidateView) -> KnowledgeGapCandidateObservation:
    return KnowledgeGapCandidateObservation(
        id=item.id,
        gap_id=item.gap_id,
        discovery_item_id=item.discovery_item_id,
        source=item.source,
        canonical_key=item.canonical_key,
        content_kind=item.content_kind,
        title=item.title,
        creator=item.creator,
        url=item.url,
        score=item.score,
        rank_reason=item.rank_reason,
        status=item.status,
        validation_method=item.validation_method,
        validated_evidence_ref=item.validated_evidence_ref,
        reviewed_by=item.reviewed_by,
        reviewed_at=item.reviewed_at.isoformat() if item.reviewed_at is not None else None,
        expires_at=item.expires_at.isoformat(),
    )


def _gap_observation(item: KnowledgeGapView) -> KnowledgeGapObservation:
    return KnowledgeGapObservation(
        id=str(item.id),
        entity_id=str(item.entity_id),
        missing_fields=list(item.missing_fields),
        importance=float(item.importance),
        resolution_state=str(item.resolution_state),
        discovery_requested=bool(item.discovery_requested),
        possible_sources=list(item.possible_sources),
        resolution_evidence_refs=list(item.resolution_evidence_refs),
    )


def _owner_deployment(
    request: Request, *, deployment_id: str, owner_id: str
) -> CharacterDeploymentRecord:
    database = request.app.state.deployment_repository.database
    with database.session() as session:
        deployment = session.get(CharacterDeploymentRecord, deployment_id)
        if deployment is None or deployment.owner_id != owner_id:
            raise HTTPException(status_code=404, detail="Deployment not found.")
        return cast(CharacterDeploymentRecord, deployment)


@router.get(
    "/deployments/{deployment_id}/knowledge-gaps/{gap_id}/candidates",
    response_model=KnowledgeGapCandidateListView,
)
def list_knowledge_gap_candidates(
    deployment_id: str,
    gap_id: str,
    request: Request,
    user: CurrentUserDependency,
    include_terminal: bool = Query(default=False),
) -> KnowledgeGapCandidateListView:
    deployment = _owner_deployment(request, deployment_id=deployment_id, owner_id=user.id)
    entities = EntityEvidenceRepository(request.app.state.database)
    try:
        entities.gap_for_scope(
            owner_id=user.id,
            connection_id=deployment.connection_id,
            guild_id=deployment.workspace_id,
            gap_id=gap_id,
        )
        candidates = entities.gap_candidates_for_scope(
            owner_id=user.id,
            connection_id=deployment.connection_id,
            guild_id=deployment.workspace_id,
            deployment_id=deployment.id,
            gap_id=gap_id,
            include_terminal=include_terminal,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Knowledge Gap not found.") from exc
    return KnowledgeGapCandidateListView(
        items=[_candidate_observation(item) for item in candidates]
    )


@router.post(
    "/deployments/{deployment_id}/knowledge-gaps/{gap_id}/candidates/{candidate_id}/review",
    response_model=KnowledgeGapCandidateReviewView,
)
def review_knowledge_gap_candidate(
    deployment_id: str,
    gap_id: str,
    candidate_id: str,
    body: KnowledgeGapCandidateReviewRequest,
    request: Request,
    user: CurrentUserDependency,
) -> KnowledgeGapCandidateReviewView:
    deployment = _owner_deployment(request, deployment_id=deployment_id, owner_id=user.id)
    service = request.app.state.knowledge_gap_discovery_service
    entities = EntityEvidenceRepository(request.app.state.database)
    try:
        gap = entities.gap_for_scope(
            owner_id=user.id,
            connection_id=deployment.connection_id,
            guild_id=deployment.workspace_id,
            gap_id=gap_id,
        )
        if body.action == "reject":
            candidate = service.reject_candidate(
                owner_id=user.id,
                connection_id=deployment.connection_id,
                guild_id=deployment.workspace_id,
                deployment_id=deployment.id,
                gap_id=gap.id,
                candidate_id=candidate_id,
                reviewed_by=user.id,
            )
            return KnowledgeGapCandidateReviewView(
                gap=_gap_observation(gap),
                candidate=_candidate_observation(candidate),
            )
        resolved_gap = service.accept_candidate_evidence(
            owner_id=user.id,
            connection_id=deployment.connection_id,
            guild_id=deployment.workspace_id,
            deployment_id=deployment.id,
            gap=gap,
            acceptance=KnowledgeGapEvidenceAcceptance(
                candidate_id=candidate_id,
                validation_method="operator_review",
                validated_evidence_ref=body.validated_evidence_ref,
                resolved_fields=tuple(body.resolved_fields),
                confidence=body.confidence,
                entity_metadata=body.entity_metadata,
                canonical_entity=body.canonical_entity,
            ),
            reviewed_by=user.id,
        )
        candidate = entities.gap_candidate_for_scope(
            owner_id=user.id,
            connection_id=deployment.connection_id,
            guild_id=deployment.workspace_id,
            deployment_id=deployment.id,
            gap_id=gap.id,
            candidate_id=candidate_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Knowledge Gap candidate not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return KnowledgeGapCandidateReviewView(
        gap=_gap_observation(resolved_gap),
        candidate=_candidate_observation(candidate),
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
