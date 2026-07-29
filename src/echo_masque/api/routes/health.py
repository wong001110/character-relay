"""Service health endpoints."""

from typing import cast

from fastapi import APIRouter, Request
from pydantic import BaseModel

from echo_masque.config import Settings
from echo_masque.persistence import StorageStatus

router = APIRouter(tags=["system"])


class StorageHealthResponse(BaseModel):
    database_kind: str
    database_path: str | None
    persistent_required: bool
    mount_path: str | None
    mount_ready: bool
    storage_instance_id: str


class ServiceHealthResponse(BaseModel):
    name: str
    version: str
    status: str = "ok"
    environment: str
    storage: StorageHealthResponse


@router.get("/health", response_model=ServiceHealthResponse)
def health(request: Request) -> ServiceHealthResponse:
    """Report process and persistence health without touching external providers."""

    settings = cast(Settings, request.app.state.settings)
    storage = cast(StorageStatus, request.app.state.storage_status)
    if storage.storage_instance_id is None:
        raise RuntimeError("Storage identity is unavailable after database initialization.")
    return ServiceHealthResponse(
        name=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        storage=StorageHealthResponse(
            database_kind=storage.database_kind,
            database_path=storage.database_path,
            persistent_required=storage.persistent_required,
            mount_path=storage.mount_path,
            mount_ready=storage.mount_ready,
            storage_instance_id=storage.storage_instance_id,
        ),
    )
