"""Account-scoped automatic image-model discovery for OpenRouter Key Groups."""

from __future__ import annotations

from datetime import datetime
from typing import cast

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from echo_masque.api.dependencies import CurrentUserDependency
from echo_masque.credentials import CredentialVault
from echo_masque.openrouter_image_scout import (
    ImageModelCandidate,
    ImageModelScoutResult,
    OpenRouterImageScoutError,
    default_openrouter_image_model_scout,
)
from echo_masque.persistence import Database, KeyGroupRepository
from echo_masque.persistence.key_group_repository import default_models
from echo_masque.provider_credentials import ResolvedProviderCredential

router = APIRouter()


class ImageModelScoutCandidateView(BaseModel):
    model_id: str
    name: str
    description: str
    style_score: int
    style_matches: list[str]
    free_endpoint_count: int
    provider_names: list[str]


class ImageModelScoutView(BaseModel):
    selected_model: str | None
    candidates: list[ImageModelScoutCandidateView]
    checked_at: datetime
    total_image_models: int
    inspected_models: int
    from_cache: bool
    cache_ttl_seconds: int


def _database(request: Request) -> Database:
    return cast(Database, request.app.state.database)


def _repository(request: Request) -> KeyGroupRepository:
    return KeyGroupRepository(_database(request))


def _vault(request: Request) -> CredentialVault:
    store = request.app.state.credential_store
    if not isinstance(store, CredentialVault):
        raise HTTPException(status_code=503, detail="Encrypted Credential Vault is unavailable.")
    return store


def _candidate_view(item: ImageModelCandidate) -> ImageModelScoutCandidateView:
    return ImageModelScoutCandidateView(
        model_id=item.model_id,
        name=item.name,
        description=item.description,
        style_score=item.style_score,
        style_matches=list(item.style_matches),
        free_endpoint_count=item.free_endpoint_count,
        provider_names=list(item.provider_names),
    )


def _result_view(result: ImageModelScoutResult) -> ImageModelScoutView:
    return ImageModelScoutView(
        selected_model=result.selected_model,
        candidates=[_candidate_view(item) for item in result.candidates],
        checked_at=result.checked_at,
        total_image_models=result.total_image_models,
        inspected_models=result.inspected_models,
        from_cache=result.from_cache,
        cache_ttl_seconds=default_openrouter_image_model_scout.cache_ttl_seconds,
    )


@router.get(
    "/api/account/key-groups/{group_id}/image-model-scout",
    response_model=ImageModelScoutView,
)
async def scout_image_models(
    group_id: str,
    request: Request,
    user: CurrentUserDependency,
    refresh: bool = Query(default=False),
) -> ImageModelScoutView:
    group = _repository(request).get_group(user.id, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Key Group not found.")
    if group.provider.casefold().strip() != "openrouter":
        raise HTTPException(
            status_code=409,
            detail="Automatic free image-model discovery currently requires OpenRouter.",
        )
    api_key = _vault(request).get_scope(
        owner_id=user.id,
        scope_kind=CredentialVault.key_group_scope_kind,
        scope_id=group.id,
    )
    if api_key is None:
        raise HTTPException(status_code=409, detail="Key Group API key is not configured.")
    models = default_models(group)
    credential = ResolvedProviderCredential(
        key_group_id=group.id,
        provider=group.provider,
        base_url=group.base_url,
        model=models.get("image_generation", ""),
        api_key=api_key,
    )
    try:
        result = await default_openrouter_image_model_scout.discover(
            credential,
            force_refresh=refresh,
        )
    except OpenRouterImageScoutError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return _result_view(result)
