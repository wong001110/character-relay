"""Phase 14 Matrix, analytics, export, and Prompt version endpoints."""

from __future__ import annotations

from typing import cast

from fastapi import (
    APIRouter,
    BackgroundTasks,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)

from echo_masque.api.dependencies import (
    CurrentUserDependency,
    quota_http_exception,
    quota_service,
)
from echo_masque.config import Settings
from echo_masque.matrix import (
    ExportFormat,
    MatrixAnalytics,
    MatrixComparison,
    MatrixCreate,
    MatrixDefinition,
    MatrixLaunch,
    MatrixListPage,
    MatrixPreview,
    MatrixTaskView,
    MatrixUpdate,
    MatrixView,
    PromptVersionDiff,
    PromptVersionView,
)
from echo_masque.persistence import MatrixRepository
from echo_masque.security_controls import QuotaExceeded
from echo_masque.services import MatrixService

router = APIRouter(tags=["matrices"])
ExportFormatQuery = Query("json", alias="format")


def matrix_repository(request: Request) -> MatrixRepository:
    return cast(MatrixRepository, request.app.state.matrix_repository)


def matrix_service(request: Request) -> MatrixService:
    return cast(MatrixService, request.app.state.matrix_service)


def _enforce_matrix_concurrency(request: Request, concurrency: int) -> None:
    resolved = cast(Settings, request.app.state.settings)
    if concurrency > resolved.max_matrix_concurrency_per_user:
        raise quota_http_exception(
            QuotaExceeded(
                "Matrix concurrency exceeds the account limit."
            )
        )


@router.post("/api/matrices/preview", response_model=MatrixPreview)
def preview_matrix(
    definition: MatrixDefinition,
    request: Request,
    user: CurrentUserDependency,
) -> MatrixPreview:
    _enforce_matrix_concurrency(request, definition.concurrency)
    try:
        return matrix_service(request).preview(user.id, definition)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/api/matrices", response_model=MatrixListPage)
