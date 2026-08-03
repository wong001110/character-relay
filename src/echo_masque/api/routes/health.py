"""Service health endpoints."""

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
from echo_masque.public_demo import PUBLIC_DEMO_EMAIL

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
    credential_ready_count = 0
    for card in cards:
        target = repository.get_target(card.target_id)
        if target is not None and (
            target.target_kind != "prompt_model"
            or credential_store.get(user.id, card.id) is not None
        ):
            credential_ready_count += 1

    scenarios = workspace_repository.list_scenarios(user.id)
    packs = workspace_repository.list_packs(user.id)
    return PublicDemoStatusResponse(
        enabled=True,
        ready=(
            len(cards) == 2
            and bool(scenarios)
            and bool(packs)
            and credential_ready_count == len(cards)
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
