"""Tool Calling catalog, deployment assignment, Server runtime, and diagnostics."""

import json
from typing import cast
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from echo_masque.api.dependencies import CurrentUserDependency, SuperAdminUserDependency
from echo_masque.api.tool_schemas import (
    DeploymentToolProfileUpdate,
    DeploymentToolProfileView,
    ServerRuntimeTimezoneUpdate,
    ServerRuntimeTimezoneView,
    ToolCatalogView,
    ToolRuntimeTestDeploymentView,
    ToolRuntimeTestExecute,
    ToolRuntimeTestResult,
)
from echo_masque.persistence import AuthRepository, DeploymentToolRepository
from echo_masque.persistence.database import Database
from echo_masque.persistence.deployment_models import (
    CharacterDeploymentRecord,
    DeploymentToolProfileRecord,
)
from echo_masque.persistence.models import CharacterCardRecord
from echo_masque.persistence.server_runtime_repository import ServerRuntimeRepository
from echo_masque.providers import ChatToolCall, ChatToolFunctionCall
from echo_masque.server_time import activate_server_timezone, validate_timezone
from echo_masque.tool_runtime import ToolExecutionContext, ToolRegistry

router = APIRouter(prefix="/api", tags=["tools"])


def tool_repository(request: Request) -> DeploymentToolRepository:
    return cast(DeploymentToolRepository, request.app.state.deployment_tool_repository)


def tool_registry(request: Request) -> ToolRegistry:
    return cast(ToolRegistry, request.app.state.tool_registry)


def database(request: Request) -> Database:
    return cast(Database, request.app.state.database)


def auth_repository(request: Request) -> AuthRepository:
    return cast(AuthRepository, request.app.state.auth_repository)


def server_runtime_repository(request: Request) -> ServerRuntimeRepository:
    return ServerRuntimeRepository(database(request))


def _decode_enabled_tools(value: str) -> list[str]:
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(decoded, list):
        return []
    return list(
        dict.fromkeys(item.strip() for item in decoded if isinstance(item, str) and item.strip())
    )


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


@router.get(
    "/tools/test/deployments",
    response_model=list[ToolRuntimeTestDeploymentView],
)
def list_tool_runtime_test_deployments(
    request: Request,
    user: SuperAdminUserDependency,
) -> list[ToolRuntimeTestDeploymentView]:
    del user
    runtime = server_runtime_repository(request)
    with database(request).session() as session:
        rows = list(
            session.execute(
                select(
                    CharacterDeploymentRecord,
                    CharacterCardRecord.display_name,
                    DeploymentToolProfileRecord.enabled_tools_json,
                )
                .join(
                    CharacterCardRecord,
                    CharacterCardRecord.id == CharacterDeploymentRecord.character_card_id,
                )
                .outerjoin(
                    DeploymentToolProfileRecord,
                    DeploymentToolProfileRecord.deployment_id == CharacterDeploymentRecord.id,
                )
                .order_by(CharacterDeploymentRecord.updated_at.desc())
                .limit(500)
            )
        )

    views: list[ToolRuntimeTestDeploymentView] = []
    for deployment, character_name, enabled_json in rows:
        guild_id = deployment.workspace_id
        timezone = runtime.resolve_timezone(
            owner_id=deployment.owner_id,
            connection_id=deployment.connection_id,
            guild_id=guild_id,
        )
        views.append(
            ToolRuntimeTestDeploymentView(
                deployment_id=deployment.id,
                owner_id=deployment.owner_id,
                character_card_id=deployment.character_card_id,
                character_name=character_name,
                platform=deployment.platform,
                connection_id=deployment.connection_id,
                guild_id=guild_id,
                channel_id=(
                    "" if deployment.channel_id.startswith("@server:") else deployment.channel_id
                ),
                channel_name=deployment.channel_name,
                thread_id=deployment.thread_id,
                thread_name=deployment.thread_name,
                timezone=timezone,
                enabled_tools=_decode_enabled_tools(enabled_json or "[]"),
            )
        )
    return views


