"""Owner-authored notes and relationships; room-member writes use the trusted connector."""

from typing import cast

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from echo_masque.api.dependencies import CurrentUserDependency
from echo_masque.notes import NoteAccessDenied, NoteConflict, NoteInput, NoteView
from echo_masque.persistence.note_repository import CharacterNoteRepository
from echo_masque.room_routing import RoomScope

router = APIRouter(prefix="/api/characters", tags=["character notes"])


class NoteLocation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    connection_id: str = Field(min_length=1, max_length=200)
    guild_id: str = Field(min_length=1, max_length=200)
    channel_id: str = Field(min_length=1, max_length=200)
    thread_id: str = Field(default="", max_length=200)

    def scope(self, owner_id: str) -> RoomScope:
        return RoomScope(owner_id=owner_id, **self.model_dump())


class AuthoredNoteCreate(NoteInput):
    # null is a deliberate author-defined background, not a member's global memory.
    location: NoteLocation | None = None


class AuthoredNoteUpdate(NoteInput):
    expected_version: int = Field(ge=1)


def _repo(request: Request) -> CharacterNoteRepository:
    return cast(CharacterNoteRepository, request.app.state.character_note_repository)


def _failure(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=409 if isinstance(exc, NoteConflict) else 404, detail=str(exc))


@router.get("/{card_id}/notes", response_model=list[NoteView])
def list_notes(
    card_id: str,
    request: Request,
    user: CurrentUserDependency,
    connection_id: str = "",
    guild_id: str = "",
    channel_id: str = "",
    thread_id: str = "",
) -> list[NoteView]:
    if any((connection_id, guild_id, channel_id, thread_id)) and not all(
        (
            connection_id,
            guild_id,
            channel_id,
        )
    ):
        raise HTTPException(status_code=422, detail="complete_note_scope_required")
    scope = (
        RoomScope(
            owner_id=user.id,
            connection_id=connection_id,
            guild_id=guild_id,
            channel_id=channel_id,
            thread_id=thread_id,
        )
        if connection_id
        else None
    )
    try:
        return list(_repo(request).list(owner_id=user.id, card_id=card_id, scope=scope, limit=256))
    except (NoteAccessDenied, NoteConflict) as exc:
        raise _failure(exc) from exc


@router.post("/{card_id}/notes", response_model=NoteView, status_code=201)
def create_note(
    card_id: str,
    payload: AuthoredNoteCreate,
    request: Request,
    user: CurrentUserDependency,
) -> NoteView:
    try:
        return _repo(request).create(
            owner_id=user.id,
            card_id=card_id,
            payload=NoteInput.model_validate(payload.model_dump(exclude={"location"})),
            scope=payload.location.scope(user.id) if payload.location else None,
            authored=True,
        )
    except (NoteAccessDenied, NoteConflict) as exc:
        raise _failure(exc) from exc


@router.patch("/{card_id}/notes/{note_id}", response_model=NoteView)
def update_note(
    card_id: str,
    note_id: str,
    payload: AuthoredNoteUpdate,
    request: Request,
    user: CurrentUserDependency,
) -> NoteView:
    try:
        result = _repo(request).change(
            owner_id=user.id,
            card_id=card_id,
            note_id=note_id,
            expected_version=payload.expected_version,
            operator=True,
            payload=NoteInput.model_validate(payload.model_dump(exclude={"expected_version"})),
        )
        assert result is not None
        return result
    except (NoteAccessDenied, NoteConflict) as exc:
        raise _failure(exc) from exc


@router.delete("/{card_id}/notes/{note_id}", status_code=204)
def forget_note(
    card_id: str,
    note_id: str,
    request: Request,
    user: CurrentUserDependency,
    expected_version: int = Query(ge=1),
) -> None:
    try:
        _repo(request).change(
            owner_id=user.id,
            card_id=card_id,
            note_id=note_id,
            expected_version=expected_version,
            payload=None,
            operator=True,
        )
    except (NoteAccessDenied, NoteConflict) as exc:
        raise _failure(exc) from exc
