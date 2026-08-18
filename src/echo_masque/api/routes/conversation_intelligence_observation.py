"""Read-only observability views for Conversation Intelligence control-plane UI."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, cast

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict

from echo_masque.api.dependencies import CurrentUserDependency
from echo_masque.conversation_intelligence_observation import (
    ConversationIntelligenceObservationService,
)
from echo_masque.persistence.conversation_topic_repository import ConversationTopicRepository
from echo_masque.persistence.database import Database
from echo_masque.persistence.deployment_repository import DeploymentRepository
from echo_masque.persistence.discord_identity_repository import DiscordIdentityRepository
from echo_masque.persistence.repository import Repository

router = APIRouter(tags=["conversation-intelligence"])


class TopicOverviewView(BaseModel):
    model_config = ConfigDict(frozen=True)

    total: int
    active: int
    cooling: int
    closed: int
    archived: int
    stale_active: int
    channel_count: int


class TopicDecisionView(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    message_id: str
    from_topic_id: str
    from_topic_label: str
    to_topic_id: str
    to_topic_label: str
    decision: str
    reason: str
    dense_score: float
    sparse_score: float
    continuation_score: float
    switch_score: float
    candidate_dense_score: float
    candidate_sparse_score: float
    idle_seconds: int
    created_at: datetime


class TopicDecisionTimelineView(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: tuple[TopicDecisionView, ...] = ()


class CharacterMindEventView(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    state_type: str
    subject_type: str
    subject_key: str
    subject_label: str
    delta: float
    evidence_confidence: float
    value_before: float
    value_after: float
    confidence_before: float
    confidence_after: float
    contradiction: bool
    source_type: str
    source_message_id: str
    source_burst_id: str
    reason_code: str
    channel_id: str
    topic_id: str
    recorded_at: datetime


class CharacterMindHistoryView(BaseModel):
    model_config = ConfigDict(frozen=True)

    character_card_id: str
    character_display_name: str
    connection_id: str
    guild_id: str
    items: tuple[CharacterMindEventView, ...] = ()


class SocialNeighborView(BaseModel):
    model_config = ConfigDict(frozen=True)

    subject_key: str
    subject_type: Literal["actor", "character"]
    label: str
    avatar_url: str
    discord_user_id: str
    is_bot: bool
    character_card_id: str
    value: float
    confidence: float
    evidence_count: int
    last_evidence_at: datetime
    trend: str


class SocialEgoGraphView(BaseModel):
    model_config = ConfigDict(frozen=True)

    character_card_id: str
    character_display_name: str
    character_avatar_url: str
    connection_id: str
    guild_id: str
    items: tuple[SocialNeighborView, ...] = ()


class InterestView(BaseModel):
    model_config = ConfigDict(frozen=True)

    subject_key: str
    subject_type: str
    subject_label: str
    value: float
    confidence: float
    evidence_count: int
    last_evidence_at: datetime
    trend: str


class CurrentInterestView(BaseModel):
    model_config = ConfigDict(frozen=True)

    character_card_id: str
    character_display_name: str
    connection_id: str
    guild_id: str
    items: tuple[InterestView, ...] = ()


def _database(request: Request) -> Database:
    return cast(Database, request.app.state.database)


def _repository(request: Request) -> Repository:
    return cast(Repository, request.app.state.repository)


def _observation(request: Request) -> ConversationIntelligenceObservationService:
    return ConversationIntelligenceObservationService(_database(request))


def _subject_label(
    topics: ConversationTopicRepository,
    *,
    owner_id: str,
    subject_type: str,
    subject_key: str,
) -> str:
    if subject_type != "topic" or not subject_key.startswith("topic:"):
        return subject_key.removeprefix("actor:") or subject_key
    topic = topics.get(subject_key.removeprefix("topic:"), owner_id)
    return topic.topic_label if topic is not None and topic.topic_label.strip() else subject_key


def _character_social_presentation(
    request: Request,
    *,
    owner_id: str,
    character_card_id: str,
    connection_id: str,
    guild_id: str,
    card_display_name: str,
) -> tuple[str, str]:
    database = _database(request)
    candidates = [
        item
        for item in DeploymentRepository(database).list_connector_deployments(
            platform="discord",
            connection_id=connection_id,
        )
        if item.owner_id == owner_id
        and item.character_card_id == character_card_id
        and item.workspace_id == guild_id
    ]
    candidates.sort(
        key=lambda item: (
            0 if item.channel_id.startswith("@server:") else 1,
            item.channel_name,
            item.id,
        )
    )
    identities = DiscordIdentityRepository(database)
    display_name = card_display_name
    avatar_url = ""
    for deployment in candidates:
        identity = identities.get_identity(deployment.id, owner_id)
        if identity is None:
            continue
        if identity.display_name.strip():
            display_name = identity.display_name.strip()
        if identity.avatar_url.strip():
            avatar_url = identity.avatar_url.strip()
        break
    if not avatar_url:
        avatar_url = f"/api/characters/portraits/{character_card_id}"
    return display_name, avatar_url


@router.get("/overview", response_model=TopicOverviewView)
def inspect_overview(
    request: Request,
    user: CurrentUserDependency,
    connection_id: str = Query(min_length=1, max_length=64),
    guild_id: str = Query(min_length=1, max_length=200),
) -> TopicOverviewView:
    value = _observation(request).topic_overview(
        owner_id=user.id,
        connection_id=connection_id,
        guild_id=guild_id,
    )
    return TopicOverviewView(
        total=value.total,
        active=value.active,
        cooling=value.cooling,
        closed=value.closed,
        archived=value.archived,
        stale_active=value.stale_active,
        channel_count=value.channel_count,
    )


@router.get("/topic-decisions", response_model=TopicDecisionTimelineView)
def inspect_topic_decisions(
    request: Request,
    user: CurrentUserDependency,
    connection_id: str = Query(min_length=1, max_length=64),
    guild_id: str = Query(min_length=1, max_length=200),
    channel_id: str = Query(min_length=1, max_length=200),
    thread_id: str = Query(default="", max_length=200),
    limit: int = Query(default=100, ge=1, le=300),
) -> TopicDecisionTimelineView:
    topics = ConversationTopicRepository(_database(request))
    records = _observation(request).topic_decisions(
        owner_id=user.id,
        connection_id=connection_id,
        guild_id=guild_id,
        channel_id=channel_id,
        thread_id=thread_id,
        limit=limit,
    )

    def label(topic_id: str) -> str:
        if not topic_id:
            return ""
        item = topics.get(topic_id, user.id)
        return item.topic_label if item is not None else topic_id

    return TopicDecisionTimelineView(
        items=tuple(
            TopicDecisionView(
                id=item.id,
                message_id=item.message_id,
                from_topic_id=item.from_topic_id,
                from_topic_label=label(item.from_topic_id),
                to_topic_id=item.to_topic_id,
                to_topic_label=label(item.to_topic_id),
                decision=item.decision,
                reason=item.reason,
                dense_score=item.dense_score,
                sparse_score=item.sparse_score,
                continuation_score=item.continuation_score,
                switch_score=item.switch_score,
                candidate_dense_score=item.candidate_dense_score,
                candidate_sparse_score=item.candidate_sparse_score,
                idle_seconds=item.idle_seconds,
                created_at=item.created_at,
            )
            for item in records
        )
    )


@router.get(
    "/characters/{character_card_id}/history",
    response_model=CharacterMindHistoryView,
)
def inspect_character_history(
    character_card_id: str,
    request: Request,
    user: CurrentUserDependency,
    connection_id: str = Query(min_length=1, max_length=64),
    guild_id: str = Query(min_length=1, max_length=200),
    state_type: str = Query(default="", max_length=40),
    limit: int = Query(default=200, ge=1, le=500),
) -> CharacterMindHistoryView:
    card = _repository(request).get_character_card(character_card_id, user.id)
    if card is None:
        raise HTTPException(status_code=404, detail="Character Card not found.")
    records = _observation(request).character_history(
        owner_id=user.id,
        character_card_id=character_card_id,
        connection_id=connection_id,
        guild_id=guild_id,
        state_types=(state_type,) if state_type else (),
        limit=limit,
    )
    topics = ConversationTopicRepository(_database(request))
    return CharacterMindHistoryView(
        character_card_id=character_card_id,
        character_display_name=card.display_name,
        connection_id=connection_id,
        guild_id=guild_id,
        items=tuple(
            CharacterMindEventView(
                id=item.id,
                state_type=item.state_type,
                subject_type=item.subject_type,
                subject_key=item.subject_key,
                subject_label=_subject_label(
                    topics,
                    owner_id=user.id,
                    subject_type=item.subject_type,
                    subject_key=item.subject_key,
                ),
                delta=item.delta,
                evidence_confidence=item.evidence_confidence,
                value_before=item.value_before,
                value_after=item.value_after,
                confidence_before=item.confidence_before,
                confidence_after=item.confidence_after,
                contradiction=item.contradiction,
                source_type=item.source_type,
                source_message_id=item.source_message_id,
                source_burst_id=item.source_burst_id,
                reason_code=item.reason_code,
                channel_id=item.channel_id,
                topic_id=item.topic_id,
                recorded_at=item.recorded_at,
            )
            for item in records
        ),
    )


@router.get(
    "/characters/{character_card_id}/social-graph",
    response_model=SocialEgoGraphView,
)
def inspect_social_graph(
    character_card_id: str,
    request: Request,
    user: CurrentUserDependency,
    connection_id: str = Query(min_length=1, max_length=64),
    guild_id: str = Query(min_length=1, max_length=200),
) -> SocialEgoGraphView:
    card = _repository(request).get_character_card(character_card_id, user.id)
    if card is None:
        raise HTTPException(status_code=404, detail="Character Card not found.")
    display_name, avatar_url = _character_social_presentation(
        request,
        owner_id=user.id,
        character_card_id=character_card_id,
        connection_id=connection_id,
        guild_id=guild_id,
        card_display_name=card.display_name,
    )
    items = _observation(request).social_ego_graph(
        owner_id=user.id,
        character_card_id=character_card_id,
        connection_id=connection_id,
        guild_id=guild_id,
    )
    return SocialEgoGraphView(
        character_card_id=character_card_id,
        character_display_name=display_name,
        character_avatar_url=avatar_url,
        connection_id=connection_id,
        guild_id=guild_id,
        items=tuple(
            SocialNeighborView(
                subject_key=item.subject_key,
                subject_type=cast(Literal["actor", "character"], item.subject_type),
                label=item.label,
                avatar_url=item.avatar_url,
                discord_user_id=item.discord_user_id,
                is_bot=item.is_bot,
                character_card_id=item.character_card_id,
                value=item.value,
                confidence=item.confidence,
                evidence_count=item.evidence_count,
                last_evidence_at=item.last_evidence_at,
                trend=item.trend,
            )
            for item in items
        ),
    )


@router.get(
    "/characters/{character_card_id}/interests",
    response_model=CurrentInterestView,
)
def inspect_current_interests(
    character_card_id: str,
    request: Request,
    user: CurrentUserDependency,
    connection_id: str = Query(min_length=1, max_length=64),
    guild_id: str = Query(min_length=1, max_length=200),
) -> CurrentInterestView:
    card = _repository(request).get_character_card(character_card_id, user.id)
    if card is None:
        raise HTTPException(status_code=404, detail="Character Card not found.")
    topics = ConversationTopicRepository(_database(request))
    items = _observation(request).current_interests(
        owner_id=user.id,
        character_card_id=character_card_id,
        connection_id=connection_id,
        guild_id=guild_id,
    )
    return CurrentInterestView(
        character_card_id=character_card_id,
        character_display_name=card.display_name,
        connection_id=connection_id,
        guild_id=guild_id,
        items=tuple(
            InterestView(
                subject_key=item.subject_key,
                subject_type=item.subject_type,
                subject_label=_subject_label(
                    topics,
                    owner_id=user.id,
                    subject_type=item.subject_type,
                    subject_key=item.subject_key,
                ),
                value=item.value,
                confidence=item.confidence,
                evidence_count=item.evidence_count,
                last_evidence_at=item.last_evidence_at,
                trend=item.trend,
            )
            for item in items
        ),
    )


__all__ = ["router"]
