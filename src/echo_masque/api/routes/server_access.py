"""Account and Super Admin endpoints for Discord server access."""

from __future__ import annotations

from datetime import datetime
from typing import cast

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from echo_masque.api.dependencies import (
    CurrentUserDependency,
    SuperAdminUserDependency,
    is_super_admin,
)
from echo_masque.persistence import (
    AuthRepository,
    DeploymentConflict,
    DeploymentRepository,
    ExpressionRepository,
)
from echo_masque.persistence.database import Database
from echo_masque.persistence.deployment_models import DiscordServerCatalogRecord
from echo_masque.persistence.models import UserRecord
from echo_masque.persistence.server_access_models import DiscordServerAccessRecord
from echo_masque.persistence.server_access_repository import ServerAccessRepository

router = APIRouter(prefix="/api", tags=["server-access"])


class JoinServerRequest(BaseModel):
    code: str = Field(min_length=1, max_length=40)


class JoinEnabledUpdate(BaseModel):
    join_enabled: bool


class ServerAccessView(BaseModel):
    connection_id: str
    guild_id: str
    guild_name: str
    profile_id: str | None
    access_source: str
    joined_at: datetime | None


class ServerAccessOverview(BaseModel):
    is_super_admin: bool
    servers: list[ServerAccessView]


class ServerMemberView(BaseModel):
    user_id: str
    display_name: str
    email: str
    access_source: str
    joined_at: datetime


class AdminServerAccessView(BaseModel):
    connection_id: str
    guild_id: str
    guild_name: str
    join_code: str
    join_enabled: bool
    synced_at: datetime
    members: list[ServerMemberView]


def _database(request: Request) -> Database:
    return cast(Database, request.app.state.database)


def _access_repository(request: Request) -> ServerAccessRepository:
    return ServerAccessRepository(_database(request))


def _deployment_repository(request: Request) -> DeploymentRepository:
    return cast(DeploymentRepository, request.app.state.deployment_repository)


def _expression_repository(request: Request) -> ExpressionRepository:
    return cast(ExpressionRepository, request.app.state.expression_repository)


def _auth_repository(request: Request) -> AuthRepository:
    return cast(AuthRepository, request.app.state.auth_repository)


def _super_admin_id(request: Request) -> str:
    email = request.app.state.settings.bootstrap_admin_email
    if email is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Bootstrap Super Admin is not configured.",
        )
    record = _auth_repository(request).get_user_by_email(email.casefold().strip())
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Bootstrap Super Admin is not available.",
        )
    return record.id


