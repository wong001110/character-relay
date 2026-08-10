"""Super Admin-only durable Runtime Trace inspection endpoints."""

from typing import Literal, cast

from fastapi import APIRouter, HTTPException, Query, Request

from echo_masque.api.dependencies import SuperAdminUserDependency
from echo_masque.api.runtime_durability_schemas import (
    RuntimeTraceAccessView,
    RuntimeTraceClearResult,
    RuntimeTraceEventView,
    RuntimeTracePage,
    RuntimeTraceSummary,
    RuntimeTraceView,
)
from echo_masque.auth import SYSTEM_RUNTIME_USER_ID
from echo_masque.persistence import AuthRepository, Database, DurableRuntimeRepository
from echo_masque.persistence.models import UserRecord

router = APIRouter(prefix="/api/admin/runtime-traces", tags=["runtime-traces"])


def runtime_repository(request: Request) -> DurableRuntimeRepository:
    return cast(DurableRuntimeRepository, request.app.state.durable_runtime_repository)


def auth_repository(request: Request) -> AuthRepository:
    return cast(AuthRepository, request.app.state.auth_repository)


def database(request: Request) -> Database:
    return cast(Database, request.app.state.database)


def active_owner_filter(request: Request, owner_id: str | None) -> str | None:
    selected = owner_id.strip() if owner_id else ""
    if not selected:
        return None
    with database(request).session() as session:
        user = session.get(UserRecord, selected)
        if user is None or not user.is_active or user.id == SYSTEM_RUNTIME_USER_ID:
            raise HTTPException(status_code=422, detail="Runtime Trace account is unavailable.")
    return selected


@router.get("/access", response_model=RuntimeTraceAccessView)
def runtime_trace_access(user: SuperAdminUserDependency) -> RuntimeTraceAccessView:
    del user
    return RuntimeTraceAccessView()


@router.get("/page", response_model=RuntimeTracePage)
def paginate_runtime_traces(
    request: Request,
    user: SuperAdminUserDependency,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=1000),
    graph_name: Literal["condition_watch", "character_turn", "social_turn"] | None = None,
    status_filter: Literal["running", "completed", "failed"] | None = Query(
        default=None,
        alias="status",
    ),
    operation_id: str | None = Query(default=None, max_length=64),
    owner_id: str | None = Query(default=None, max_length=64),
) -> RuntimeTracePage:
    del user
    try:
        records, next_cursor = runtime_repository(request).list_trace_runs_page(
            limit=limit,
            cursor=cursor,
            graph_name=graph_name,
            status=status_filter,
            operation_id=operation_id.strip() if operation_id else None,
            owner_id=active_owner_filter(request, owner_id),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return RuntimeTracePage(
        items=[RuntimeTraceSummary.from_record(item) for item in records],
        next_cursor=next_cursor,
        has_more=next_cursor is not None,
    )


@router.get("/{graph_run_id}", response_model=RuntimeTraceView)
def get_runtime_trace(
    graph_run_id: str,
    request: Request,
    user: SuperAdminUserDependency,
) -> RuntimeTraceView:
    del user
    record = runtime_repository(request).get_trace_run(graph_run_id.strip())
    if record is None:
        raise HTTPException(status_code=404, detail="Runtime Trace not found.")
    summary = RuntimeTraceSummary.from_record(record)
    events = [
        RuntimeTraceEventView.from_record(item)
        for item in runtime_repository(request).trace_events(record.graph_run_id)
    ]
    return RuntimeTraceView(**summary.model_dump(), events=events)


@router.delete("", response_model=RuntimeTraceClearResult)
def clear_runtime_traces(
    request: Request,
    user: SuperAdminUserDependency,
    owner_id: str | None = Query(default=None, max_length=64),
) -> RuntimeTraceClearResult:
    selected_owner = active_owner_filter(request, owner_id)
    deleted = runtime_repository(request).clear_traces(owner_id=selected_owner)
    auth_repository(request).audit(
        actor_user_id=user.id,
        action="runtime_traces.cleared",
        resource_type="runtime_trace",
        metadata={"deleted_count": deleted, "owner_id": selected_owner},
    )
    return RuntimeTraceClearResult(deleted_count=deleted)
