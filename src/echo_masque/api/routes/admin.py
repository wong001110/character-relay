"""Public runtime status and role-protected Admin AI configuration endpoints."""

from __future__ import annotations

from typing import Literal, cast

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from echo_masque.admin_runtime import AdminRuntimeConfig, RuntimeStatus
from echo_masque.api.dependencies import AdminUserDependency
from echo_masque.api.schemas import AdminRuntimeView, RuntimeCredentialConfigure
from echo_masque.credentials import CredentialVaultUnavailable
from echo_masque.services import RuntimeService

router = APIRouter(tags=["runtime"])


class CredentialRotationView(BaseModel):
    rotated_count: int
    key_version: str


def runtime_service(request: Request) -> RuntimeService:
    return cast(RuntimeService, request.app.state.runtime_service)


def legacy_admin_request(request: Request) -> bool:
    return bool(getattr(request.state, "legacy_admin", False))


@router.get("/api/runtime/status", response_model=RuntimeStatus)
def public_runtime_status(request: Request) -> RuntimeStatus:
    return runtime_service(request).status()


@router.get("/api/admin/runtime", response_model=AdminRuntimeView)
def get_admin_runtime(
    request: Request,
    admin: AdminUserDependency,
) -> AdminRuntimeView:
    service = runtime_service(request)
    return AdminRuntimeView(config=service.config(), status=service.status())


@router.put("/api/admin/runtime", response_model=AdminRuntimeView)
def update_admin_runtime(
    payload: AdminRuntimeConfig,
    request: Request,
    admin: AdminUserDependency,
) -> AdminRuntimeView:
    service = runtime_service(request)
    config = service.save(payload, actor_user_id=admin.id)
    return AdminRuntimeView(config=config, status=service.status())


@router.put(
    "/api/admin/runtime/credentials/{kind}",
    response_model=AdminRuntimeView,
)
def configure_runtime_credential(
    kind: Literal["adaptive", "judge"],
    payload: RuntimeCredentialConfigure,
    request: Request,
    admin: AdminUserDependency,
) -> AdminRuntimeView:
    service = runtime_service(request)
    try:
        service.set_credential(
            kind,
            payload.api_key,
            actor_user_id=admin.id,
            legacy=legacy_admin_request(request),
        )
    except CredentialVaultUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    return AdminRuntimeView(config=service.config(), status=service.status())


@router.delete(
    "/api/admin/runtime/credentials/{kind}",
    response_model=AdminRuntimeView,
)
def clear_runtime_credential(
    kind: Literal["adaptive", "judge"],
    request: Request,
    admin: AdminUserDependency,
) -> AdminRuntimeView:
    service = runtime_service(request)
    service.clear_credential(
        kind,
        actor_user_id=admin.id,
        legacy=legacy_admin_request(request),
    )
    return AdminRuntimeView(config=service.config(), status=service.status())


@router.post(
    "/api/admin/credentials/rotate",
    response_model=CredentialRotationView,
)
def rotate_credential_vault(
    request: Request,
    admin: AdminUserDependency,
) -> CredentialRotationView:
    if legacy_admin_request(request):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credential rotation requires an authenticated Admin session.",
        )
    service = runtime_service(request)
    try:
        rotated = service.rotate_credentials(actor_user_id=admin.id)
    except CredentialVaultUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    return CredentialRotationView(
        rotated_count=rotated,
        key_version=service.credential_vault.primary_version,
    )
