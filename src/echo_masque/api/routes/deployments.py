"""Platform connection and character deployment management endpoints."""

from typing import cast

from fastapi import APIRouter, HTTPException, Query, Request, status

from echo_masque.api.dependencies import CurrentUserDependency
from echo_masque.api.deployment_schemas import (
    CharacterDeploymentCreate,
    CharacterDeploymentPage,
    CharacterDeploymentStatusUpdate,
    CharacterDeploymentUpdate,
    CharacterDeploymentView,
    DeploymentLogView,
    DiscordServerCatalogView,
    DiscordServerProfileCreate,
    DiscordServerProfileUpdate,
    DiscordServerProfileView,
    PlatformConnectionCreate,
    PlatformConnectionUpdate,
    PlatformConnectionView,
)
from echo_masque.persistence import (
    DeploymentConflict,
    DeploymentLogRepository,
    DeploymentRepository,
    InteractionRepository,
    Repository,
)
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord

router = APIRouter(prefix="/api", tags=["deployments"])


def deployment_repository(request: Request) -> DeploymentRepository:
    return cast(DeploymentRepository, request.app.state.deployment_repository)


def deployment_log_repository(request: Request) -> DeploymentLogRepository:
    return cast(DeploymentLogRepository, request.app.state.deployment_log_repository)


def character_repository(request: Request) -> Repository:
    return cast(Repository, request.app.state.repository)


def interaction_repository(request: Request) -> InteractionRepository:
    return cast(InteractionRepository, request.app.state.interaction_repository)


