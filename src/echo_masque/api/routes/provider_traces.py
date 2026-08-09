"""Super Admin-only provider trace inspection endpoints."""

from typing import Literal, cast

from fastapi import APIRouter, HTTPException, Query, Request

from echo_masque.api.dependencies import SuperAdminUserDependency
from echo_masque.api.provider_trace_schemas import (
    ProviderTraceAccessView,
    ProviderTraceClearResult,
    ProviderTracePage,
    ProviderTraceSummary,
    ProviderTraceView,
)
from echo_masque.persistence import AuthRepository, ProviderTraceRepository
from echo_masque.provider_trace_classification import ProviderTraceCategory

router = APIRouter(prefix="/api/admin/provider-traces", tags=["provider-traces"])


def trace_repository(request: Request) -> ProviderTraceRepository:
    return cast(ProviderTraceRepository, request.app.state.provider_trace_repository)


def auth_repository(request: Request) -> AuthRepository:
    return cast(AuthRepository, request.app.state.auth_repository)


@router.get("/access", response_model=ProviderTraceAccessView)
def provider_trace_access(user: SuperAdminUserDependency) -> ProviderTraceAccessView:
    del user
    return ProviderTraceAccessView()


@router.get("", response_model=list[ProviderTraceView])
def list_provider_traces(
    request: Request,
    user: SuperAdminUserDependency,
    limit: int = Query(default=100, ge=1, le=200),
    status_filter: Literal["pending", "succeeded", "error"] | None = Query(
        default=None,
        alias="status",
    ),
    category: ProviderTraceCategory | None = None,
    owner_id: str | None = Query(default=None, max_length=64),
    model: str | None = Query(default=None, max_length=200),
    trace_id: str | None = Query(default=None, max_length=64),
) -> list[ProviderTraceView]:
    del user
    records = trace_repository(request).list_traces(
        limit=limit,
        status=status_filter,
        category=category,
        owner_id=owner_id.strip() if owner_id else None,
        model=model.strip() if model else None,
        trace_id=trace_id.strip() if trace_id else None,
    )
    return [ProviderTraceView.from_record(item) for item in records]


@router.get("/page", response_model=ProviderTracePage)
def paginate_provider_traces(
    request: Request,
    user: SuperAdminUserDependency,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=1000),
    status_filter: Literal["pending", "succeeded", "error"] | None = Query(
        default=None,
        alias="status",
    ),
    category: ProviderTraceCategory | None = None,
    owner_id: str | None = Query(default=None, max_length=64),
    model: str | None = Query(default=None, max_length=200),
    trace_id: str | None = Query(default=None, max_length=64),
) -> ProviderTracePage:
    del user
    try:
        records, next_cursor = trace_repository(request).list_traces_page(
            limit=limit,
            cursor=cursor,
            status=status_filter,
            category=category,
            owner_id=owner_id.strip() if owner_id else None,
            model=model.strip() if model else None,
            trace_id=trace_id.strip() if trace_id else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ProviderTracePage(
        items=[ProviderTraceSummary.from_record(item) for item in records],
        next_cursor=next_cursor,
        has_more=next_cursor is not None,
    )


@router.delete("", response_model=ProviderTraceClearResult)
def clear_provider_traces(
    request: Request,
    user: SuperAdminUserDependency,
    owner_id: str | None = Query(default=None, max_length=64),
) -> ProviderTraceClearResult:
    selected_owner = owner_id.strip() if owner_id else None
    deleted = trace_repository(request).clear(owner_id=selected_owner)
    auth_repository(request).audit(
        actor_user_id=user.id,
        action="provider_traces.cleared",
        resource_type="provider_trace",
        metadata={"deleted_count": deleted, "owner_id": selected_owner},
    )
    return ProviderTraceClearResult(deleted_count=deleted)


@router.get("/{trace_id}", response_model=ProviderTraceView)
def get_provider_trace(
    trace_id: str,
    request: Request,
    user: SuperAdminUserDependency,
) -> ProviderTraceView:
    del user
    record = trace_repository(request).get_trace(trace_id.strip())
    if record is None:
        raise HTTPException(status_code=404, detail="Provider Trace not found.")
    return ProviderTraceView.from_record(record)
