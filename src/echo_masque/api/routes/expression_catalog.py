"""Owner-scoped Discord expression catalog; optional explicit metadata enrichment only."""

from typing import cast

from fastapi import APIRouter, HTTPException, Query, Request, status

from echo_masque.api.dependencies import CurrentUserDependency, quota_http_exception, quota_service
from echo_masque.api.expression_schemas import ExpressionSemanticCreate, ExpressionSemanticView
from echo_masque.expression_assistant import (
    ExpressionAssistantService,
    ExpressionAssistantUnavailable,
    ExpressionSuggestionRequest,
    ExpressionSuggestionResult,
)
from echo_masque.persistence import ExpressionRepository
from echo_masque.persistence.expression_models import DiscordExpressionSemanticRecord
from echo_masque.persistence.expression_repository import expression_key
from echo_masque.providers import ProviderError
from echo_masque.security_controls import QuotaExceeded

router = APIRouter(prefix="/api", tags=["expressions"])


def expression_repository(request: Request) -> ExpressionRepository:
    return cast(ExpressionRepository, request.app.state.expression_repository)


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


@router.post(
    "/discord/expression-dictionary/suggest",
    response_model=ExpressionSuggestionResult,
)
async def suggest_expression_dictionary_entry(
    payload: ExpressionSuggestionRequest,
    request: Request,
    user: CurrentUserDependency,
) -> ExpressionSuggestionResult:
    runtime = request.app.state.authoring_runtime_service
    try:
        quota_service(request).consume_authoring_generation(user.id)
        return await ExpressionAssistantService(runtime).suggest(payload)
    except QuotaExceeded as exc:
        raise quota_http_exception(exc) from exc
    except ExpressionAssistantUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except ProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
