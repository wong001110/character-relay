"""Owner-facing observability for Social Model, Conversation Structure, and Participation v3."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Literal, cast

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from echo_masque.api.dependencies import CurrentUserDependency
from echo_masque.character_relationships import CharacterRelationshipService, RelationshipStateView
from echo_masque.knowledge_consolidation_v3 import KnowledgeConsolidationV3Result
from echo_masque.persistence import DeploymentRepository
from echo_masque.persistence.character_relationship_models import DeploymentRelationshipEventRecord
from echo_masque.persistence.conversation_structure_repository import (
    ConversationStructureRepository,
)
from echo_masque.persistence.database import Database
from echo_masque.persistence.deployment_models import (
    CharacterDeploymentRecord,
    DiscordServerProfileRecord,
)
from echo_masque.persistence.discord_identity_models import (
    DeploymentMessageIdentityRecord,
    DiscordGuildActorIdentityRecord,
)
from echo_masque.persistence.models import CharacterCardRecord
from echo_masque.persistence.smart_participation_state_models import (
    SmartParticipationDeploymentStateRecord,
    SmartParticipationReplyDecisionRecord,
    SmartParticipationScopeStateRecord,
)
from echo_masque.social_intelligence_v3 import SocialIntelligenceV3Service

router = APIRouter(tags=["deployments"])


def _database(request: Request) -> Database:
    return cast(DeploymentRepository, request.app.state.deployment_repository).database


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


class RelationshipEvidenceView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dimension: str
    delta: float
    confidence: float
    reason_code: str
    source_message_id: str
    source_burst_id: str
    recorded_at: str


class PersonImpressionProductView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str
    observations: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    confidence: float
    updated_at: str


class RelationshipStateProductView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    familiarity: float
    affinity: float
    trust: float
    comfort: float
    familiarity_baseline: float
    affinity_baseline: float
    trust_baseline: float
    comfort_baseline: float
    last_evidence_at: str


class SocialTargetProductView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_type: Literal["actor", "deployment"]
    target_key: str
    target_kind: Literal["user", "bot", "character", "unknown"]
    label: str
    avatar_url: str = ""
    state: RelationshipStateProductView | None = None
    impression: PersonImpressionProductView | None = None
    recent_evidence: list[RelationshipEvidenceView] = Field(default_factory=list)


class DeploymentSocialIntelligenceView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    deployment_id: str
    character_card_id: str
    character_display_name: str
    connection_id: str
    guild_id: str
    items: list[SocialTargetProductView] = Field(default_factory=list)


class ConversationThreadProductView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    label: str
    summary: str
    keywords: list[str] = Field(default_factory=list)
    status: str
    last_active_at: str


class ConversationSegmentProductView(BaseModel):
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


class ServerConversationStructureProductView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    server_profile_id: str
    connection_id: str
    guild_id: str
    threads: list[ConversationThreadProductView] = Field(default_factory=list)
    segments: list[ConversationSegmentProductView] = Field(default_factory=list)


class ParticipationDeploymentView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    deployment_id: str
    character_card_id: str
    character_display_name: str
    status: str
    participation_mode: str
    last_admitted_at: str | None = None
    last_channel_id: str = ""
    last_thread_id: str = ""


class ParticipationScopeView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    channel_id: str
    thread_id: str
    last_admitted_at: str | None = None
    recent_deployment_id: str
    window_started_at: str | None = None
    window_count: int


class ReplyPlannerDecisionView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    deployment_id: str
    character_card_id: str
    character_display_name: str
    burst_id: str
    source_message_id: str
    channel_id: str
    thread_id: str
    segment_id: str
    semantic_thread_id: str
    score: float
    reason: str
    guidance: str
    plan_kind: str
    authoritative: bool
    resolver_version: str
    created_at: str


class ServerParticipationIntelligenceView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    server_profile_id: str
    resolver_version: str = "conversation-intelligence-v3"
    planner_model: str = "Burst -> Segments -> Conversation Threads -> Participation Planner"
    deployments: list[ParticipationDeploymentView] = Field(default_factory=list)
    scopes: list[ParticipationScopeView] = Field(default_factory=list)
    recent_reply_decisions: list[ReplyPlannerDecisionView] = Field(default_factory=list)


class KnowledgeConsolidationCheckpointView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    source_ref_type: str
    source_ref: str
    wiki_page_id: str
    source_count: int
    utility_status: str


def _server_profile(
    request: Request,
    user: CurrentUserDependency,
    server_profile_id: str,
) -> DiscordServerProfileRecord:
    with _database(request).session() as session:
        profile = session.get(DiscordServerProfileRecord, server_profile_id)
        if profile is None or profile.owner_id != user.id:
            raise HTTPException(status_code=404, detail="Server Profile not found.")
        session.expunge(profile)
        return profile


def _consolidation_result(
    value: KnowledgeConsolidationV3Result,
) -> KnowledgeConsolidationCheckpointView:
    return KnowledgeConsolidationCheckpointView(
        status=value.status,
        source_ref_type=value.source_ref_type,
        source_ref=value.source_ref,
        wiki_page_id=value.wiki_page_id,
        source_count=value.source_count,
        utility_status=value.utility_status,
    )


def _relationship_state(value: RelationshipStateView | None) -> RelationshipStateProductView | None:
    if value is None:
        return None
    return RelationshipStateProductView(
        familiarity=value.familiarity,
        affinity=value.affinity,
        trust=value.trust,
        comfort=value.comfort,
        familiarity_baseline=value.familiarity_baseline,
        affinity_baseline=value.affinity_baseline,
        trust_baseline=value.trust_baseline,
        comfort_baseline=value.comfort_baseline,
        last_evidence_at=value.last_evidence_at.isoformat(),
    )


def _derived_impression(
    state: RelationshipStateView | None,
    events: list[DeploymentRelationshipEventRecord],
) -> PersonImpressionProductView | None:
    if state is None:
        return None
    clauses = [
        "This is currently a familiar interaction partner."
        if state.familiarity >= 0.55
        else "They are becoming a familiar interaction partner."
        if state.familiarity >= 0.15
        else "There is still limited familiarity evidence."
    ]
    for label, value in (
        ("affinity", state.affinity),
        ("trust", state.trust),
        ("comfort", state.comfort),
    ):
        if value >= 0.25:
            clauses.append(f"Current {label} evidence is positive.")
        elif value <= -0.25:
            clauses.append(f"Current {label} evidence is negative.")
    observations: list[str] = []
    for dimension in ("familiarity", "affinity", "trust", "comfort"):
        values = [item for item in events if item.dimension == dimension]
        if not values:
            continue
        net = sum(item.delta * item.confidence for item in values)
        direction = "positive" if net > 0 else "negative" if net < 0 else "mixed"
        observations.append(f"Recent {dimension} evidence is {direction}.")
    evidence_refs = [
        event.source_message_id or event.source_burst_id
        for event in events[:8]
        if event.source_message_id or event.source_burst_id
    ]
    return PersonImpressionProductView(
        summary=" ".join(clauses),
        observations=observations[:6],
        evidence_refs=evidence_refs,
        confidence=min(0.85, 0.35 + min(len(events), 10) * 0.05),
        updated_at=state.last_evidence_at.isoformat(),
    )


@router.get(
    "/deployments/{deployment_id}/social-intelligence",
    response_model=DeploymentSocialIntelligenceView,
)
def deployment_social_intelligence(
    deployment_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> DeploymentSocialIntelligenceView:
    database = _database(request)
    relationships = CharacterRelationshipService(database)
    social = SocialIntelligenceV3Service(database)
    states = relationships.list_states(owner_id=user.id, source_deployment_id=deployment_id)
    state_by_key = {(item.target_type, item.target_key): item for item in states}

    with database.session() as session:
        source = session.get(CharacterDeploymentRecord, deployment_id)
        if source is None or source.owner_id != user.id:
            raise HTTPException(status_code=404, detail="Deployment not found.")
        source_card = session.get(CharacterCardRecord, source.character_card_id)
        source_display_name = (
            source_card.display_name if source_card is not None else source.character_card_id
        )
        source_values = (
            source.id,
            source.character_card_id,
            source.connection_id,
            source.workspace_id,
        )
        events = list(
            session.scalars(
                select(DeploymentRelationshipEventRecord)
                .where(
                    DeploymentRelationshipEventRecord.owner_id == user.id,
                    DeploymentRelationshipEventRecord.source_deployment_id == deployment_id,
                )
                .order_by(DeploymentRelationshipEventRecord.recorded_at.desc())
                .limit(400)
            )
        )
        events_by_key: dict[tuple[str, str], list[DeploymentRelationshipEventRecord]] = defaultdict(
            list
        )
        for event in events:
            key = (event.target_type, event.target_key)
            if len(events_by_key[key]) < 12:
                events_by_key[key].append(event)
        keys = set(state_by_key) | set(events_by_key)
        items: list[SocialTargetProductView] = []
        for target_type, target_key in keys:
            target_kind: Literal["user", "bot", "character", "unknown"] = "unknown"
            label = target_key
            avatar_url = ""
            if target_type == "deployment":
                target = session.get(CharacterDeploymentRecord, target_key)
                if target is not None and target.owner_id == user.id:
                    card = session.get(CharacterCardRecord, target.character_card_id)
                    identity = session.get(DeploymentMessageIdentityRecord, target.id)
                    label = card.display_name if card is not None else target.character_card_id
                    avatar_url = identity.avatar_url if identity is not None else ""
                    target_kind = "character"
            elif target_type == "actor":
                actor = session.scalar(
                    select(DiscordGuildActorIdentityRecord).where(
                        DiscordGuildActorIdentityRecord.owner_id == user.id,
                        DiscordGuildActorIdentityRecord.connection_id == source_values[2],
                        DiscordGuildActorIdentityRecord.guild_id == source_values[3],
                        DiscordGuildActorIdentityRecord.user_id == target_key,
                    )
                )
                if actor is not None:
                    label = (
                        actor.guild_display_name
                        or actor.global_display_name
                        or actor.username
                        or actor.user_id
                    )
                    avatar_url = actor.avatar_url
                    target_kind = "bot" if actor.is_bot else "user"
                else:
                    target_kind = "user"
            key = (cast(Literal["actor", "deployment"], target_type), target_key)
            state_value = state_by_key.get(key)
            stored = social.impression(
                owner_id=user.id,
                source_deployment_id=deployment_id,
                target_type=key[0],
                target_key=target_key,
            )
            impression = (
                PersonImpressionProductView(
                    summary=stored.summary,
                    observations=list(stored.observations),
                    evidence_refs=list(stored.evidence_refs),
                    confidence=stored.confidence,
                    updated_at=stored.updated_at.isoformat(),
                )
                if stored is not None
                else _derived_impression(state_value, events_by_key.get(key, []))
            )
            items.append(
                SocialTargetProductView(
                    target_type=key[0],
                    target_key=target_key,
                    target_kind=target_kind,
                    label=label,
                    avatar_url=avatar_url,
                    state=_relationship_state(state_value),
                    impression=impression,
                    recent_evidence=[
                        RelationshipEvidenceView(
                            dimension=event.dimension,
                            delta=event.delta,
                            confidence=event.confidence,
                            reason_code=event.reason_code,
                            source_message_id=event.source_message_id,
                            source_burst_id=event.source_burst_id,
                            recorded_at=event.recorded_at.isoformat(),
                        )
                        for event in events_by_key.get(key, [])
                    ],
                )
            )
    items.sort(
        key=lambda item: (
            item.state.last_evidence_at if item.state is not None else "",
            item.impression.updated_at if item.impression is not None else "",
        ),
        reverse=True,
    )
    return DeploymentSocialIntelligenceView(
        deployment_id=source_values[0],
        character_card_id=source_values[1],
        character_display_name=source_display_name,
        connection_id=source_values[2],
        guild_id=source_values[3],
        items=items,
    )


@router.get(
    "/server-profiles/{server_profile_id}/conversation-structure",
    response_model=ServerConversationStructureProductView,
)
def server_conversation_structure(
    server_profile_id: str,
    request: Request,
    user: CurrentUserDependency,
    limit: int = Query(default=50, ge=1, le=200),
) -> ServerConversationStructureProductView:
    profile = _server_profile(request, user, server_profile_id)
    repository = ConversationStructureRepository(_database(request))
    threads = repository.recent_threads_for_server(
        owner_id=user.id,
        connection_id=profile.connection_id,
        guild_id=profile.guild_id,
        limit=30,
    )
    segments = repository.recent_segments(
        owner_id=user.id,
        connection_id=profile.connection_id,
        guild_id=profile.guild_id,
        limit=limit,
    )
    return ServerConversationStructureProductView(
        server_profile_id=profile.id,
        connection_id=profile.connection_id,
        guild_id=profile.guild_id,
        threads=[
            ConversationThreadProductView(
                id=item.id,
                label=item.canonical_label,
                summary=item.working_summary or item.anchor_summary,
                keywords=[],
                status=item.status,
                last_active_at=item.last_active_at.isoformat(),
            )
            for item in threads
        ],
        segments=[
            ConversationSegmentProductView(
                id=item.id,
                burst_id=item.burst_id,
                message_ids=list(item.message_ids),
                participant_ids=list(item.participant_ids),
                kind=item.kind,
                summary=item.summary,
                semantic_thread_id=item.thread_id,
                thread_action=item.thread_action,
                thread_evidence=item.thread_evidence,
                confidence=item.confidence,
                source=item.source,
                created_at=item.created_at.isoformat(),
            )
            for item in segments
        ],
    )


@router.get(
    "/server-profiles/{server_profile_id}/participation-intelligence",
    response_model=ServerParticipationIntelligenceView,
)
def server_participation_intelligence(
    server_profile_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> ServerParticipationIntelligenceView:
    profile = _server_profile(request, user, server_profile_id)
    database = _database(request)
    with database.session() as session:
        deployments = list(
            session.scalars(
                select(CharacterDeploymentRecord)
                .where(
                    CharacterDeploymentRecord.owner_id == user.id,
                    CharacterDeploymentRecord.connection_id == profile.connection_id,
                    CharacterDeploymentRecord.workspace_id == profile.guild_id,
                    CharacterDeploymentRecord.platform == "discord",
                )
                .order_by(CharacterDeploymentRecord.created_at)
            )
        )
        deployment_ids = {item.id for item in deployments}
        deployment_state_rows = list(
            session.scalars(
                select(SmartParticipationDeploymentStateRecord)
                .where(
                    SmartParticipationDeploymentStateRecord.connection_id == profile.connection_id,
                    SmartParticipationDeploymentStateRecord.guild_id == profile.guild_id,
                )
                .order_by(SmartParticipationDeploymentStateRecord.last_admitted_at.desc())
            )
        )
        latest_by_deployment: dict[str, SmartParticipationDeploymentStateRecord] = {}
        for state in deployment_state_rows:
            if (
                state.deployment_id in deployment_ids
                and state.deployment_id not in latest_by_deployment
            ):
                latest_by_deployment[state.deployment_id] = state
        scope_rows = list(
            session.scalars(
                select(SmartParticipationScopeStateRecord)
                .where(
                    SmartParticipationScopeStateRecord.connection_id == profile.connection_id,
                    SmartParticipationScopeStateRecord.guild_id == profile.guild_id,
                )
                .order_by(SmartParticipationScopeStateRecord.last_admitted_at.desc())
                .limit(30)
            )
        )
        decision_rows = list(
            session.scalars(
                select(SmartParticipationReplyDecisionRecord)
                .where(
                    SmartParticipationReplyDecisionRecord.owner_id == user.id,
                    SmartParticipationReplyDecisionRecord.connection_id == profile.connection_id,
                    SmartParticipationReplyDecisionRecord.guild_id == profile.guild_id,
                )
                .order_by(SmartParticipationReplyDecisionRecord.created_at.desc())
                .limit(80)
            )
        )
        card_ids = {item.character_card_id for item in deployments}
        cards = (
            {
                card.id: card
                for card in session.scalars(
                    select(CharacterCardRecord).where(CharacterCardRecord.id.in_(card_ids))
                )
            }
            if card_ids
            else {}
        )
        deployment_views = [
            ParticipationDeploymentView(
                deployment_id=deployment.id,
                character_card_id=deployment.character_card_id,
                character_display_name=(
                    cards[deployment.character_card_id].display_name
                    if deployment.character_card_id in cards
                    else deployment.character_card_id
                ),
                status=deployment.status,
                participation_mode=deployment.participation_mode,
                last_admitted_at=(
                    _iso(latest_by_deployment[deployment.id].last_admitted_at)
                    if deployment.id in latest_by_deployment
                    else None
                ),
                last_channel_id=(
                    latest_by_deployment[deployment.id].channel_id
                    if deployment.id in latest_by_deployment
                    else ""
                ),
                last_thread_id=(
                    latest_by_deployment[deployment.id].thread_id
                    if deployment.id in latest_by_deployment
                    else ""
                ),
            )
            for deployment in deployments
        ]
        decision_views = [
            ReplyPlannerDecisionView(
                deployment_id=decision.deployment_id,
                character_card_id=decision.character_card_id,
                character_display_name=(
                    cards[decision.character_card_id].display_name
                    if decision.character_card_id in cards
                    else decision.character_card_id
                ),
                burst_id=decision.burst_id,
                source_message_id=decision.source_message_id,
                channel_id=decision.channel_id,
                thread_id=decision.thread_id,
                segment_id=decision.segment_id,
                semantic_thread_id=decision.semantic_thread_id,
                score=decision.score,
                reason=decision.reason,
                guidance=decision.guidance,
                plan_kind=decision.plan_kind,
                authoritative=decision.authoritative,
                resolver_version=decision.resolver_version,
                created_at=decision.created_at.isoformat(),
            )
            for decision in decision_rows
        ]
    return ServerParticipationIntelligenceView(
        server_profile_id=profile.id,
        deployments=deployment_views,
        scopes=[
            ParticipationScopeView(
                channel_id=item.channel_id,
                thread_id=item.thread_id,
                last_admitted_at=_iso(item.last_admitted_at),
                recent_deployment_id=item.recent_deployment_id,
                window_started_at=_iso(item.window_started_at),
                window_count=item.window_count,
            )
            for item in scope_rows
        ],
        recent_reply_decisions=decision_views,
    )


@router.post(
    "/server-profiles/{server_profile_id}/knowledge-consolidation/entities/{entity_id}",
    response_model=KnowledgeConsolidationCheckpointView,
)
def consolidate_server_entity_knowledge(
    server_profile_id: str,
    entity_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> KnowledgeConsolidationCheckpointView:
    """Owner-triggered, server-scoped Wiki checkpoint for one existing Entity."""

    profile = _server_profile(request, user, server_profile_id)
    service = request.app.state.knowledge_consolidation_v3_service
    try:
        result = service.consolidate_entity(
            owner_id=user.id,
            connection_id=profile.connection_id,
            guild_id=profile.guild_id,
            entity_id=entity_id,
            reason="owner_manual_checkpoint",
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Entity not found.") from exc
    return _consolidation_result(result)


__all__ = ["router"]