def deployment_view(
    request: Request,
    *,
    owner_id: str,
    record: CharacterDeploymentRecord,
) -> CharacterDeploymentView:
    repo = deployment_repository(request)
    card = character_repository(request).get_character_card(record.character_card_id, owner_id)
    scope = repo.get_deployment_scope(record.id)
    profile = repo.get_server_profile_for_deployment(record.id) if scope is not None else None
    return CharacterDeploymentView.from_record(
        record,
        character_display_name=card.display_name if card is not None else "Archived character",
        scope=scope,
        server_profile_name=profile.name if profile is not None else "",
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
    deployments = deployment_repository(request)
    connection = deployments.get_connection(connection_id, user.id)
    if connection is None:
        raise HTTPException(status_code=404, detail="Platform connection not found.")
    profile_ids = [
        item.id
        for item in deployments.list_server_profiles(user.id)
        if item.connection_id == connection_id
    ]
    deployment_log_repository(request).delete_connection_scope(connection_id)
    interaction_repository(request).delete_connection_scope(
        owner_id=user.id,
        connection_id=connection_id,
        server_profile_ids=profile_ids,
    )
    if not deployments.delete_connection(connection_id, user.id):
        raise HTTPException(status_code=404, detail="Platform connection not found.")


@router.get(
    "/discord/server-catalog",
    response_model=list[DiscordServerCatalogView],
)
def list_discord_server_catalog(
    request: Request,
    user: CurrentUserDependency,
    connection_id: str | None = Query(default=None, max_length=64),
) -> list[DiscordServerCatalogView]:
    return [
        DiscordServerCatalogView.from_record(item)
        for item in deployment_repository(request).list_discord_server_catalog(
            user.id,
            connection_id=connection_id,
        )
    ]


@router.get(
    "/discord/server-profiles",
    response_model=list[DiscordServerProfileView],
)
def list_discord_server_profiles(
    request: Request,
    user: CurrentUserDependency,
) -> list[DiscordServerProfileView]:
    return [
        DiscordServerProfileView.from_record(item)
        for item in deployment_repository(request).list_server_profiles(user.id)
    ]


@router.post(
    "/discord/server-profiles",
    response_model=DiscordServerProfileView,
    status_code=status.HTTP_201_CREATED,
)
def create_discord_server_profile(
    payload: DiscordServerProfileCreate,
    request: Request,
    user: CurrentUserDependency,
) -> DiscordServerProfileView:
    try:
        record = deployment_repository(request).create_server_profile(
            owner_id=user.id,
            connection_id=payload.connection_id,
            name=payload.name,
            guild_id=payload.guild_id,
            guild_name=payload.guild_name,
            excluded_channel_ids=payload.excluded_channel_ids,
            excluded_category_ids=payload.excluded_category_ids,
            thread_policy=payload.thread_policy,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Discord connection not found.") from exc
    except DeploymentConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return DiscordServerProfileView.from_record(record)


@router.patch(
    "/discord/server-profiles/{profile_id}",
    response_model=DiscordServerProfileView,
)
def update_discord_server_profile(
    profile_id: str,
    payload: DiscordServerProfileUpdate,
    request: Request,
    user: CurrentUserDependency,
) -> DiscordServerProfileView:
    record = deployment_repository(request).update_server_profile(
        profile_id,
        user.id,
        **payload.model_dump(exclude_unset=True),
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Discord server profile not found.")
    return DiscordServerProfileView.from_record(record)


@router.delete(
    "/discord/server-profiles/{profile_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_discord_server_profile(
    profile_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> None:
    deployments = deployment_repository(request)
    profile = deployments.get_server_profile(profile_id, user.id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Discord server profile not found.")
    try:
        deleted = deployments.delete_server_profile(profile_id, user.id)
    except DeploymentConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Discord server profile not found.")
    interaction_repository(request).delete_server_scope(
        owner_id=user.id,
        server_profile_id=profile.id,
        connection_id=profile.connection_id,
        guild_id=profile.guild_id,
    )


@router.get("/deployment-logs", response_model=list[DeploymentLogView])
def list_deployment_logs(
    request: Request,
    user: CurrentUserDependency,
    connection_id: str | None = Query(default=None, max_length=64),
    deployment_id: str | None = Query(default=None, max_length=64),
    level: str | None = Query(
        default=None,
        pattern="^(debug|info|warning|error)$",
    ),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[DeploymentLogView]:
    if connection_id is not None:
        connection = deployment_repository(request).get_connection(connection_id, user.id)
        if connection is None:
            raise HTTPException(status_code=404, detail="Platform connection not found.")
    records = deployment_log_repository(request).list_events(
        user.id,
        connection_id=connection_id,
        deployment_id=deployment_id,
        level=level,
        limit=limit,
    )
    return [DeploymentLogView.from_record(item) for item in records]


@router.get("/deployments", response_model=list[CharacterDeploymentView])
def list_deployments(
    request: Request,
    user: CurrentUserDependency,
    character_card_id: str | None = Query(default=None),
    server_profile_id: str | None = Query(default=None, max_length=64),
) -> list[CharacterDeploymentView]:
    records = deployment_repository(request).list_deployments(
        user.id,
        character_card_id=character_card_id,
        server_profile_id=server_profile_id,
    )
    return [deployment_view(request, owner_id=user.id, record=record) for record in records]


@router.get("/deployments/page", response_model=CharacterDeploymentPage)
def paginate_deployments(
    request: Request,
    user: CurrentUserDependency,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    character_card_id: str | None = Query(default=None),
    platform: str | None = Query(default=None, max_length=24),
    deployment_status: str | None = Query(
        default=None,
        alias="status",
        max_length=24,
    ),
    server_profile_id: str | None = Query(default=None, max_length=64),
) -> CharacterDeploymentPage:
    records, safe_page, total, pages, counts = deployment_repository(request).list_deployments_page(
        user.id,
        page=page,
        page_size=page_size,
        character_card_id=character_card_id,
        platform=platform,
        status=deployment_status,
        server_profile_id=server_profile_id,
    )
    return CharacterDeploymentPage(
        items=[deployment_view(request, owner_id=user.id, record=record) for record in records],
        page=safe_page,
        page_size=page_size,
        total=total,
        pages=pages,
        active=counts["active"],
        paused=counts["paused"],
        attention=counts["attention"],
    )


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
            server_profile_id=payload.server_profile_id,
            workspace_id=payload.workspace_id,
            workspace_name=payload.workspace_name,
            channel_id=payload.channel_id,
            channel_name=payload.channel_name,
            thread_id=payload.thread_id,
            thread_name=payload.thread_name,
            excluded_channel_ids=payload.excluded_channel_ids,
            excluded_category_ids=payload.excluded_category_ids,
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
    except KeyError as exc:
        resource = str(exc).strip("'")
        raise HTTPException(status_code=404, detail=f"{resource.title()} not found.") from exc
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
