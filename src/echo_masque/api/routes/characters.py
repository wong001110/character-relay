"""Character Card collection and provider credential endpoints."""

import os
from typing import Literal, cast

from fastapi import APIRouter, HTTPException, Request, status

from echo_masque.api.dependencies import (
    CurrentUserDependency,
    quota_http_exception,
    quota_service,
)
from echo_masque.api.schemas import (
    CharacterCardCreate,
    CharacterCardFields,
    CharacterCardUpdate,
    CharacterCardView,
    CredentialConfigure,
    CredentialStatus,
    PromptCharacterCreate,
)
from echo_masque.character_assistant import (
    CharacterAssistantService,
    CharacterAssistantUnavailable,
    CharacterSuggestionRequest,
    CharacterSuggestionResult,
)
from echo_masque.character_prompts import CharacterPromptProfile
from echo_masque.credentials import (
    CredentialStore,
    CredentialVault,
    CredentialVaultUnavailable,
)
from echo_masque.persistence import MatrixRepository, Repository, TargetAccessRepository
from echo_masque.persistence.models import CharacterCardRecord
from echo_masque.providers import ProviderError
from echo_masque.security_controls import QuotaExceeded
from echo_masque.targets import PromptModelConfig

router = APIRouter(prefix="/api/characters", tags=["characters"])


def repository(request: Request) -> Repository:
    return cast(Repository, request.app.state.repository)


def matrix_repository(request: Request) -> MatrixRepository:
    return cast(MatrixRepository, request.app.state.matrix_repository)


def credential_store(request: Request) -> CredentialStore:
    return cast(CredentialStore, request.app.state.credential_store)


def credential_source(request: Request) -> Literal["vault", "memory"]:
    store = credential_store(request)
    if isinstance(store, CredentialVault) and store.settings.environment == "production":
        return "vault"
    return "memory"


def target_access(request: Request) -> TargetAccessRepository:
    return cast(TargetAccessRepository, request.app.state.target_access_repository)


def _enforce_create_quota(request: Request, owner_id: str) -> None:
    try:
        quota_service(request).enforce_create(owner_id, "character")
    except QuotaExceeded as exc:
        raise quota_http_exception(exc) from exc


def _sync_prompt_profile(repo: Repository, card: CharacterCardRecord) -> None:
    """Keep persisted prompt targets compatible with the runtime compiler."""

    target = repo.get_target(card.target_id)
    if target is None or target.target_kind != "prompt_model":
        return
    current = PromptModelConfig.model_validate_json(target.config_json)
    profile = CharacterPromptProfile.from_record(card)
    if current.character_profile == profile:
        return
    updated = current.model_copy(update={"character_profile": profile})
    repo.update_target(
        target.id,
        name=target.name,
        config=updated.model_dump(mode="json"),
    )


def _create_card(
    repo: Repository,
    *,
    owner_id: str,
    target_id: str,
    payload: CharacterCardFields,
) -> CharacterCardView:
    record = repo.create_character_card(
        owner_id=owner_id,
        target_id=target_id,
        display_name=payload.display_name,
        subtitle=payload.subtitle,
        subject_type=payload.subject_type,
        persona_summary=payload.persona_summary,
        traits=payload.traits,
        tags=payload.tags,
        expected_tone=payload.expected_tone,
        forbidden_behaviors=payload.forbidden_behaviors,
        memory_summary=payload.memory_summary,
        preferred_suites=[item.value for item in payload.preferred_suites],
        portrait_variant=payload.portrait_variant,
    )
    _sync_prompt_profile(repo, record)
    return CharacterCardView.from_record(record)


