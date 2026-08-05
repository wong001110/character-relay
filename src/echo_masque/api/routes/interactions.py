"""Owner-scoped Interaction Session and Discord Sticker Dictionary endpoints."""

from typing import cast

from fastapi import APIRouter, HTTPException, Query, Request, status

from echo_masque.api.dependencies import CurrentUserDependency
from echo_masque.api.interaction_schemas import (
    InteractionSessionCreate,
    InteractionSessionStatusUpdate,
    InteractionSessionView,
    StickerSemanticCreate,
    StickerSemanticView,
)
from echo_masque.persistence import (
    DeploymentRepository,
    InteractionConflict,
    InteractionRepository,
    Repository,
)
from echo_masque.persistence.interaction_models import (
    DiscordInteractionSessionRecord,
    DiscordStickerSemanticRecord,
)

router = APIRouter(prefix="/api", tags=["interactions"])


def interaction_repository(request: Request) -> InteractionRepository:
    return cast(InteractionRepository, request.app.state.interaction_repository)


def deployment_repository(request: Request) -> DeploymentRepository:
    return cast(DeploymentRepository, request.app.state.deployment_repository)


def character_repository(request: Request) -> Repository:
    return cast(Repository, request.app.state.repository)


def session_view(
    request: Request,
    record: DiscordInteractionSessionRecord,
) -> InteractionSessionView:
    ids = interaction_repository(request).participant_ids(record)
    names: list[str] = []
    deployments = deployment_repository(request)
    characters = character_repository(request)
    for deployment_id in ids:
        deployment = deployments.get_deployment(deployment_id, record.owner_id)
        if deployment is None:
            names.append("Unavailable deployment")
            continue
        card = characters.get_character_card(deployment.character_card_id, record.owner_id)
        names.append(card.display_name if card is not None else "Archived character")
    return InteractionSessionView(
        id=record.id,
        connection_id=record.connection_id,
        guild_id=record.guild_id,
        guild_name=record.guild_name,
        channel_id=record.channel_id,
        channel_name=record.channel_name,
        category_id=record.category_id,
        target_user_id=record.target_user_id,
        target_display_name=record.target_display_name,
        participant_deployment_ids=ids,
        participant_names=names,
        rounds_per_trigger=record.rounds_per_trigger,
        maximum_triggers=record.maximum_triggers,
        completed_triggers=record.completed_triggers,
        maximum_replies_per_trigger=record.rounds_per_trigger * len(ids),
        cooldown_seconds=record.cooldown_seconds,
        duration_seconds=record.duration_seconds,
        intensity=record.intensity,  # type: ignore[arg-type]
        status=record.status,  # type: ignore[arg-type]
        started_at=record.started_at,
        expires_at=record.expires_at,
        last_triggered_at=record.last_triggered_at,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def sticker_view(
    request: Request,
    record: DiscordStickerSemanticRecord,
) -> StickerSemanticView:
    return StickerSemanticView(
        id=record.id,
        connection_id=record.connection_id,
        guild_id=record.guild_id,
        sticker_id=record.sticker_id,
        name=record.name,
        description=record.description,
        tags=interaction_repository(request).sticker_tags(record),
        format_type=record.format_type,
        asset_url=record.asset_url,
        semantic_intent=record.semantic_intent,
        semantic_emotion=record.semantic_emotion,
        semantic_description=record.semantic_description,
        semantic_source=record.semantic_source,  # type: ignore[arg-type]
        semantic_confidence=record.semantic_confidence,
        last_seen_at=record.last_seen_at,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.get("/interaction-sessions", response_model=list[InteractionSessionView])
def list_interaction_sessions(
    request: Request,
    user: CurrentUserDependency,
) -> list[InteractionSessionView]:
    return [
        session_view(request, item)
        for item in interaction_repository(request).list_sessions(user.id)
    ]


@router.post(
    "/interaction-sessions",
    response_model=InteractionSessionView,
    status_code=status.HTTP_201_CREATED,
)
def create_interaction_session(
    payload: InteractionSessionCreate,
    request: Request,
    user: CurrentUserDependency,
) -> InteractionSessionView:
    try:
        record = interaction_repository(request).create_session(
            owner_id=user.id,
            **payload.model_dump(),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Discord connection not found.") from exc
    except InteractionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return session_view(request, record)


@router.patch(
    "/interaction-sessions/{session_id}/status",
    response_model=InteractionSessionView,
)
def update_interaction_session_status(
    session_id: str,
    payload: InteractionSessionStatusUpdate,
    request: Request,
    user: CurrentUserDependency,
) -> InteractionSessionView:
    record = interaction_repository(request).set_session_status(
        session_id,
        user.id,
        payload.status,
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Interaction Session not found.")
    return session_view(request, record)


@router.delete(
    "/interaction-sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_interaction_session(
    session_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> None:
    if not interaction_repository(request).delete_session(session_id, user.id):
        raise HTTPException(status_code=404, detail="Interaction Session not found.")


@router.get(
    "/discord/sticker-dictionary",
    response_model=list[StickerSemanticView],
)
def list_sticker_dictionary(
    request: Request,
    user: CurrentUserDependency,
    connection_id: str | None = Query(default=None, max_length=64),
    guild_id: str | None = Query(default=None, max_length=200),
) -> list[StickerSemanticView]:
    return [
        sticker_view(request, item)
        for item in interaction_repository(request).list_stickers(
            user.id,
            connection_id=connection_id,
            guild_id=guild_id,
        )
    ]


@router.put(
    "/discord/sticker-dictionary",
    response_model=StickerSemanticView,
)
def save_sticker_dictionary_entry(
    payload: StickerSemanticCreate,
    request: Request,
    user: CurrentUserDependency,
) -> StickerSemanticView:
    try:
        record = interaction_repository(request).upsert_manual_sticker(
            owner_id=user.id,
            **payload.model_dump(),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Discord connection not found.") from exc
    return sticker_view(request, record)


@router.delete(
    "/discord/sticker-dictionary/{record_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_sticker_dictionary_entry(
    record_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> None:
    if not interaction_repository(request).delete_sticker(record_id, user.id):
        raise HTTPException(status_code=404, detail="Sticker Dictionary entry not found.")
