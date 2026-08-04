"""Super Admin-only provider trace inspection endpoints."""

from typing import Literal, cast

from fastapi import APIRouter, Query, Request

from echo_masque.api.dependencies import SuperAdminUserDependency
from echo_masque.api.provider_trace_schemas import (
    ProviderTraceClearResult,
    ProviderTraceView,
)
from echo_masque.persistence import AuthRepository, ProviderTraceRepository

router = APIRouter(prefix="/api/admin/provider-traces", tags=["provider-traces"])


def trace_repository(request: Request) -> ProviderTraceRepository:
    return cast(ProviderTraceRepository, request.app.state.provider_trace_repository)


def auth_repository(request: Request) -> AuthRepository:
    return cast(AuthRepository, request.app.state.auth_repository)


@router.get("", response_model=list[ProviderTraceView])
def list_provider_traces(
    request: Request,
    user: SuperAdminUserDependency,
    limit: int = Query(default=100, ge=1, le=200),
    status_filter: Literal["pending", "succeeded", "error"] | None = Query(
        default=None,
        alias="status",
    ),
    model: str | None = Query(default=None, max_length=200),
    trace_id: str | None = Query(default=None, max_length=64),
) -> list[ProviderTraceView]:
    del user
    records = trace_repository(request).list_traces(
        limit=limit,
        status=status_filter,
        model=model.strip() if model else None,
        trace_id=trace_id.strip() if trace_id else None,
    )
    return [ProviderTraceView.from_record(item) for item in records]


@router.delete("", response_model=ProviderTraceClearResult)
def clear_provider_traces(
    request: Request,
    user: SuperAdminUserDependency,
) -> ProviderTraceClearResult:
    deleted = trace_repository(request).clear()
    auth_repository(request).audit(
        actor_user_id=user.id,
        action="provider_traces.cleared",
        resource_type="provider_trace",
        metadata={"deleted_count": deleted},
    )
    return ProviderTraceClearResult(deleted_count=deleted)
