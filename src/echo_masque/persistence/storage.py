"""Production storage inspection and fail-closed persistence validation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from sqlalchemy.engine import make_url

from echo_masque.config import Settings
from echo_masque.persistence.database import normalize_postgresql_driver_url

MountChecker = Callable[[Path], bool]


class UnsafeProductionStorageError(RuntimeError):
    """Raised before startup when production persistence is not actually mounted."""


@dataclass(frozen=True, slots=True)
class StorageStatus:
    """Safe, non-secret storage metadata exposed through application health."""

    database_kind: str
    database_path: str | None
    persistent_required: bool
    mount_path: str | None
    mount_ready: bool
    storage_instance_id: str | None = None

    def with_instance_id(self, instance_id: str) -> StorageStatus:
        return replace(self, storage_instance_id=instance_id)


def _database_path(value: str | None) -> Path | None:
    if value is None or value in {"", ":memory:"}:
        return None
    return Path(value).expanduser().resolve()


def inspect_storage(
    settings: Settings,
    *,
    mount_checker: MountChecker | None = None,
) -> StorageStatus:
    """Inspect storage and reject unsupported production database topologies."""

    del mount_checker
    parsed = make_url(normalize_postgresql_driver_url(settings.database_url))
    database_kind = parsed.get_backend_name()
    database_path = _database_path(parsed.database) if database_kind == "sqlite" else None
    if settings.environment == "production" and database_kind != "postgresql":
        raise UnsafeProductionStorageError(
            "Knowledge Fabric production requires PostgreSQL + pgvector; non-PostgreSQL "
            "databases are limited to development, tests, and an offline migration source."
        )

    return StorageStatus(
        database_kind=database_kind,
        database_path=str(database_path) if database_path is not None else None,
        persistent_required=False,
        mount_path=None,
        mount_ready=True,
    )
