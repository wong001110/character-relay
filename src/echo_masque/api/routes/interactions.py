"""Owner-scoped Interaction Session and Discord Sticker Dictionary endpoints."""

from typing import cast

from fastapi import APIRouter, HTTPException, Query, Request, status

from echo_masque.api.dependencies import CurrentUserDependency
from echo_masque.api.expression_schemas import (
    ExpressionNodeView,
    ExpressionRunDetail,
    ExpressionRunView,
    ExpressionSemanticCreate,
    ExpressionSemanticView,
)
from echo_masque.api.interaction_schemas import (
    InteractionSessionCreate,
    InteractionSessionStatusUpdate,
    InteractionSessionView,
    InteractionTemplateApply,
    InteractionTemplateCreate,
    InteractionTemplateUpdate,
    InteractionTemplateView,
    StickerSemanticCreate,
    StickerSemanticView,
)
from echo_masque.persistence import (
    DeploymentRepository,
    ExpressionRepository,
    InteractionConflict,
    InteractionRepository,
    Repository,
)
from echo_masque.persistence.expression_models import (
    DiscordExpressionNodeRecord,
    DiscordExpressionRunRecord,
    DiscordExpressionSemanticRecord,
)
from echo_masque.persistence.expression_repository import expression_key
from echo_masque.persistence.interaction_models import (
    DiscordInteractionSessionRecord,
    DiscordInteractionTemplateRecord,
    DiscordStickerSemanticRecord,
)

router = APIRouter(prefix="/api", tags=["interactions"])


def interaction_repository(request: Request) -> InteractionRepository:
    return cast(InteractionRepository, request.app.state.interaction_repository)


def deployment_repository(request: Request) -> DeploymentRepository:
    return cast(DeploymentRepository, request.app.state.deployment_repository)


def expression_repository(request: Request) -> ExpressionRepository:
    return cast(ExpressionRepository, request.app.state.expression_repository)


def character_repository(request: Request) -> Repository:
    return cast(Repository, request.app.state.repository)


