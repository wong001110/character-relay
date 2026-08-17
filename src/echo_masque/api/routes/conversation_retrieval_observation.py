"""Read-only layered Character recall preview for Portal diagnostics."""

from __future__ import annotations

import json
from typing import cast

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from echo_masque.api.dependencies import CurrentUserDependency
from echo_masque.internal_context import InternalContextService
from echo_masque.memory_layers import SynthesizedMemoryFreshnessRepository
from echo_masque.persistence.database import Database
from echo_masque.persistence.episodic_sql_rag_repository import EpisodicSqlRagRepository
from echo_masque.persistence.repository import Repository
from echo_masque.tool_runtime import ToolExecutionContext

router = APIRouter()


class RetrievalPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=800)
    connection_id: str = Field(min_length=1, max_length=64)
    guild_id: str = Field(min_length=1, max_length=200)
    channel_id: str = Field(default="", max_length=200)
    thread_id: str = Field(default="", max_length=200)
    subject_user_id: str = Field(default="", max_length=200)
    topic_id: str = Field(default="", max_length=64)
    limit: int = Field(default=6, ge=1, le=8)


class RetrievalMemoryItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    ref: str
    origin: str
    scope_type: str
    memory_type: str
    content: str
    score: float
    priority: float | None = None
    confidence: float | None = None
    importance: float | None = None
    freshness: str = ""


class RetrievalEntityItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    entity_type: str
    canonical_key: str
    label: str
    source_type: str


class RetrievalEpisodeItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    ref: str
    topic_ref: str
    channel_ref: str
    thread_ref: str
    summary: str
    score: float
    expanded_via_entity: bool
    source_message_refs: tuple[str, ...] = ()
    entities: tuple[RetrievalEntityItem, ...] = ()


class RetrievalPreviewView(BaseModel):
    model_config = ConfigDict(frozen=True)

    query: str
    memory_count: int
    episode_count: int
    seed_count: int
    expanded_count: int
    memories: tuple[RetrievalMemoryItem, ...] = ()
    episodes: tuple[RetrievalEpisodeItem, ...] = ()


def _database(request: Request) -> Database:
    return cast(Database, request.app.state.database)


def _repository(request: Request) -> Repository:
    return cast(Repository, request.app.state.repository)


def _internal_context(request: Request) -> InternalContextService:
    return cast(InternalContextService, request.app.state.internal_context_service)


@router.post(
    "/characters/{character_card_id}/retrieval-preview",
    response_model=RetrievalPreviewView,
)
def retrieval_preview(
    character_card_id: str,
    payload: RetrievalPreviewRequest,
    request: Request,
    user: CurrentUserDependency,
) -> RetrievalPreviewView:
    if _repository(request).get_character_card(character_card_id, user.id) is None:
        raise HTTPException(status_code=404, detail="Character Card not found.")
    context = ToolExecutionContext(
        owner_id=user.id,
        deployment_id="",
        character_card_id=character_card_id,
        platform="discord",
        connection_id=payload.connection_id,
        guild_id=payload.guild_id,
        channel_id=payload.channel_id,
        thread_id=payload.thread_id,
        initiator_user_id=payload.subject_user_id,
        topic_id=payload.topic_id,
    )
    service = _internal_context(request)
    memory_result = json.loads(
        service.memory_search(
            {"query": payload.query, "limit": payload.limit},
            context,
        )
    )
    episode_result = json.loads(
        service.conversation_search(
            {"query": payload.query, "limit": payload.limit},
            context,
        )
    )
    freshness = SynthesizedMemoryFreshnessRepository(_database(request))
    memories: list[RetrievalMemoryItem] = []
    for raw in memory_result.get("memories", []):
        if not isinstance(raw, dict):
            continue
        ref = str(raw.get("ref", ""))
        origin = str(raw.get("origin", ""))
        freshness_status = "durable" if origin == "core" else ""
        if origin == "synthesized" and ref:
            freshness_record = freshness.get(ref)
            freshness_status = (
                freshness_record.freshness_status if freshness_record is not None else "untracked"
            )
        memories.append(
            RetrievalMemoryItem(
                ref=ref,
                origin=origin,
                scope_type=str(raw.get("scope_type", "")),
                memory_type=str(raw.get("memory_type", "")),
                content=str(raw.get("content", "")),
                score=float(raw.get("score", 0.0) or 0.0),
                priority=(
                    float(raw["priority"])
                    if isinstance(raw.get("priority"), (int, float))
                    else None
                ),
                confidence=(
                    float(raw["confidence"])
                    if isinstance(raw.get("confidence"), (int, float))
                    else None
                ),
                importance=(
                    float(raw["importance"])
                    if isinstance(raw.get("importance"), (int, float))
                    else None
                ),
                freshness=freshness_status,
            )
        )
    episodic = EpisodicSqlRagRepository(_database(request))
    episodes: list[RetrievalEpisodeItem] = []
    for raw in episode_result.get("episodes", []):
        if not isinstance(raw, dict):
            continue
        ref = str(raw.get("ref", ""))
        entities = episodic.entities_for_episode(owner_id=user.id, episode_id=ref) if ref else ()
        source_refs = raw.get("source_message_refs", [])
        episodes.append(
            RetrievalEpisodeItem(
                ref=ref,
                topic_ref=str(raw.get("topic_ref", "")),
                channel_ref=str(raw.get("channel_ref", "")),
                thread_ref=str(raw.get("thread_ref", "")),
                summary=str(raw.get("summary", "")),
                score=float(raw.get("score", 0.0) or 0.0),
                expanded_via_entity=bool(raw.get("expanded_via_entity", False)),
                source_message_refs=tuple(
                    str(item) for item in source_refs if isinstance(item, str) and item
                ) if isinstance(source_refs, list) else (),
                entities=tuple(
                    RetrievalEntityItem(
                        entity_type=item.entity_type,
                        canonical_key=item.canonical_key,
                        label=item.label,
                        source_type=item.source_type,
                    )
                    for item in entities
                ),
            )
        )
    return RetrievalPreviewView(
        query=payload.query,
        memory_count=len(memories),
        episode_count=len(episodes),
        seed_count=int(episode_result.get("seed_count", 0) or 0),
        expanded_count=int(episode_result.get("expanded_count", 0) or 0),
        memories=tuple(memories),
        episodes=tuple(episodes),
    )


__all__ = ["router"]
