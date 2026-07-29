"""Production storage inspection and fail-closed persistence validation."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from sqlalchemy.engine import make_url

from echo_masque.config import Settings

MountChecker = Callable[[Path], bool]
DATA_MOUNT = Path("/data")


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

    def with_instance_id(self, instance_id: str) -> "StorageStatus":
        return replace(self, storage_instance_id=instance_id)


def inspect_storage(
    settings: Settings,
    *,
    mount_checker: MountChecker | None = None,
) -> StorageStatus:
    """Inspect storage and reject unsafe production SQLite before opening the database."""

    parsed = make_url(settings.database_url)
    database_kind = parsed.get_backend_name()
    database_path = _database_path(parsed.database)
    persistent_required = settings.environment == "production" and database_kind == "sqlite"

    if not persistent_required:
        return StorageStatus(
            database_kind=database_kind,
            database_path=str(database_path) if database_path is not None else None,
            persistent_required=False,
            mount_path=None,
            mount_ready=True,
        )

    if database_path is None:
        raise UnsafeProductionStorageError(
            "Unsafe production storage: SQLite must use an absolute file under /data."
        )
    if not database_path.is_relative_to(DATA_MOUNT):
        raise UnsafeProductionStorageError(
            "Unsafe production storage: SQLite database path must be under /data; "
            f"resolved path is {database_path}."
        )

    checker = mount_checker or _default_mount_checker
    mount_ready = checker(DATA_MOUNT)
    if not mount_ready:
        raise UnsafeProductionStorageError(
            "Unsafe production storage: /data exists but is not a mounted persistent volume. "
            "Attach the Railway Volume to the active Production environment and mount it at /data."
        )

    return StorageStatus(
        database_kind=database_kind,
        database_path=str(database_path),
        persistent_required=True,
        mount_path=str(DATA_MOUNT),
        mount_ready=True,
    )


def _database_path(value: str | None) -> Path | None:
    if value in {None, "", ":memory:"}:
        return None
    return Path(value).expanduser().resolve()


def _default_mount_checker(path: Path) -> bool:
    """Require a dedicated filesystem mount, not the image-local /data directory."""

    return os.path.ismount(path)
