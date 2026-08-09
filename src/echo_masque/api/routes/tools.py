"""Tool Calling catalog, deployment assignment, and Server runtime endpoints."""

from typing import cast

from fastapi import APIRouter, HTTPException, Request

from echo_masque.api.dependencies import CurrentUserDependency
from echo_masque.api.tool_schemas import (
    DeploymentToolProfileUpdate,
    DeploymentToolProfileView,
    ServerRuntimeTimezoneUpdate,
    ServerRuntimeTimezoneView,
    ToolCatalogView,
)
from echo_masque.persistence import DeploymentToolRepository
from echo_masque.persistence.server_runtime_repository import ServerRuntimeRepository
from echo_masque.server_time import validate_timezone
from echo_masque.tool_runtime import ToolRegistry

router = APIRouter(prefix="/api", tags=["tools"])


def tool_repository(request: Request) -> DeploymentToolRepository:
    return cast(DeploymentToolRepository, request.app.state.deployment_tool_repository)


def tool_registry(request: Request) -> ToolRegistry:
    return cast(ToolRegistry, request.app.state.tool_registry)


def server_runtime_repository(request: Request) -> ServerRuntimeRepository:
    return ServerRuntimeRepository(request.app.state.database)


@router.get("/tools/catalog", response_model=ToolCatalogView)
def list_tool_catalog(
    request: Request,
    user: CurrentUserDependency,
) -> ToolCatalogView:
    del user
    return ToolCatalogView(items=list(tool_registry(request).catalog()))


@router.get(
    "/deployments/{deployment_id}/tools",
    response_model=DeploymentToolProfileView,
)
def get_deployment_tools(
    deployment_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> DeploymentToolProfileView:
    enabled = tool_repository(request).get_enabled_tools(deployment_id, user.id)
    if enabled is None:
        raise HTTPException(status_code=404, detail="Deployment not found.")
    return DeploymentToolProfileView(
        deployment_id=deployment_id,
        enabled_tools=enabled,
    )


@router.put(
    "/deployments/{deployment_id}/tools",
    response_model=DeploymentToolProfileView,
)
def update_deployment_tools(
    deployment_id: str,
    payload: DeploymentToolProfileUpdate,
    request: Request,
    user: CurrentUserDependency,
) -> DeploymentToolProfileView:
    try:
        enabled = list(tool_registry(request).validate_ids(payload.enabled_tools))
        saved = tool_repository(request).set_enabled_tools(
            deployment_id=deployment_id,
            owner_id=user.id,
            enabled_tools=enabled,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Deployment not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return DeploymentToolProfileView(
        deployment_id=deployment_id,
        enabled_tools=saved,
    )


@router.get(
    "/discord/server-profiles/{profile_id}/runtime",
    response_model=ServerRuntimeTimezoneView,
)
def get_server_runtime(
    profile_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> ServerRuntimeTimezoneView:
    timezone = server_runtime_repository(request).get_timezone(
        profile_id=profile_id,
        owner_id=user.id,
    )
    if timezone is None:
        raise HTTPException(status_code=404, detail="Discord server profile not found.")
    return ServerRuntimeTimezoneView(profile_id=profile_id, timezone=timezone)


@router.patch(
    "/discord/server-profiles/{profile_id}/runtime",
    response_model=ServerRuntimeTimezoneView,
)
def update_server_runtime(
    profile_id: str,
    payload: ServerRuntimeTimezoneUpdate,
    request: Request,
    user: CurrentUserDependency,
) -> ServerRuntimeTimezoneView:
    try:
        timezone = validate_timezone(payload.timezone)
        record = server_runtime_repository(request).set_timezone(
            profile_id=profile_id,
            owner_id=user.id,
            timezone=timezone,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="Discord server profile not found.")
    return ServerRuntimeTimezoneView(profile_id=profile_id, timezone=record.timezone)