def list_matrices(
    request: Request,
    user: CurrentUserDependency,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> MatrixListPage:
    return matrix_repository(request).list_matrices(
        user.id,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/api/matrices",
    response_model=MatrixView,
    status_code=status.HTTP_201_CREATED,
)
def create_matrix(
    payload: MatrixCreate,
    request: Request,
    user: CurrentUserDependency,
) -> MatrixView:
    _enforce_matrix_concurrency(request, payload.definition.concurrency)
    try:
        quota_service(request).enforce_create(user.id, "matrix")
    except QuotaExceeded as exc:
        raise quota_http_exception(exc) from exc
    try:
        return matrix_service(request).create(user.id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/api/matrices/{matrix_id}", response_model=MatrixView)
def get_matrix(
    matrix_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> MatrixView:
    item = matrix_repository(request).get_matrix(matrix_id, user.id)
    if item is None:
        raise HTTPException(status_code=404, detail="Experiment Matrix not found.")
    return item


@router.put("/api/matrices/{matrix_id}", response_model=MatrixView)
def update_matrix(
    matrix_id: str,
    payload: MatrixUpdate,
    request: Request,
    user: CurrentUserDependency,
) -> MatrixView:
    if payload.definition is not None:
        _enforce_matrix_concurrency(request, payload.definition.concurrency)
    try:
        item = matrix_service(request).update(matrix_id, user.id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="Experiment Matrix not found.")
    return item


@router.delete("/api/matrices/{matrix_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_matrix(
    matrix_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> None:
    try:
        deleted = matrix_repository(request).delete_matrix(matrix_id, user.id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Experiment Matrix not found.")


@router.post(
    "/api/matrices/{matrix_id}/launch",
    response_model=MatrixView,
    status_code=status.HTTP_202_ACCEPTED,
)
def launch_matrix(
    matrix_id: str,
    payload: MatrixLaunch,
    request: Request,
    background_tasks: BackgroundTasks,
    user: CurrentUserDependency,
) -> MatrixView:
    try:
        quota_service(request).enforce_matrix_launch(
            user.id,
            payload.confirmed_task_count,
        )
    except QuotaExceeded as exc:
        raise quota_http_exception(exc) from exc
    try:
        matrix = matrix_service(request).launch(matrix_id, user.id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Experiment Matrix not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    background_tasks.add_task(matrix_service(request).run_matrix, matrix.id)
    return matrix


@router.post("/api/matrices/{matrix_id}/pause", response_model=MatrixView)
def pause_matrix(
    matrix_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> MatrixView:
    try:
        item = matrix_service(request).pause(matrix_id, user.id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="Experiment Matrix not found.")
    return item


@router.post("/api/matrices/{matrix_id}/resume", response_model=MatrixView)
def resume_matrix(
    matrix_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    user: CurrentUserDependency,
) -> MatrixView:
    try:
        item = matrix_service(request).resume(matrix_id, user.id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="Experiment Matrix not found.")
    background_tasks.add_task(matrix_service(request).run_matrix, matrix_id)
    return item


@router.post("/api/matrices/{matrix_id}/cancel", response_model=MatrixView)
def cancel_matrix(
    matrix_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> MatrixView:
    item = matrix_service(request).cancel(matrix_id, user.id)
    if item is None:
        raise HTTPException(status_code=404, detail="Experiment Matrix not found.")
    return item


@router.post("/api/matrices/{matrix_id}/retry-failed", response_model=MatrixView)
def retry_failed_tasks(
    matrix_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    user: CurrentUserDependency,
) -> MatrixView:
    item = matrix_service(request).retry_failed(matrix_id, user.id)
    if item is None:
        raise HTTPException(status_code=404, detail="Experiment Matrix not found.")
    background_tasks.add_task(matrix_service(request).run_matrix, matrix_id)
    return item


@router.put("/api/matrices/{matrix_id}/baseline", response_model=MatrixView)
def set_matrix_baseline(
    matrix_id: str,
    value: bool,
    request: Request,
    user: CurrentUserDependency,
) -> MatrixView:
    item = matrix_repository(request).set_matrix_baseline(matrix_id, user.id, value)
    if item is None:
        raise HTTPException(status_code=404, detail="Experiment Matrix not found.")
    return item


@router.get("/api/matrices/{matrix_id}/tasks", response_model=list[MatrixTaskView])
def matrix_tasks(
    matrix_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> list[MatrixTaskView]:
    items = matrix_repository(request).list_tasks(matrix_id, user.id)
    if items is None:
        raise HTTPException(status_code=404, detail="Experiment Matrix not found.")
    return items


@router.get("/api/matrices/{matrix_id}/analytics", response_model=MatrixAnalytics)
def matrix_analytics(
    matrix_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> MatrixAnalytics:
    item = matrix_service(request).analytics(matrix_id, user.id)
    if item is None:
        raise HTTPException(status_code=404, detail="Experiment Matrix not found.")
    return item


@router.get("/api/matrices/compare/result", response_model=MatrixComparison)
def compare_matrices(
    request: Request,
    baseline_id: str,
    candidate_id: str,
    user: CurrentUserDependency,
) -> MatrixComparison:
    item = matrix_service(request).compare(baseline_id, candidate_id, user.id)
    if item is None:
        raise HTTPException(status_code=404, detail="One or both Matrices were not found.")
    return item


@router.get("/api/matrices/{matrix_id}/export")
def export_matrix(
    matrix_id: str,
    request: Request,
    user: CurrentUserDependency,
    export_format: ExportFormat = ExportFormatQuery,
) -> Response:
    exported = matrix_service(request).export(matrix_id, user.id, export_format)
    if exported is None:
        raise HTTPException(status_code=404, detail="Experiment Matrix not found.")
    return Response(
        content=exported.content,
        media_type=exported.media_type,
        headers={"Content-Disposition": f'attachment; filename="{exported.filename}"'},
    )


@router.get(
    "/api/characters/{character_card_id}/prompt-versions",
    response_model=list[PromptVersionView],
)
def list_prompt_versions(
    character_card_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> list[PromptVersionView]:
    items = matrix_repository(request).list_prompt_versions(user.id, character_card_id)
    if items is None:
        raise HTTPException(status_code=404, detail="Character Card not found.")
    return items


@router.post(
    "/api/characters/{character_card_id}/prompt-versions/{version_id}/restore",
    response_model=PromptVersionView,
)
def restore_prompt_version(
    character_card_id: str,
    version_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> PromptVersionView:
    item = matrix_repository(request).restore_prompt_version(
        user.id,
        character_card_id,
        version_id,
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Prompt version not found.")
    return item


@router.put(
    "/api/characters/{character_card_id}/prompt-versions/{version_id}/production",
    response_model=PromptVersionView,
)
def set_production_prompt_version(
    character_card_id: str,
    version_id: str,
    value: bool,
    request: Request,
    user: CurrentUserDependency,
) -> PromptVersionView:
    item = matrix_repository(request).set_production_version(
        user.id,
        character_card_id,
        version_id,
        value,
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Prompt version not found.")
    return item


@router.get(
    "/api/prompt-versions/compare",
    response_model=PromptVersionDiff,
)
def compare_prompt_versions(
    request: Request,
    left_id: str,
    right_id: str,
    user: CurrentUserDependency,
) -> PromptVersionDiff:
    item = matrix_repository(request).prompt_version_diff(user.id, left_id, right_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Comparable Prompt versions not found.")
    return item
