"""Authoring Runtime administration and authenticated AI draft generation."""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, HTTPException, Request, status

from echo_masque.api.dependencies import (
    AdminUserDependency,
    CurrentUserDependency,
    quota_http_exception,
    quota_service,
)
from echo_masque.authoring_generation import (
    AuthoringGenerationRequest,
    AuthoringGenerationResult,
    AuthoringGenerationService,
    AuthoringRuntimeUnavailable,
)
from echo_masque.authoring_runtime import (
    AuthoringCredentialConfigure,
    AuthoringRuntimeConfig,
    AuthoringRuntimeService,
    AuthoringRuntimeStatus,
    AuthoringRuntimeView,
)
from echo_masque.credentials import CredentialVaultUnavailable
from echo_masque.providers import ProviderError
from echo_masque.security_controls import QuotaExceeded

router = APIRouter(tags=["authoring"])


def runtime_service(request: Request) -> AuthoringRuntimeService:
    return cast(AuthoringRuntimeService, request.app.state.authoring_runtime_service)


def generation_service(request: Request) -> AuthoringGenerationService:
    return cast(AuthoringGenerationService, request.app.state.authoring_generation_service)


@router.get("/api/authoring/runtime/status", response_model=AuthoringRuntimeStatus)
def authoring_runtime_status(
    request: Request,
    user: CurrentUserDependency,
) -> AuthoringRuntimeStatus:
    return runtime_service(request).status()


@router.get("/api/admin/authoring-runtime", response_model=AuthoringRuntimeView)
def get_authoring_runtime(
    request: Request,
    admin: AdminUserDependency,
) -> AuthoringRuntimeView:
    return runtime_service(request).view()


@router.put("/api/admin/authoring-runtime", response_model=AuthoringRuntimeView)
def update_authoring_runtime(
    payload: AuthoringRuntimeConfig,
    request: Request,
    admin: AdminUserDependency,
) -> AuthoringRuntimeView:
    service = runtime_service(request)
    service.save(payload, actor_user_id=admin.id)
    return service.view()


@router.put(
    "/api/admin/authoring-runtime/credential",
    response_model=AuthoringRuntimeView,
)
def configure_authoring_credential(
    payload: AuthoringCredentialConfigure,
    request: Request,
    admin: AdminUserDependency,
) -> AuthoringRuntimeView:
    service = runtime_service(request)
    try:
        service.set_credential(payload.api_key, actor_user_id=admin.id)
    except CredentialVaultUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    return service.view()


@router.delete(
    "/api/admin/authoring-runtime/credential",
    response_model=AuthoringRuntimeView,
)
def clear_authoring_credential(
    request: Request,
    admin: AdminUserDependency,
) -> AuthoringRuntimeView:
    service = runtime_service(request)
    service.clear_credential(actor_user_id=admin.id)
    return service.view()


@router.post(
    "/api/authoring/generate",
    response_model=AuthoringGenerationResult,
    status_code=status.HTTP_201_CREATED,
)
async def generate_authoring_drafts(
    payload: AuthoringGenerationRequest,
    request: Request,
    user: CurrentUserDependency,
) -> AuthoringGenerationResult:
    try:
        quota_service(request).consume_authoring_generation(user.id)
        return await generation_service(request).generate(user.id, payload)
    except QuotaExceeded as exc:
        raise quota_http_exception(exc) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AuthoringRuntimeUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except ProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