def _catalog_for_guild(
    request: Request,
    *,
    guild_id: str,
) -> DiscordServerCatalogRecord:
    owner_id = _super_admin_id(request)
    record = next(
        (
            item
            for item in _deployment_repository(request).list_discord_server_catalog(owner_id)
            if item.guild_id == guild_id
        ),
        None,
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Discord server not found.")
    return record


def _access_view(
    request: Request,
    *,
    access: DiscordServerAccessRecord | None,
    catalog: DiscordServerCatalogRecord,
    user_id: str,
    super_admin: bool = False,
) -> ServerAccessView:
    profile = _access_repository(request).find_profile_for_access(
        user_id=user_id,
        connection_id=catalog.connection_id,
        guild_id=catalog.guild_id,
    )
    access_source = "super_admin" if super_admin else (access.access_source if access else "direct")
    return ServerAccessView(
        connection_id=catalog.connection_id,
        guild_id=catalog.guild_id,
        guild_name=catalog.guild_name,
        profile_id=profile.id if profile is not None else None,
        access_source=access_source,
        joined_at=None if super_admin or access is None else access.created_at,
    )


def _member_view(access: DiscordServerAccessRecord, user: UserRecord) -> ServerMemberView:
    return ServerMemberView(
        user_id=access.user_id,
        display_name=user.display_name,
        email=user.email,
        access_source=access.access_source,
        joined_at=access.created_at,
    )


def _ensure_compatibility_profile(
    request: Request,
    *,
    user_id: str,
    catalog: DiscordServerCatalogRecord,
) -> str:
    profile, created = _access_repository(request).ensure_profile_for_access(
        user_id=user_id,
        catalog=catalog,
    )
    if created:
        _expression_repository(request).clone_server_resources(
            source_owner_id=_super_admin_id(request),
            target_owner_id=user_id,
            connection_id=catalog.connection_id,
            guild_id=catalog.guild_id,
        )
    return profile.id


@router.get("/account/server-access", response_model=ServerAccessOverview)
def account_server_access(
    request: Request,
    user: CurrentUserDependency,
) -> ServerAccessOverview:
    super_admin = is_super_admin(user, request.app.state.settings)
    catalog_owner_id = _super_admin_id(request)
    deployments = _deployment_repository(request)
    access_repo = _access_repository(request)

    if super_admin:
        servers = [
            _access_view(
                request,
                access=None,
                catalog=catalog,
                user_id=user.id,
                super_admin=True,
            )
            for catalog in deployments.list_discord_server_catalog(catalog_owner_id)
        ]
        return ServerAccessOverview(is_super_admin=True, servers=servers)

    access_repo.backfill_access_from_profiles(
        catalog_owner_id=catalog_owner_id,
        user_id=user.id,
    )
    catalogs = {
        (item.connection_id, item.guild_id): item
        for item in deployments.list_discord_server_catalog(catalog_owner_id)
    }
    servers: list[ServerAccessView] = []
    for access in access_repo.list_user_access(user.id):
        catalog = catalogs.get((access.connection_id, access.guild_id))
        if catalog is None:
            continue
        servers.append(
            _access_view(
                request,
                access=access,
                catalog=catalog,
                user_id=user.id,
            )
        )
    servers.sort(key=lambda item: (item.guild_name.casefold(), item.guild_id))
    return ServerAccessOverview(is_super_admin=False, servers=servers)


@router.post("/account/server-access/join", response_model=ServerAccessView)
def join_server(
    payload: JoinServerRequest,
    request: Request,
    user: CurrentUserDependency,
) -> ServerAccessView:
    if is_super_admin(user, request.app.state.settings):
        raise HTTPException(
            status_code=400,
            detail="Super Admin already has access to every server.",
        )

    access_repo = _access_repository(request)
    config = access_repo.get_join_config_by_code(payload.code)
    if config is None:
        raise HTTPException(status_code=404, detail="Server join code is not valid.")
    if not config.join_enabled:
        raise HTTPException(
            status_code=403,
            detail="Joining this server is currently disabled.",
        )

    catalog = access_repo.get_catalog_server(
        catalog_owner_id=_super_admin_id(request),
        connection_id=config.connection_id,
        guild_id=config.guild_id,
    )
    if catalog is None:
        raise HTTPException(status_code=404, detail="Discord server is no longer available.")

    access = access_repo.grant_access(
        user_id=user.id,
        connection_id=catalog.connection_id,
        guild_id=catalog.guild_id,
        source="join_code",
    )
    _ensure_compatibility_profile(request, user_id=user.id, catalog=catalog)
    return _access_view(
        request,
        access=access,
        catalog=catalog,
        user_id=user.id,
    )


@router.get("/admin/server-access/servers", response_model=list[AdminServerAccessView])
def admin_server_access(
    request: Request,
    _: SuperAdminUserDependency,
) -> list[AdminServerAccessView]:
    super_admin_id = _super_admin_id(request)
    deployments = _deployment_repository(request)
    access_repo = _access_repository(request)
    access_repo.backfill_access_from_profiles(catalog_owner_id=super_admin_id)

    result: list[AdminServerAccessView] = []
    for catalog in deployments.list_discord_server_catalog(super_admin_id):
        config = access_repo.ensure_join_config(
            connection_id=catalog.connection_id,
            guild_id=catalog.guild_id,
        )
        members = [
            _member_view(access, member)
            for access, member in access_repo.list_server_members(
                connection_id=catalog.connection_id,
                guild_id=catalog.guild_id,
                exclude_user_id=super_admin_id,
            )
        ]
        result.append(
            AdminServerAccessView(
                connection_id=catalog.connection_id,
                guild_id=catalog.guild_id,
                guild_name=catalog.guild_name,
                join_code=config.join_code,
                join_enabled=config.join_enabled,
                synced_at=catalog.synced_at,
                members=members,
            )
        )
    return result


@router.patch(
    "/admin/server-access/servers/{guild_id}/join",
    response_model=AdminServerAccessView,
)
def update_server_join(
    guild_id: str,
    payload: JoinEnabledUpdate,
    request: Request,
    _: SuperAdminUserDependency,
) -> AdminServerAccessView:
    catalog = _catalog_for_guild(request, guild_id=guild_id)
    access_repo = _access_repository(request)
    access_repo.ensure_join_config(
        connection_id=catalog.connection_id,
        guild_id=catalog.guild_id,
    )
    access_repo.set_join_enabled(
        connection_id=catalog.connection_id,
        guild_id=catalog.guild_id,
        enabled=payload.join_enabled,
    )
    return _admin_server_view(request, catalog=catalog)


@router.post(
    "/admin/server-access/servers/{guild_id}/join-code/regenerate",
    response_model=AdminServerAccessView,
)
def regenerate_server_join_code(
    guild_id: str,
    request: Request,
    _: SuperAdminUserDependency,
) -> AdminServerAccessView:
    catalog = _catalog_for_guild(request, guild_id=guild_id)
    access_repo = _access_repository(request)
    access_repo.ensure_join_config(
        connection_id=catalog.connection_id,
        guild_id=catalog.guild_id,
    )
    access_repo.regenerate_join_code(
        connection_id=catalog.connection_id,
        guild_id=catalog.guild_id,
    )
    return _admin_server_view(request, catalog=catalog)


@router.put(
    "/admin/server-access/servers/{guild_id}/members/{user_id}",
    response_model=AdminServerAccessView,
)
def grant_server_access(
    guild_id: str,
    user_id: str,
    request: Request,
    _: SuperAdminUserDependency,
) -> AdminServerAccessView:
    super_admin_id = _super_admin_id(request)
    if user_id == super_admin_id:
        raise HTTPException(
            status_code=400,
            detail="Super Admin already has global server access.",
        )
    target = _auth_repository(request).get_user(user_id)
    if target is None or not target.is_active:
        raise HTTPException(status_code=404, detail="Active account not found.")

    catalog = _catalog_for_guild(request, guild_id=guild_id)
    access_repo = _access_repository(request)
    access_repo.grant_access(
        user_id=user_id,
        connection_id=catalog.connection_id,
        guild_id=catalog.guild_id,
        source="super_admin",
    )
    _ensure_compatibility_profile(request, user_id=user_id, catalog=catalog)
    return _admin_server_view(request, catalog=catalog)


@router.delete(
    "/admin/server-access/servers/{guild_id}/members/{user_id}",
    response_model=AdminServerAccessView,
)
def revoke_server_access(
    guild_id: str,
    user_id: str,
    request: Request,
    _: SuperAdminUserDependency,
) -> AdminServerAccessView:
    catalog = _catalog_for_guild(request, guild_id=guild_id)
    access_repo = _access_repository(request)
    profile = access_repo.find_profile_for_access(
        user_id=user_id,
        connection_id=catalog.connection_id,
        guild_id=catalog.guild_id,
    )
    if profile is not None:
        try:
            _deployment_repository(request).delete_server_profile(profile.id, user_id)
        except DeploymentConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    access_repo.revoke_access(
        user_id=user_id,
        connection_id=catalog.connection_id,
        guild_id=catalog.guild_id,
    )
    return _admin_server_view(request, catalog=catalog)


def _admin_server_view(
    request: Request,
    *,
    catalog: DiscordServerCatalogRecord,
) -> AdminServerAccessView:
    super_admin_id = _super_admin_id(request)
    access_repo = _access_repository(request)
    config = access_repo.ensure_join_config(
        connection_id=catalog.connection_id,
        guild_id=catalog.guild_id,
    )
    members = [
        _member_view(access, member)
        for access, member in access_repo.list_server_members(
            connection_id=catalog.connection_id,
            guild_id=catalog.guild_id,
            exclude_user_id=super_admin_id,
        )
    ]
    return AdminServerAccessView(
        connection_id=catalog.connection_id,
        guild_id=catalog.guild_id,
        guild_name=catalog.guild_name,
        join_code=config.join_code,
        join_enabled=config.join_enabled,
        synced_at=catalog.synced_at,
        members=members,
    )
