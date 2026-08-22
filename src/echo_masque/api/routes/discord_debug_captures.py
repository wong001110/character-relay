"""Super Admin-only temporary Discord runtime-ingress capture endpoints."""

import math
from typing import cast

from fastapi import APIRouter, HTTPException, Query, Request, Response, status

from echo_masque.api.dependencies import SuperAdminUserDependency
from echo_masque.api.discord_debug_capture_schemas import (
    DiscordDebugCaptureAccessView,
    DiscordDebugCaptureClearResult,
    DiscordDebugCaptureRecordDetail,
    DiscordDebugCaptureRecordPage,
    DiscordDebugCaptureRecordSummary,
    DiscordDebugCaptureSessionCreate,
    DiscordDebugCaptureSessionView,
)
from echo_masque.discord_debug_capture import (
    DiscordDebugCaptureConflict,
    DiscordDebugCaptureStore,
)
from echo_masque.persistence import AuthRepository, DeploymentRepository
from echo_masque.persistence.deployment_models import DiscordServerProfileRecord
from echo_masque.persistence.models import utcnow

router = APIRouter(
    prefix="/api/admin/discord-debug-captures",
    tags=["discord-debug-captures"],
)


def capture_store(request: Request) -> DiscordDebugCaptureStore:
    return cast(DiscordDebugCaptureStore, request.app.state.discord_debug_capture_store)


def deployment_repository(request: Request) -> DeploymentRepository:
    return cast(DeploymentRepository, request.app.state.deployment_repository)


def auth_repository(request: Request) -> AuthRepository:
    return cast(AuthRepository, request.app.state.auth_repository)


