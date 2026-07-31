"""Owner-scoped calibration Dataset, Case, version, and archive endpoints."""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, HTTPException, Request, status

from echo_masque.api.dependencies import CurrentUserDependency
from echo_masque.calibration import (
    CalibrationArchive,
    CalibrationArchiveImport,
    CalibrationCaseCreate,
    CalibrationCaseUpdate,
    CalibrationCaseView,
    CalibrationDatasetCreate,
    CalibrationDatasetUpdate,
    CalibrationDatasetView,
    CalibrationImportResult,
    CalibrationRunImport,
)
from echo_masque.persistence import AuthRepository, CalibrationRepository
from echo_masque.persistence.calibration_repository import CalibrationConflict

router = APIRouter(prefix="/api/calibration", tags=["calibration"])


def calibration_repository(request: Request) -> CalibrationRepository:
    return cast(CalibrationRepository, request.app.state.calibration_repository)


def auth_repository(request: Request) -> AuthRepository:
    return cast(AuthRepository, request.app.state.auth_repository)


def audit(
    request: Request,
    *,
    actor_user_id: str,
    action: str,
    resource_type: str,
    resource_id: str,
    metadata: dict[str, object] | None = None,
) -> None:
    auth_repository(request).audit(
        actor_user_id=actor_user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        metadata=metadata,
    )


def conflict(exc: CalibrationConflict) -> HTTPException:
    return HTTPException(status_code=409, detail=str(exc))


@router.get("/datasets", response_model=list[CalibrationDatasetView])
def list_datasets(
    request: Request,
    user: CurrentUserDependency,
) -> list[CalibrationDatasetView]:
    return calibration_repository(request).list_datasets(user.id)


@router.post(
    "/datasets",
    response_model=CalibrationDatasetView,
    status_code=status.HTTP_201_CREATED,
)
def create_dataset(
    payload: CalibrationDatasetCreate,
    request: Request,
    user: CurrentUserDependency,
) -> CalibrationDatasetView:
    item = calibration_repository(request).create_dataset(user.id, payload)
    audit(
        request,
        actor_user_id=user.id,
        action="calibration.dataset_created",
        resource_type="calibration_dataset",
        resource_id=item.id,
        metadata={"version": item.version},
    )
    return item


@router.get("/datasets/{dataset_id}", response_model=CalibrationDatasetView)
def get_dataset(
    dataset_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> CalibrationDatasetView:
    item = calibration_repository(request).get_dataset(dataset_id, user.id)
    if item is None:
        raise HTTPException(status_code=404, detail="Calibration Dataset not found.")
    return item


@router.put("/datasets/{dataset_id}", response_model=CalibrationDatasetView)
def update_dataset(
    dataset_id: str,
    payload: CalibrationDatasetUpdate,
    request: Request,
    user: CurrentUserDependency,
) -> CalibrationDatasetView:
    try:
        item = calibration_repository(request).update_dataset(
            dataset_id,
            user.id,
            payload,
        )
    except CalibrationConflict as exc:
        raise conflict(exc) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="Calibration Dataset not found.")
    audit(
        request,
        actor_user_id=user.id,
        action="calibration.dataset_updated",
        resource_type="calibration_dataset",
        resource_id=item.id,
    )
    return item


@router.post(
    "/datasets/{dataset_id}/approve",
    response_model=CalibrationDatasetView,
)
def approve_dataset(
    dataset_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> CalibrationDatasetView:
    try:
        item = calibration_repository(request).approve_dataset(dataset_id, user.id)
    except CalibrationConflict as exc:
        raise conflict(exc) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="Calibration Dataset not found.")
    audit(
        request,
        actor_user_id=user.id,
        action="calibration.dataset_approved",
        resource_type="calibration_dataset",
        resource_id=item.id,
        metadata={"version": item.version, "cases": len(item.cases)},
    )
    return item


