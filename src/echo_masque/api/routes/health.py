"""Service health endpoints."""

import os
from typing import cast

from fastapi import APIRouter, Request
from pydantic import BaseModel

from echo_masque.config import Settings
from echo_masque.credentials import CredentialStore
from echo_masque.persistence import (
    AuthRepository,
    Repository,
    StorageStatus,
    WorkspaceRepository,
)
from echo_masque.persistence.models import CharacterCardRecord
from echo_masque.public_demo import PUBLIC_DEMO_EMAIL
from echo_masque.targets import PromptModelConfig

router = APIRouter(tags=["system"])


class StorageHealthResponse(BaseModel):
    database_kind: str
    database_path: str | None
    persistent_required: bool
    mount_path: str | None
    mount_ready: bool
    storage_instance_id: str


class ServiceHealthResponse(BaseModel):
    name: str
    version: str
    status: str = "ok"
    environment: str
    storage: StorageHealthResponse


class PublicDemoStatusResponse(BaseModel):
    enabled: bool
    ready: bool
    email: str
    role: str
    character_names: list[str]
    scenario_count: int
    test_pack_count: int
    credential_ready_count: int
    read_only: bool
    daily_run_limit: int
    secrets_included: bool = False


@router.get("/health", response_model=ServiceHealthResponse)
def health(request: Request) -> ServiceHealthResponse:
    """Report process and persistence health without touching external providers."""

    settings = cast(Settings, request.app.state.settings)
    storage = cast(StorageStatus, request.app.state.storage_status)
    if storage.storage_instance_id is None:
        raise RuntimeError("Storage identity is unavailable after database initialization.")
    return ServiceHealthResponse(
        name=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        storage=StorageHealthResponse(
            database_kind=storage.database_kind,
            database_path=storage.database_path,
            persistent_required=storage.persistent_required,
            mount_path=storage.mount_path,
            mount_ready=storage.mount_ready,
            storage_instance_id=storage.storage_instance_id,
        ),
    )


def _credential_ready(
    repository: Repository,
    credential_store: CredentialStore,
    owner_id: str,
    card: CharacterCardRecord,
) -> bool:
    target = repository.get_target(card.target_id)
    if target is None:
        return False
    if target.target_kind != "prompt_model":
        return True
    if credential_store.get(owner_id, card.id) is not None:
        return True
    config = PromptModelConfig.model_validate_json(target.config_json)
    return bool(os.getenv(config.api_key_env))


def _public_demo_ready(
    *,
    card_count: int,
    credential_ready_count: int,
    scenario_count: int,
    test_pack_count: int,
) -> bool:
    """Require a useful Demo set without fixing the catalog to exactly two cards."""

    return (
        card_count >= 2
        and scenario_count > 0
        and test_pack_count > 0
        and credential_ready_count == card_count
    )


@router.get("/api/public-demo/status", response_model=PublicDemoStatusResponse)
def public_demo_status(request: Request) -> PublicDemoStatusResponse:
    """Expose only non-sensitive readiness metadata for the shared Demo workspace."""

    settings = cast(Settings, request.app.state.settings)
    auth_repository = cast(AuthRepository, request.app.state.auth_repository)
    repository = cast(Repository, request.app.state.repository)
    workspace_repository = cast(
        WorkspaceRepository,
        request.app.state.workspace_repository,
    )
    credential_store = cast(CredentialStore, request.app.state.credential_store)

    user = auth_repository.get_user_by_email(PUBLIC_DEMO_EMAIL)
    if not settings.public_demo_enabled or user is None or not user.is_active:
        return PublicDemoStatusResponse(
            enabled=settings.public_demo_enabled,
            ready=False,
            email=PUBLIC_DEMO_EMAIL,
            role="user",
            character_names=[],
            scenario_count=0,
            test_pack_count=0,
            credential_ready_count=0,
            read_only=True,
            daily_run_limit=settings.public_demo_max_runs_per_day,
        )

    cards = repository.list_character_cards(user.id)
    credential_ready_count = sum(
        1
        for card in cards
        if _credential_ready(repository, credential_store, user.id, card)
    )
    scenarios = workspace_repository.list_scenarios(user.id)
    packs = workspace_repository.list_packs(user.id)
    return PublicDemoStatusResponse(
        enabled=True,
        ready=_public_demo_ready(
            card_count=len(cards),
            credential_ready_count=credential_ready_count,
            scenario_count=len(scenarios),
            test_pack_count=len(packs),
        ),
        email=PUBLIC_DEMO_EMAIL,
        role=user.role,
        character_names=sorted(card.display_name for card in cards),
        scenario_count=len(scenarios),
        test_pack_count=len(packs),
        credential_ready_count=credential_ready_count,
        read_only=True,
        daily_run_limit=settings.public_demo_max_runs_per_day,
    )