def _update_card(
    repo: Repository,
    *,
    owner_id: str,
    card_id: str,
    payload: CharacterCardFields,
) -> CharacterCardView:
    record = repo.update_character_card(
        card_id,
        owner_id,
        display_name=payload.display_name,
        subtitle=payload.subtitle,
        subject_type=payload.subject_type,
        persona_summary=payload.persona_summary,
        traits=payload.traits,
        tags=payload.tags,
        expected_tone=payload.expected_tone,
        forbidden_behaviors=payload.forbidden_behaviors,
        memory_summary=payload.memory_summary,
        preferred_suites=[item.value for item in payload.preferred_suites],
        portrait_variant=payload.portrait_variant,
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Character Card not found.")
    _sync_prompt_profile(repo, record)
    return CharacterCardView.from_record(record)


def _status_for(
    request: Request,
    *,
    owner_id: str,
    card_id: str,
) -> CredentialStatus:
    repo = repository(request)
    card = repo.get_character_card(card_id, owner_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Character Card not found.")
    _sync_prompt_profile(repo, card)
    target = repo.get_target(card.target_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Target binding not found.")
    if target.target_kind != "prompt_model":
        return CredentialStatus(required=False, configured=True, source="not_required")
    config = PromptModelConfig.model_validate_json(target.config_json)
    if credential_store(request).has(owner_id, card_id):
        return CredentialStatus(
            required=True,
            configured=True,
            source=credential_source(request),
        )
    if os.getenv(config.api_key_env):
        return CredentialStatus(required=True, configured=True, source="environment")
    return CredentialStatus(required=True, configured=False, source="missing")


@router.get("", response_model=list[CharacterCardView])
def list_characters(
    request: Request,
    user: CurrentUserDependency,
) -> list[CharacterCardView]:
    repo = repository(request)
    records = repo.list_character_cards(user.id)
    for item in records:
        _sync_prompt_profile(repo, item)
    return [CharacterCardView.from_record(item) for item in records]


@router.post("/suggest", response_model=CharacterSuggestionResult)
async def suggest_character_card(
    payload: CharacterSuggestionRequest,
    request: Request,
    user: CurrentUserDependency,
) -> CharacterSuggestionResult:
    try:
        quota_service(request).consume_authoring_generation(user.id)
        return await CharacterAssistantService(
            request.app.state.authoring_runtime_service
        ).suggest(payload)
    except QuotaExceeded as exc:
        raise quota_http_exception(exc) from exc
    except CharacterAssistantUnavailable as exc:
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


@router.post("", response_model=CharacterCardView, status_code=status.HTTP_201_CREATED)
def create_character(
    payload: CharacterCardCreate,
    request: Request,
    user: CurrentUserDependency,
) -> CharacterCardView:
    _enforce_create_quota(request, user.id)
    repo = repository(request)
    target = repo.get_target(payload.target_id)
    if target is None or not target_access(request).can_access(
        owner_id=user.id,
        target_id=payload.target_id,
    ):
        raise HTTPException(status_code=404, detail="Target binding not found.")
    card = _create_card(
        repo,
        owner_id=user.id,
        target_id=payload.target_id,
        payload=payload,
    )
    matrix_repository(request).capture_prompt_version(user.id, card.id)
    return card


@router.post(
    "/prompt-model",
    response_model=CharacterCardView,
    status_code=status.HTTP_201_CREATED,
)
def create_prompt_character(
    payload: PromptCharacterCreate,
    request: Request,
    user: CurrentUserDependency,
) -> CharacterCardView:
    _enforce_create_quota(request, user.id)
    repo = repository(request)
    config = PromptModelConfig(
        name=payload.display_name,
        provider=payload.provider,
        model=payload.model,
        system_prompt=payload.system_prompt,
        base_url=payload.base_url,
        temperature=payload.temperature,
    )
    target = repo.create_target(
        name=payload.display_name,
        target_kind="prompt_model",
        config=config.model_dump(mode="json"),
    )
    target_access(request).assign(owner_id=user.id, target_id=target.id)
    card = _create_card(
        repo,
        owner_id=user.id,
        target_id=target.id,
        payload=payload,
    )
    try:
        credential_store(request).set(user.id, card.id, payload.api_key)
    except CredentialVaultUnavailable as exc:
        repo.delete_character_card(card.id, user.id)
        target_access(request).remove(owner_id=user.id, target_id=target.id)
        repo.delete_target(target.id)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    matrix_repository(request).capture_prompt_version(user.id, card.id, label="Initial")
    return card


@router.put("/{card_id}", response_model=CharacterCardView)
def update_character(
    card_id: str,
    payload: CharacterCardUpdate,
    request: Request,
    user: CurrentUserDependency,
) -> CharacterCardView:
    repo = repository(request)
    card = repo.get_character_card(card_id, user.id)
    if card is None:
        raise HTTPException(status_code=404, detail="Character Card not found.")
    target = repo.get_target(card.target_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Target binding not found.")
    prompt_changed = False
    if target.target_kind == "prompt_model":
        current = PromptModelConfig.model_validate_json(target.config_json)
        config = PromptModelConfig(
            name=payload.display_name,
            provider=payload.provider or current.provider,
            model=payload.model or current.model,
            system_prompt=payload.system_prompt or current.system_prompt,
            base_url=payload.base_url or current.base_url,
            api_key_env=current.api_key_env,
            temperature=(
                payload.temperature if payload.temperature is not None else current.temperature
            ),
            character_profile=current.character_profile,
        )
        prompt_changed = config.model_dump(mode="json") != current.model_dump(mode="json")
        if repo.update_target(
            target.id,
            name=payload.display_name,
            config=config.model_dump(mode="json"),
        ) is None:
            raise HTTPException(status_code=404, detail="Target binding not found.")
    updated = _update_card(
        repo,
        owner_id=user.id,
        card_id=card_id,
        payload=payload,
    )
    if prompt_changed:
        matrix_repository(request).capture_prompt_version(user.id, card_id)
    return updated


@router.get("/{card_id}/credential", response_model=CredentialStatus)
def credential_status(
    card_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> CredentialStatus:
    return _status_for(request, owner_id=user.id, card_id=card_id)


@router.put("/{card_id}/credential", response_model=CredentialStatus)
def configure_credential(
    card_id: str,
    payload: CredentialConfigure,
    request: Request,
    user: CurrentUserDependency,
) -> CredentialStatus:
    current = _status_for(request, owner_id=user.id, card_id=card_id)
    if not current.required:
        raise HTTPException(
            status_code=409,
            detail="This Character Card does not use a model-provider credential.",
        )
    try:
        credential_store(request).set(user.id, card_id, payload.api_key)
    except CredentialVaultUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return CredentialStatus(
        required=True,
        configured=True,
        source=credential_source(request),
    )


@router.delete("/{card_id}/credential", status_code=status.HTTP_204_NO_CONTENT)
def clear_credential(
    card_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> None:
    _status_for(request, owner_id=user.id, card_id=card_id)
    credential_store(request).delete(user.id, card_id)


@router.get("/{card_id}", response_model=CharacterCardView)
def get_character(
    card_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> CharacterCardView:
    repo = repository(request)
    record = repo.get_character_card(card_id, user.id)
    if record is None:
        raise HTTPException(status_code=404, detail="Character Card not found.")
    _sync_prompt_profile(repo, record)
    return CharacterCardView.from_record(record)