@router.post(
    "/datasets/{dataset_id}/archive",
    response_model=CalibrationDatasetView,
)
def archive_dataset(
    dataset_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> CalibrationDatasetView:
    item = calibration_repository(request).archive_dataset(dataset_id, user.id)
    if item is None:
        raise HTTPException(status_code=404, detail="Calibration Dataset not found.")
    audit(
        request,
        actor_user_id=user.id,
        action="calibration.dataset_archived",
        resource_type="calibration_dataset",
        resource_id=item.id,
        metadata={"version": item.version},
    )
    return item


@router.post(
    "/datasets/{dataset_id}/new-version",
    response_model=CalibrationDatasetView,
    status_code=status.HTTP_201_CREATED,
)
def create_next_version(
    dataset_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> CalibrationDatasetView:
    try:
        item = calibration_repository(request).create_next_version(
            dataset_id,
            user.id,
        )
    except CalibrationConflict as exc:
        raise conflict(exc) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="Calibration Dataset not found.")
    audit(
        request,
        actor_user_id=user.id,
        action="calibration.dataset_version_created",
        resource_type="calibration_dataset",
        resource_id=item.id,
        metadata={"version": item.version, "parent_dataset_id": dataset_id},
    )
    return item


@router.delete(
    "/datasets/{dataset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_dataset(
    dataset_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> None:
    try:
        deleted = calibration_repository(request).delete_dataset(dataset_id, user.id)
    except CalibrationConflict as exc:
        raise conflict(exc) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Calibration Dataset not found.")
    audit(
        request,
        actor_user_id=user.id,
        action="calibration.dataset_deleted",
        resource_type="calibration_dataset",
        resource_id=dataset_id,
    )


@router.post(
    "/datasets/{dataset_id}/cases",
    response_model=CalibrationCaseView,
    status_code=status.HTTP_201_CREATED,
)
def create_case(
    dataset_id: str,
    payload: CalibrationCaseCreate,
    request: Request,
    user: CurrentUserDependency,
) -> CalibrationCaseView:
    try:
        item = calibration_repository(request).create_case(
            dataset_id,
            user.id,
            payload,
        )
    except CalibrationConflict as exc:
        raise conflict(exc) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="Calibration Dataset not found.")
    audit(
        request,
        actor_user_id=user.id,
        action="calibration.case_created",
        resource_type="calibration_case",
        resource_id=item.id,
        metadata={"dataset_id": dataset_id, "source": item.source},
    )
    return item


@router.post(
    "/datasets/{dataset_id}/cases/import-run",
    response_model=CalibrationCaseView,
    status_code=status.HTTP_201_CREATED,
)
def import_run_case(
    dataset_id: str,
    payload: CalibrationRunImport,
    request: Request,
    user: CurrentUserDependency,
) -> CalibrationCaseView:
    try:
        item = calibration_repository(request).import_run_case(
            dataset_id,
            user.id,
            payload,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CalibrationConflict as exc:
        raise conflict(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="Calibration Dataset not found.")
    audit(
        request,
        actor_user_id=user.id,
        action="calibration.case_imported",
        resource_type="calibration_case",
        resource_id=item.id,
        metadata={
            "dataset_id": dataset_id,
            "run_id": payload.run_id,
            "scenario_id": payload.scenario_id,
            "turn_index": payload.turn_index,
        },
    )
    return item


@router.put("/cases/{case_id}", response_model=CalibrationCaseView)
def update_case(
    case_id: str,
    payload: CalibrationCaseUpdate,
    request: Request,
    user: CurrentUserDependency,
) -> CalibrationCaseView:
    try:
        item = calibration_repository(request).update_case(case_id, user.id, payload)
    except CalibrationConflict as exc:
        raise conflict(exc) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="Calibration Case not found.")
    audit(
        request,
        actor_user_id=user.id,
        action="calibration.case_updated",
        resource_type="calibration_case",
        resource_id=item.id,
        metadata={"dataset_id": item.dataset_id},
    )
    return item


@router.delete("/cases/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_case(
    case_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> None:
    try:
        deleted = calibration_repository(request).delete_case(case_id, user.id)
    except CalibrationConflict as exc:
        raise conflict(exc) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Calibration Case not found.")
    audit(
        request,
        actor_user_id=user.id,
        action="calibration.case_deleted",
        resource_type="calibration_case",
        resource_id=case_id,
    )


@router.get("/archive", response_model=CalibrationArchive)
def export_archive(
    request: Request,
    user: CurrentUserDependency,
) -> CalibrationArchive:
    archive = calibration_repository(request).export_archive(user.id)
    audit(
        request,
        actor_user_id=user.id,
        action="calibration.archive_exported",
        resource_type="calibration_archive",
        resource_id=user.id,
        metadata={"datasets": len(archive.datasets)},
    )
    return archive


@router.post("/archive/import", response_model=CalibrationImportResult)
def import_archive(
    payload: CalibrationArchiveImport,
    request: Request,
    user: CurrentUserDependency,
) -> CalibrationImportResult:
    archive = payload.archive.model_copy(update={"owner_id": user.id})
    try:
        result = calibration_repository(request).import_archive(
            user.id,
            archive,
            payload.mode,
        )
    except CalibrationConflict as exc:
        raise conflict(exc) from exc
    audit(
        request,
        actor_user_id=user.id,
        action="calibration.archive_imported",
        resource_type="calibration_archive",
        resource_id=user.id,
        metadata={
            "mode": payload.mode,
            "datasets": result.imported.get("datasets", 0),
            "cases": result.imported.get("cases", 0),
        },
    )
    return result
