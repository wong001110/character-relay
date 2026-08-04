"""Platform connection and character deployment management endpoints."""

from typing import cast

from fastapi import APIRouter, HTTPException, Query, Request, status

from echo_masque.api.dependencies import CurrentUserDependency
from echo_masque.api.deployment_schemas import (
    CharacterDeploymentCreate,
    CharacterDeploymentStatusUpdate,
    CharacterDeploymentUpdate,
    CharacterDeploymentView,
    PlatformConnectionCreate,
    PlatformConnectionUpdate,
    PlatformConnectionView,
)
from echo_masque.persistence import DeploymentConflict, DeploymentRepository, Repository
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord

router = APIRouter(prefix="/api", tags=["deployments"])


def deployment_repository(request: Request) -> DeploymentRepository:
    return cast(DeploymentRepository, request.app.state.deployment_repository)


def character_repository(request: Request) -> Repository:
    return cast(Repository, request.app.state.repository)


def deployment_view(
    request: Request,
    *,
    owner_id: str,
    record: CharacterDeploymentRecord,
) -> CharacterDeploymentView:
    card = character_repository(request).get_character_card(record.character_card_id, owner_id)
    return CharacterDeploymentView.from_record(
        record,
        character_display_name=card.display_name if card is not None else "Archived character",
    )


@router.get("/connections", response_model=list[PlatformConnectionView])
def list_connections(
    request: Request,
    user: CurrentUserDependency,
) -> list[PlatformConnectionView]:
    return [
        PlatformConnectionView.from_record(item)
        for item in deployment_repository(request).list_connections(user.id)
    ]


@router.post(
    "/connections",
    response_model=PlatformConnectionView,
    status_code=status.HTTP_201_CREATED,
)
def create_connection(
    payload: PlatformConnectionCreate,
    request: Request,
    user: CurrentUserDependency,
) -> PlatformConnectionView:
    record = deployment_repository(request).create_connection(
        owner_id=user.id,
        platform=payload.platform,
        display_name=payload.display_name,
        connection_mode=payload.connection_mode,
        external_account_id=payload.external_account_id,
        status=payload.status,
        metadata=payload.metadata,
    )
    return PlatformConnectionView.from_record(record)


@router.patch("/connections/{connection_id}", response_model=PlatformConnectionView)
def update_connection(
    connection_id: str,
    payload: PlatformConnectionUpdate,
    request: Request,
    user: CurrentUserDependency,
) -> PlatformConnectionView:
    record = deployment_repository(request).update_connection(
        connection_id,
        user.id,
        display_name=payload.display_name,
        connection_mode=payload.connection_mode,
        external_account_id=payload.external_account_id,
        status=payload.status,
        metadata=payload.metadata,
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Platform connection not found.")
    return PlatformConnectionView.from_record(record)


@router.delete("/connections/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_connection(
    connection_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> None:
    if not deployment_repository(request).delete_connection(connection_id, user.id):
        raise HTTPException(status_code=404, detail="Platform connection not found.")


@router.get("/deployments", response_model=list[CharacterDeploymentView])
def list_deployments(
    request: Request,
    user: CurrentUserDependency,
    character_card_id: str | None = Query(default=None),
) -> list[CharacterDeploymentView]:
    records = deployment_repository(request).list_deployments(
        user.id,
        character_card_id=character_card_id,
    )
    return [
        deployment_view(request, owner_id=user.id, record=record)
        for record in records
    ]


@router.post(
    "/deployments",
    response_model=CharacterDeploymentView,
    status_code=status.HTTP_201_CREATED,
)
def create_deployment(
    payload: CharacterDeploymentCreate,
    request: Request,
    user: CurrentUserDependency,
) -> CharacterDeploymentView:
    repo = deployment_repository(request)
    try:
        record = repo.create_deployment(
            owner_id=user.id,
            character_card_id=payload.character_card_id,
            connection_id=payload.connection_id,
            workspace_id=payload.workspace_id,
            workspace_name=payload.workspace_name,
            channel_id=payload.channel_id,
            channel_name=payload.channel_name,
            thread_id=payload.thread_id,
            thread_name=payload.thread_name,
            participation_mode=payload.participation_mode,
            memory_scope=payload.memory_scope,
            version_label=payload.version_label,
            sticker_count=payload.sticker_count,
            status=payload.status,
        )
    except KeyError as exc:
        resource = str(exc).strip("'")
        raise HTTPException(status_code=404, detail=f"{resource.title()} not found.") from exc
    except DeploymentConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return deployment_view(request, owner_id=user.id, record=record)


@router.put("/deployments/{deployment_id}", response_model=CharacterDeploymentView)
def update_deployment(
    deployment_id: str,
    payload: CharacterDeploymentUpdate,
    request: Request,
    user: CurrentUserDependency,
) -> CharacterDeploymentView:
    values = payload.model_dump(exclude_unset=True)
    try:
        record = deployment_repository(request).update_deployment(
            deployment_id,
            user.id,
            **values,
        )
    except DeploymentConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="Deployment not found.")
    return deployment_view(request, owner_id=user.id, record=record)


@router.patch(
    "/deployments/{deployment_id}/status",
    response_model=CharacterDeploymentView,
)
def update_deployment_status(
    deployment_id: str,
    payload: CharacterDeploymentStatusUpdate,
    request: Request,
    user: CurrentUserDependency,
) -> CharacterDeploymentView:
    record = deployment_repository(request).update_deployment(
        deployment_id,
        user.id,
        status=payload.status,
        last_error=payload.last_error,
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Deployment not found.")
    return deployment_view(request, owner_id=user.id, record=record)


@router.delete("/deployments/{deployment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_deployment(
    deployment_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> None:
    if not deployment_repository(request).delete_deployment(deployment_id, user.id):
        raise HTTPException(status_code=404, detail="Deployment not found.")
