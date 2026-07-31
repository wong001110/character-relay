"""Secret-free Phase 16 authoring archive endpoints."""

from typing import cast

from fastapi import APIRouter, HTTPException, Request

from echo_masque.api.dependencies import CurrentUserDependency
from echo_masque.authoring import (
    AuthoringArchive,
    AuthoringImportRequest,
    AuthoringImportResult,
)
from echo_masque.authoring_archive import AuthoringArchiveService
from echo_masque.persistence import AuthRepository
from echo_masque.persistence.authoring_repository import AuthoringConflict

router = APIRouter(prefix="/api/authoring", tags=["authoring"])


def archive_service(request: Request) -> AuthoringArchiveService:
    return cast(AuthoringArchiveService, request.app.state.authoring_archive_service)


def auth_repository(request: Request) -> AuthRepository:
    return cast(AuthRepository, request.app.state.auth_repository)


@router.get("/archive", response_model=AuthoringArchive)
def export_authoring_archive(
    request: Request,
    user: CurrentUserDependency,
) -> AuthoringArchive:
    archive = archive_service(request).export(user.id)
    auth_repository(request).audit(
        actor_user_id=user.id,
        action="authoring.archive_exported",
        resource_type="authoring_archive",
        resource_id=user.id,
        metadata={
            "scenario_drafts": len(archive.scenario_drafts),
            "test_pack_drafts": len(archive.test_pack_drafts),
        },
    )
    return archive


@router.post("/archive/import", response_model=AuthoringImportResult)
def import_authoring_archive(
    payload: AuthoringImportRequest,
    request: Request,
    user: CurrentUserDependency,
) -> AuthoringImportResult:
    archive = payload.archive.model_copy(update={"owner_id": user.id})
    try:
        result = archive_service(request).import_archive(
            user.id,
            archive,
            payload.mode,
        )
    except AuthoringConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    auth_repository(request).audit(
        actor_user_id=user.id,
        action="authoring.archive_imported",
        resource_type="authoring_archive",
        resource_id=user.id,
        metadata={
            "mode": payload.mode,
            "imported": result.imported,
            "skipped": result.skipped,
        },
    )
    return result
