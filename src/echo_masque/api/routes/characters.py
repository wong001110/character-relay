"""Character Card collection and provider credential endpoints."""

import os
from typing import Annotated, cast

from fastapi import APIRouter, Header, HTTPException, Request, status

from echo_masque.api.schemas import (
    CharacterCardCreate,
    CharacterCardFields,
    CharacterCardUpdate,
    CharacterCardView,
    CredentialConfigure,
    CredentialStatus,
    PromptCharacterCreate,
)
from echo_masque.credentials import CredentialStore
from echo_masque.persistence import MatrixRepository, Repository
from echo_masque.targets import PromptModelConfig

router = APIRouter(prefix="/api/characters", tags=["characters"])


def repository(request: Request) -> Repository:
    return cast(Repository, request.app.state.repository)


def matrix_repository(request: Request) -> MatrixRepository:
    return cast(MatrixRepository, request.app.state.matrix_repository)


def credential_store(request: Request) -> CredentialStore:
    return cast(CredentialStore, request.app.state.credential_store)


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
    target = repo.get_target(card.target_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Target binding not found.")
    if target.target_kind != "prompt_model":
        return CredentialStatus(
            required=False,
            configured=True,
            source="not_required",
        )
    config = PromptModelConfig.model_validate_json(target.config_json)
    if credential_store(request).has(owner_id, card_id):
        return CredentialStatus(required=True, configured=True, source="memory")
    if os.getenv(config.api_key_env):
        return CredentialStatus(required=True, configured=True, source="environment")
    return CredentialStatus(required=True, configured=False, source="missing")


@router.get("", response_model=list[CharacterCardView])
def list_characters(
    request: Request,
    owner_id: Annotated[str, Header(alias="X-Echo-User")] = "local-user",
) -> list[CharacterCardView]:
    return [
        CharacterCardView.from_record(item)
        for item in repository(request).list_character_cards(owner_id)
    ]


@router.post("", response_model=CharacterCardView, status_code=status.HTTP_201_CREATED)
def create_character(
    payload: CharacterCardCreate,
    request: Request,
    owner_id: Annotated[str, Header(alias="X-Echo-User")] = "local-user",
) -> CharacterCardView:
    repo = repository(request)
    if repo.get_target(payload.target_id) is None:
        raise HTTPException(status_code=404, detail="Target binding not found.")
    card = _create_card(
        repo,
        owner_id=owner_id,
        target_id=payload.target_id,
        payload=payload,
    )
    matrix_repository(request).capture_prompt_version(owner_id, card.id)
    return card


@router.post(
    "/prompt-model",
    response_model=CharacterCardView,
    status_code=status.HTTP_201_CREATED,
)
def create_prompt_character(
    payload: PromptCharacterCreate,
    request: Request,
    owner_id: Annotated[str, Header(alias="X-Echo-User")] = "local-user",
) -> CharacterCardView:
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
    card = _create_card(
        repo,
        owner_id=owner_id,
        target_id=target.id,
        payload=payload,
    )
    credential_store(request).set(owner_id, card.id, payload.api_key)
    matrix_repository(request).capture_prompt_version(owner_id, card.id, label="Initial")
    return card


@router.put("/{card_id}", response_model=CharacterCardView)
def update_character(
    card_id: str,
    payload: CharacterCardUpdate,
    request: Request,
    owner_id: Annotated[str, Header(alias="X-Echo-User")] = "local-user",
) -> CharacterCardView:
    repo = repository(request)
    card = repo.get_character_card(card_id, owner_id)
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
        owner_id=owner_id,
        card_id=card_id,
        payload=payload,
    )
    if prompt_changed:
        matrix_repository(request).capture_prompt_version(owner_id, card_id)
    return updated


@router.get("/{card_id}/credential", response_model=CredentialStatus)
def credential_status(
    card_id: str,
    request: Request,
    owner_id: Annotated[str, Header(alias="X-Echo-User")] = "local-user",
) -> CredentialStatus:
    return _status_for(request, owner_id=owner_id, card_id=card_id)


@router.put("/{card_id}/credential", response_model=CredentialStatus)
def configure_credential(
    card_id: str,
    payload: CredentialConfigure,
    request: Request,
    owner_id: Annotated[str, Header(alias="X-Echo-User")] = "local-user",
) -> CredentialStatus:
    current = _status_for(request, owner_id=owner_id, card_id=card_id)
    if not current.required:
        raise HTTPException(
            status_code=409,
            detail="This Character Card does not use a model-provider credential.",
        )
    credential_store(request).set(owner_id, card_id, payload.api_key)
    return CredentialStatus(required=True, configured=True, source="memory")


@router.delete("/{card_id}/credential", status_code=status.HTTP_204_NO_CONTENT)
def clear_credential(
    card_id: str,
    request: Request,
    owner_id: Annotated[str, Header(alias="X-Echo-User")] = "local-user",
) -> None:
    _status_for(request, owner_id=owner_id, card_id=card_id)
    credential_store(request).delete(owner_id, card_id)


@router.get("/{card_id}", response_model=CharacterCardView)
def get_character(
    card_id: str,
    request: Request,
    owner_id: Annotated[str, Header(alias="X-Echo-User")] = "local-user",
) -> CharacterCardView:
    record = repository(request).get_character_card(card_id, owner_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Character Card not found.")
    return CharacterCardView.from_record(record)


@router.delete("/{card_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_character(
    card_id: str,
    request: Request,
    owner_id: Annotated[str, Header(alias="X-Echo-User")] = "local-user",
) -> None:
    if not repository(request).delete_character_card(card_id, owner_id):
        raise HTTPException(status_code=409, detail="Character Card cannot be deleted.")
    credential_store(request).delete(owner_id, card_id)
