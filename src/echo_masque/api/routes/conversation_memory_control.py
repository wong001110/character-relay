"""Explicit Core Memory controls layered beside synthesized Memory vNext."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, cast

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from echo_masque.api.dependencies import CurrentUserDependency
from echo_masque.persistence import AuthRepository
from echo_masque.persistence.core_memory_models import CharacterCoreMemoryRecord
from echo_masque.persistence.core_memory_repository import CoreMemoryRepository
from echo_masque.persistence.database import Database
from echo_masque.persistence.memory_vnext_repository import MemoryVNextRepository
from echo_masque.persistence.repository import Repository

router = APIRouter()

CoreMemoryScope = Literal["character_global", "character_server", "character_user"]


class CoreMemoryView(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    character_card_id: str
    connection_id: str
    guild_id: str
    scope_type: str
    subject_user_id: str
    memory_type: str
    content: str
    priority: float
    status: str
    source_memory_id: str
    source_message_id: str
    use_count: int
    last_used_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class CoreMemoryListView(BaseModel):
    model_config = ConfigDict(frozen=True)

    character_card_id: str
    items: tuple[CoreMemoryView, ...] = ()


class CoreMemoryCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=2000)
    scope_type: CoreMemoryScope = "character_global"
    connection_id: str = Field(default="", max_length=64)
    guild_id: str = Field(default="", max_length=200)
    subject_user_id: str = Field(default="", max_length=200)
    memory_type: str = Field(default="other", max_length=40)
    priority: float = Field(default=0.75, ge=0.0, le=1.0)
    source_message_id: str = Field(default="", max_length=200)


class CoreMemoryUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str | None = Field(default=None, min_length=1, max_length=2000)
    memory_type: str | None = Field(default=None, max_length=40)
    priority: float | None = Field(default=None, ge=0.0, le=1.0)
    status: Literal["active", "archived"] | None = None


class PromoteMemoryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    priority: float = Field(default=0.85, ge=0.0, le=1.0)


def _database(request: Request) -> Database:
    return cast(Database, request.app.state.database)


def _repository(request: Request) -> Repository:
    return cast(Repository, request.app.state.repository)


def _auth(request: Request) -> AuthRepository:
    return cast(AuthRepository, request.app.state.auth_repository)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _view(record: CharacterCoreMemoryRecord) -> CoreMemoryView:
    return CoreMemoryView(
        id=record.id,
        character_card_id=record.character_card_id,
        connection_id=record.connection_id,
        guild_id=record.guild_id,
        scope_type=record.scope_type,
        subject_user_id=record.subject_user_id,
        memory_type=record.memory_type,
        content=record.content,
        priority=record.priority,
        status=record.status,
        source_memory_id=record.source_memory_id,
        source_message_id=record.source_message_id,
        use_count=record.use_count,
        last_used_at=_aware(record.last_used_at),
        created_at=_aware(record.created_at) or record.created_at,
        updated_at=_aware(record.updated_at) or record.updated_at,
    )


def _require_card(request: Request, *, owner_id: str, character_card_id: str) -> None:
    if _repository(request).get_character_card(character_card_id, owner_id) is None:
        raise HTTPException(status_code=404, detail="Character Card not found.")


@router.get(
    "/characters/{character_card_id}/core-memories",
    response_model=CoreMemoryListView,
)
def list_core_memories(
    character_card_id: str,
    request: Request,
    user: CurrentUserDependency,
    connection_id: str = Query(default="", max_length=64),
    guild_id: str = Query(default="", max_length=200),
    subject_user_id: str = Query(default="", max_length=200),
    status: str = Query(default="active", max_length=24),
) -> CoreMemoryListView:
    _require_card(request, owner_id=user.id, character_card_id=character_card_id)
    records = CoreMemoryRepository(_database(request)).list_for_character(
        owner_id=user.id,
        character_card_id=character_card_id,
        connection_id=connection_id,
        guild_id=guild_id,
        subject_user_id=subject_user_id,
        status=status,
        limit=200,
    )
    return CoreMemoryListView(
        character_card_id=character_card_id,
        items=tuple(_view(item) for item in records),
    )


@router.post(
    "/characters/{character_card_id}/core-memories",
    response_model=CoreMemoryView,
)
def create_core_memory(
    character_card_id: str,
    payload: CoreMemoryCreateRequest,
    request: Request,
    user: CurrentUserDependency,
) -> CoreMemoryView:
    _require_card(request, owner_id=user.id, character_card_id=character_card_id)
    try:
        record = CoreMemoryRepository(_database(request)).upsert(
            owner_id=user.id,
            character_card_id=character_card_id,
            content=payload.content,
            scope_type=payload.scope_type,
            connection_id=payload.connection_id,
            guild_id=payload.guild_id,
            subject_user_id=payload.subject_user_id,
            memory_type=payload.memory_type,
            priority=payload.priority,
            source_message_id=payload.source_message_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _auth(request).audit(
        actor_user_id=user.id,
        action="conversation_intelligence.core_memory_saved",
        resource_type="character_core_memory",
        resource_id=record.id,
    )
    return _view(record)


@router.patch("/core-memories/{memory_id}", response_model=CoreMemoryView)
def update_core_memory(
    memory_id: str,
    payload: CoreMemoryUpdateRequest,
    request: Request,
    user: CurrentUserDependency,
) -> CoreMemoryView:
    try:
        record = CoreMemoryRepository(_database(request)).update(
            owner_id=user.id,
            memory_id=memory_id,
            content=payload.content,
            memory_type=payload.memory_type,
            priority=payload.priority,
            status=payload.status,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Core Memory not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _auth(request).audit(
        actor_user_id=user.id,
        action="conversation_intelligence.core_memory_updated",
        resource_type="character_core_memory",
        resource_id=record.id,
    )
    return _view(record)


@router.delete("/core-memories/{memory_id}")
def delete_core_memory(
    memory_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> dict[str, bool]:
    deleted = CoreMemoryRepository(_database(request)).delete(
        owner_id=user.id,
        memory_id=memory_id,
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Core Memory not found.")
    _auth(request).audit(
        actor_user_id=user.id,
        action="conversation_intelligence.core_memory_deleted",
        resource_type="character_core_memory",
        resource_id=memory_id,
    )
    return {"deleted": True}


@router.post("/memories/{memory_id}/promote", response_model=CoreMemoryView)
def promote_synthesized_memory(
    memory_id: str,
    payload: PromoteMemoryRequest,
    request: Request,
    user: CurrentUserDependency,
) -> CoreMemoryView:
    synthesized = MemoryVNextRepository(_database(request)).get(memory_id)
    if synthesized is None or synthesized.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Synthesized Memory not found.")
    _require_card(
        request,
        owner_id=user.id,
        character_card_id=synthesized.character_card_id,
    )
    scope_type: CoreMemoryScope
    if synthesized.scope_type == "character_user" and synthesized.subject_user_id:
        scope_type = "character_user"
    elif synthesized.connection_id and synthesized.guild_id:
        scope_type = "character_server"
    else:
        scope_type = "character_global"
    record = CoreMemoryRepository(_database(request)).upsert(
        owner_id=user.id,
        character_card_id=synthesized.character_card_id,
        content=synthesized.content,
        scope_type=scope_type,
        connection_id=(
            synthesized.connection_id if scope_type != "character_global" else ""
        ),
        guild_id=synthesized.guild_id if scope_type != "character_global" else "",
        subject_user_id=(
            synthesized.subject_user_id if scope_type == "character_user" else ""
        ),
        memory_type=synthesized.memory_type,
        priority=payload.priority,
        source_memory_id=synthesized.id,
    )
    _auth(request).audit(
        actor_user_id=user.id,
        action="conversation_intelligence.memory_promoted_to_core",
        resource_type="character_core_memory",
        resource_id=record.id,
    )
    return _view(record)


__all__ = ["router"]
