"""Public runtime status and protected Admin AI configuration endpoints."""

from __future__ import annotations

import hmac
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from echo_masque.admin_runtime import AdminRuntimeConfig, RuntimeStatus
from echo_masque.api.schemas import AdminRuntimeView, RuntimeCredentialConfigure
from echo_masque.config import Settings
from echo_masque.services import RuntimeService

router = APIRouter(tags=["runtime"])


def runtime_service(request: Request) -> RuntimeService:
    return cast(RuntimeService, request.app.state.runtime_service)


def settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def require_admin(
    request: Request,
    token: Annotated[str | None, Header(alias="X-Echo-Admin")] = None,
) -> None:
    resolved = settings(request)
    expected = resolved.admin_token
    if expected is None:
        if resolved.environment in {"development", "test"}:
            expected_value = "local-admin"
        else:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Admin access is disabled until ECHO_MASQUE_ADMIN_TOKEN is configured.",
            )
    else:
        expected_value = expected.get_secret_value()
    if token is None or not hmac.compare_digest(token, expected_value):
        raise HTTPException(status_code=401, detail="Invalid Admin token.")


AdminDependency = Annotated[None, Depends(require_admin)]


@router.get("/api/runtime/status", response_model=RuntimeStatus)
def public_runtime_status(request: Request) -> RuntimeStatus:
    return runtime_service(request).status()


@router.get("/api/admin/runtime", response_model=AdminRuntimeView)
def get_admin_runtime(request: Request, _: AdminDependency) -> AdminRuntimeView:
    service = runtime_service(request)
    return AdminRuntimeView(config=service.config(), status=service.status())


@router.put("/api/admin/runtime", response_model=AdminRuntimeView)
def update_admin_runtime(
    payload: AdminRuntimeConfig,
    request: Request,
    _: AdminDependency,
) -> AdminRuntimeView:
    service = runtime_service(request)
    config = service.save(payload)
    return AdminRuntimeView(config=config, status=service.status())


@router.put(
    "/api/admin/runtime/credentials/{kind}",
    response_model=AdminRuntimeView,
)
def configure_runtime_credential(
    kind: Literal["adaptive", "judge"],
    payload: RuntimeCredentialConfigure,
    request: Request,
    _: AdminDependency,
) -> AdminRuntimeView:
    service = runtime_service(request)
    service.set_credential(kind, payload.api_key)
    return AdminRuntimeView(config=service.config(), status=service.status())


@router.delete(
    "/api/admin/runtime/credentials/{kind}",
    response_model=AdminRuntimeView,
)
def clear_runtime_credential(
    kind: Literal["adaptive", "judge"],
    request: Request,
    _: AdminDependency,
) -> AdminRuntimeView:
    service = runtime_service(request)
    service.clear_credential(kind)
    return AdminRuntimeView(config=service.config(), status=service.status())