def template_view(
    request: Request,
    record: DiscordInteractionTemplateRecord,
) -> InteractionTemplateView:
    ids = interaction_repository(request).template_character_ids(record)
    characters = character_repository(request)
    names: list[str] = []
    for character_id in ids:
        card = characters.get_character_card(character_id, record.owner_id)
        names.append(card.display_name if card is not None else "Archived character")
    return InteractionTemplateView(
        id=record.id,
        server_profile_id=record.server_profile_id,
        name=record.name,
        participant_character_card_ids=ids,
        participant_names=names,
        rounds_per_trigger=record.rounds_per_trigger,
        maximum_triggers=record.maximum_triggers,
        maximum_replies_per_trigger=record.rounds_per_trigger * len(ids),
        cooldown_seconds=record.cooldown_seconds,
        duration_seconds=record.duration_seconds,
        intensity=record.intensity,  # type: ignore[arg-type]
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


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


@router.get("/interaction-templates", response_model=list[InteractionTemplateView])
def list_interaction_templates(
    request: Request,
    user: CurrentUserDependency,
    server_profile_id: str = Query(min_length=1, max_length=64),
) -> list[InteractionTemplateView]:
    return [
        template_view(request, item)
        for item in interaction_repository(request).list_templates(
            user.id,
            server_profile_id=server_profile_id,
        )
    ]


@router.post(
    "/interaction-templates",
    response_model=InteractionTemplateView,
    status_code=status.HTTP_201_CREATED,
)
def create_interaction_template(
    payload: InteractionTemplateCreate,
    request: Request,
    user: CurrentUserDependency,
) -> InteractionTemplateView:
    try:
        record = interaction_repository(request).create_template(
            owner_id=user.id,
            **payload.model_dump(),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Discord Server not found.") from exc
    except InteractionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return template_view(request, record)


@router.put(
    "/interaction-templates/{template_id}",
    response_model=InteractionTemplateView,
)
def update_interaction_template(
    template_id: str,
    payload: InteractionTemplateUpdate,
    request: Request,
    user: CurrentUserDependency,
) -> InteractionTemplateView:
    try:
        record = interaction_repository(request).update_template(
            template_id,
            user.id,
            **payload.model_dump(exclude_unset=True),
        )
    except InteractionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="Interaction Template not found.")
    return template_view(request, record)


@router.post(
    "/interaction-templates/{template_id}/apply",
    response_model=InteractionSessionView,
    status_code=status.HTTP_201_CREATED,
)
def apply_interaction_template(
    template_id: str,
    payload: InteractionTemplateApply,
    request: Request,
    user: CurrentUserDependency,
) -> InteractionSessionView:
    try:
        record = interaction_repository(request).apply_template(
            template_id=template_id,
            owner_id=user.id,
            **payload.model_dump(),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Interaction Template not found.") from exc
    except InteractionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return session_view(request, record)


@router.delete(
    "/interaction-templates/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_interaction_template(
    template_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> None:
    if not interaction_repository(request).delete_template(template_id, user.id):
        raise HTTPException(status_code=404, detail="Interaction Template not found.")


@router.get("/interaction-sessions", response_model=list[InteractionSessionView])
def list_interaction_sessions(
    request: Request,
    user: CurrentUserDependency,
    connection_id: str | None = Query(default=None, max_length=64),
    guild_id: str | None = Query(default=None, max_length=200),
) -> list[InteractionSessionView]:
    return [
        session_view(request, item)
        for item in interaction_repository(request).list_sessions(
            user.id,
            connection_id=connection_id,
            guild_id=guild_id,
        )
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



def expression_view(
    request: Request,
    record: DiscordExpressionSemanticRecord,
) -> ExpressionSemanticView:
    expressions = expression_repository(request)
    return ExpressionSemanticView(
        id=record.id,
        resource_key=expression_key(record.resource_type, record.resource_id),
        connection_id=record.connection_id,
        guild_id=record.guild_id,
        resource_type=record.resource_type,  # type: ignore[arg-type]
        resource_id=record.resource_id,
        name=record.name,
        description=record.description,
        tags=expressions.tags(record),
        format_type=record.format_type,
        asset_url=record.asset_url,
        animated=record.animated,
        available=record.available,
        enabled=record.enabled,
        semantic_intent=record.semantic_intent,
        semantic_emotion=record.semantic_emotion,
        semantic_description=record.semantic_description,
        aliases=expressions.aliases(record),
        situations=expressions.situations(record),
        avoid_when=expressions.avoid_when(record),
        allowed_actions=expressions.allowed_actions(record),  # type: ignore[arg-type]
        semantic_source=record.semantic_source,  # type: ignore[arg-type]
        semantic_confidence=record.semantic_confidence,
        last_seen_at=record.last_seen_at,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def expression_node_view(
    request: Request,
    record: DiscordExpressionNodeRecord,
) -> ExpressionNodeView:
    expressions = expression_repository(request)
    return ExpressionNodeView(
        id=record.id,
        node_name=record.node_name,
        node_index=record.node_index,
        attempt=record.attempt,
        status=record.status,  # type: ignore[arg-type]
        input_summary=expressions.node_input(record),
        output_summary=expressions.node_output(record),
        error=record.error,
        started_at=record.started_at,
        completed_at=record.completed_at,
    )


def expression_run_view(
    request: Request,
    record: DiscordExpressionRunRecord,
) -> ExpressionRunView:
    return ExpressionRunView(
        id=record.id,
        connection_id=record.connection_id,
        guild_id=record.guild_id,
        channel_id=record.channel_id,
        source_message_id=record.source_message_id,
        deployment_id=record.deployment_id,
        character_card_id=record.character_card_id,
        status=record.status,  # type: ignore[arg-type]
        current_node=record.current_node,
        attempt_count=record.attempt_count,
        selected_action=record.selected_action,  # type: ignore[arg-type]
        selected_resource_key=record.selected_resource_key,
        state=expression_repository(request).run_state(record),
        last_error=record.last_error,
        created_at=record.created_at,
        updated_at=record.updated_at,
        completed_at=record.completed_at,
    )


@router.get(
    "/discord/expression-dictionary",
    response_model=list[ExpressionSemanticView],
)
def list_expression_dictionary(
    request: Request,
    user: CurrentUserDependency,
    connection_id: str | None = Query(default=None, max_length=64),
    guild_id: str | None = Query(default=None, max_length=200),
    resource_type: str | None = Query(default=None, pattern="^(emoji|sticker)$"),
) -> list[ExpressionSemanticView]:
    return [
        expression_view(request, item)
        for item in expression_repository(request).list_resources(
            user.id,
            connection_id=connection_id,
            guild_id=guild_id,
            resource_type=resource_type,
        )
    ]


@router.put(
    "/discord/expression-dictionary",
    response_model=ExpressionSemanticView,
)
def save_expression_dictionary_entry(
    payload: ExpressionSemanticCreate,
    request: Request,
    user: CurrentUserDependency,
) -> ExpressionSemanticView:
    try:
        record = expression_repository(request).upsert_manual_resource(
            owner_id=user.id,
            **payload.model_dump(),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Discord connection not found.") from exc
    return expression_view(request, record)


@router.get(
    "/discord/expression-runs",
    response_model=list[ExpressionRunView],
)
def list_expression_runs(
    request: Request,
    user: CurrentUserDependency,
    connection_id: str | None = Query(default=None, max_length=64),
    guild_id: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[ExpressionRunView]:
    return [
        expression_run_view(request, item)
        for item in expression_repository(request).list_runs(
            user.id,
            connection_id=connection_id,
            guild_id=guild_id,
            limit=limit,
        )
    ]


@router.get(
    "/discord/expression-runs/{run_id}",
    response_model=ExpressionRunDetail,
)
def get_expression_run(
    run_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> ExpressionRunDetail:
    record = expression_repository(request).get_run(run_id, user.id)
    if record is None:
        raise HTTPException(status_code=404, detail="Expression run not found.")
    base = expression_run_view(request, record)
    return ExpressionRunDetail(
        **base.model_dump(),
        nodes=[
            expression_node_view(request, item)
            for item in expression_repository(request).list_nodes(run_id, user.id)
        ],
    )