@router.post("/tools/test/execute", response_model=ToolRuntimeTestResult)
async def execute_tool_runtime_test(
    payload: ToolRuntimeTestExecute,
    request: Request,
    user: SuperAdminUserDependency,
) -> ToolRuntimeTestResult:
    registry = tool_registry(request)
    catalog_item = next((item for item in registry.catalog() if item.id == payload.tool_id), None)
    if catalog_item is None:
        raise HTTPException(status_code=404, detail="Tool not found in Runtime catalog.")
    if catalog_item.side_effect and not payload.confirm_side_effect:
        raise HTTPException(
            status_code=409,
            detail="This Tool has side effects. Explicit confirmation is required.",
        )

    with database(request).session() as session:
        deployment = session.get(CharacterDeploymentRecord, payload.deployment_id)
        if deployment is None:
            raise HTTPException(status_code=404, detail="Deployment not found.")
        profile = session.get(DeploymentToolProfileRecord, deployment.id)
        enabled_tools = _decode_enabled_tools(profile.enabled_tools_json if profile else "[]")

    if payload.tool_id not in enabled_tools:
        raise HTTPException(
            status_code=409,
            detail="Tool is not enabled on the selected Deployment.",
        )

    guild_id = payload.guild_id.strip() or deployment.workspace_id
    default_channel = "" if deployment.channel_id.startswith("@server:") else deployment.channel_id
    channel_id = payload.channel_id.strip() or default_channel
    thread_id = payload.thread_id.strip() or deployment.thread_id
    if payload.tool_id in {
        "scheduler.remind",
        "discord.search_messages",
        "discord.create_poll",
    } and not channel_id:
        raise HTTPException(
            status_code=422,
            detail="A concrete Discord Channel ID is required for this Tool test.",
        )

    timezone = server_runtime_repository(request).resolve_timezone(
        owner_id=deployment.owner_id,
        connection_id=deployment.connection_id,
        guild_id=guild_id,
    )
    activate_server_timezone(timezone)

    call = ChatToolCall(
        id=f"superadmin-test-{uuid4()}",
        function=ChatToolFunctionCall(
            name=catalog_item.provider_function_name,
            arguments=json.dumps(payload.arguments, ensure_ascii=False),
        ),
    )
    execution = await registry.execute(
        call,
        enabled_tool_ids=tuple(enabled_tools),
        context=ToolExecutionContext(
            owner_id=deployment.owner_id,
            deployment_id=deployment.id,
            character_card_id=deployment.character_card_id,
            platform=deployment.platform,
            connection_id=deployment.connection_id,
            guild_id=guild_id,
            channel_id=channel_id,
            thread_id=thread_id,
            message_id=payload.message_id.strip(),
            trigger_text=payload.trigger_text.strip(),
            initiator_is_bot=False,
            initiator_user_id=payload.initiator_user_id.strip(),
        ),
        allow_side_effect=payload.confirm_side_effect,
    )

    try:
        parsed_result: object = json.loads(execution.content)
    except json.JSONDecodeError:
        parsed_result = execution.content

    auth_repository(request).audit(
        actor_user_id=user.id,
        action="tool_runtime.test_executed",
        resource_type="deployment",
        resource_id=deployment.id,
        metadata={
            "tool_id": payload.tool_id,
            "side_effect": catalog_item.side_effect,
            "status": execution.trace.status,
        },
    )
    return ToolRuntimeTestResult(
        deployment_id=deployment.id,
        tool_id=payload.tool_id,
        provider_function_name=catalog_item.provider_function_name,
        side_effect=catalog_item.side_effect,
        status=execution.trace.status,
        duration_ms=execution.trace.duration_ms,
        error=execution.trace.error,
        timezone=timezone,
        result=parsed_result,
        raw_content=execution.content,
    )