def require_owned_discord_profile(
    request: Request,
    *,
    owner_id: str,
    server_profile_id: str,
) -> DiscordServerProfileRecord:
    deployments = deployment_repository(request)
    profile = deployments.get_server_profile(server_profile_id, owner_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Discord server profile not found.")
    connection = deployments.get_connection(profile.connection_id, owner_id)
    if connection is None or connection.platform != "discord":
        raise HTTPException(status_code=404, detail="Discord connection not found.")
    return profile


@router.get("/access", response_model=DiscordDebugCaptureAccessView)
def discord_debug_capture_access(
    user: SuperAdminUserDependency,
) -> DiscordDebugCaptureAccessView:
    del user
    return DiscordDebugCaptureAccessView()


@router.post(
    "/sessions",
    response_model=DiscordDebugCaptureSessionView,
    status_code=status.HTTP_201_CREATED,
)
def start_discord_debug_capture_session(
    payload: DiscordDebugCaptureSessionCreate,
    request: Request,
    user: SuperAdminUserDependency,
) -> DiscordDebugCaptureSessionView:
    profile = require_owned_discord_profile(
        request,
        owner_id=user.id,
        server_profile_id=payload.server_profile_id,
    )
    try:
        session = capture_store(request).start_session(
            owner_id=user.id,
            server_profile_id=profile.id,
            connection_id=profile.connection_id,
            guild_id=profile.guild_id,
            guild_name=profile.guild_name,
            ttl_minutes=payload.ttl_minutes,
        )
    except DiscordDebugCaptureConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    try:
        auth_repository(request).audit(
            actor_user_id=user.id,
            action="discord_debug_capture.started",
            resource_type="discord_debug_capture_session",
            resource_id=session.id,
            metadata={
                "session_id": session.id,
                "server_profile_id": session.server_profile_id,
                "connection_id": session.connection_id,
                "guild_id": session.guild_id,
                "ttl_minutes": payload.ttl_minutes,
            },
        )
    except Exception:
        capture_store(request).discard_session(session.id, owner_id=user.id)
        raise
    return DiscordDebugCaptureSessionView.from_capture(session, now=utcnow())


@router.get(
    "/sessions/current",
    response_model=DiscordDebugCaptureSessionView | None,
)
def get_current_discord_debug_capture_session(
    request: Request,
    user: SuperAdminUserDependency,
    server_profile_id: str = Query(min_length=1, max_length=64),
) -> DiscordDebugCaptureSessionView | None:
    require_owned_discord_profile(
        request,
        owner_id=user.id,
        server_profile_id=server_profile_id,
    )
    session = capture_store(request).current_session(
        owner_id=user.id,
        server_profile_id=server_profile_id,
    )
    if session is None:
        return None
    return DiscordDebugCaptureSessionView.from_capture(session, now=utcnow())


@router.post(
    "/sessions/{session_id}/stop",
    response_model=DiscordDebugCaptureSessionView,
)
def stop_discord_debug_capture_session(
    session_id: str,
    request: Request,
    user: SuperAdminUserDependency,
) -> DiscordDebugCaptureSessionView:
    store = capture_store(request)
    clean_session_id = session_id.strip()
    session = store.get_session(clean_session_id, owner_id=user.id)
    if session is None:
        raise HTTPException(status_code=404, detail="Discord debug capture session not found.")
    auth_repository(request).audit(
        actor_user_id=user.id,
        action="discord_debug_capture.stopped",
        resource_type="discord_debug_capture_session",
        resource_id=session.id,
        metadata={
            "session_id": session.id,
            "server_profile_id": session.server_profile_id,
            "record_count": session.record_count,
        },
    )
    stopped = store.stop_session(clean_session_id, owner_id=user.id)
    if stopped is None:
        raise HTTPException(status_code=404, detail="Discord debug capture session not found.")
    return DiscordDebugCaptureSessionView.from_capture(stopped, now=utcnow())


@router.get(
    "/sessions/{session_id}/records/page",
    response_model=DiscordDebugCaptureRecordPage,
)
def paginate_discord_debug_capture_records(
    session_id: str,
    request: Request,
    user: SuperAdminUserDependency,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
) -> DiscordDebugCaptureRecordPage:
    try:
        records, total = capture_store(request).list_records(
            session_id.strip(),
            owner_id=user.id,
            page=page,
            page_size=page_size,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail="Discord debug capture session not found.",
        ) from exc
    pages = max(1, math.ceil(total / page_size))
    return DiscordDebugCaptureRecordPage(
        items=[DiscordDebugCaptureRecordSummary.from_capture(item) for item in records],
        page=min(page, pages),
        page_size=page_size,
        total=total,
        pages=pages,
    )


@router.get(
    "/records/{record_id}",
    response_model=DiscordDebugCaptureRecordDetail,
)
def get_discord_debug_capture_record(
    record_id: str,
    request: Request,
    response: Response,
    user: SuperAdminUserDependency,
) -> DiscordDebugCaptureRecordDetail:
    store = capture_store(request)
    record = store.get_record(record_id.strip(), owner_id=user.id)
    if record is None:
        raise HTTPException(status_code=404, detail="Discord debug capture record not found.")
    auth_repository(request).audit(
        actor_user_id=user.id,
        action="discord_debug_capture.record_viewed",
        resource_type="discord_debug_capture_record",
        resource_id=record.id,
        metadata={"session_id": record.session_id, "record_id": record.id},
    )
    payload = store.codec.decode(record.encoded_payload)
    response.headers["Cache-Control"] = "no-store"
    return DiscordDebugCaptureRecordDetail(
        **DiscordDebugCaptureRecordSummary.from_capture(record).model_dump(),
        payload=payload,
    )


@router.delete(
    "/sessions/{session_id}/records",
    response_model=DiscordDebugCaptureClearResult,
)
def clear_discord_debug_capture_records(
    session_id: str,
    request: Request,
    user: SuperAdminUserDependency,
) -> DiscordDebugCaptureClearResult:
    store = capture_store(request)
    clean_session_id = session_id.strip()
    try:
        _, record_count = store.list_records(
            clean_session_id,
            owner_id=user.id,
            page=1,
            page_size=1,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail="Discord debug capture session not found.",
        ) from exc
    auth_repository(request).audit(
        actor_user_id=user.id,
        action="discord_debug_capture.records_cleared",
        resource_type="discord_debug_capture_session",
        resource_id=clean_session_id,
        metadata={"session_id": clean_session_id, "deleted_count": record_count},
    )
    deleted = store.clear_records(clean_session_id, owner_id=user.id)
    if deleted is None:
        raise HTTPException(status_code=404, detail="Discord debug capture session not found.")
    return DiscordDebugCaptureClearResult(deleted_count=deleted)


__all__ = ["router"]
