from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from echo_masque.api import create_app
from echo_masque.config import Settings
from echo_masque.persistence import UnsafeProductionStorageError, inspect_storage


def test_non_production_sqlite_does_not_require_a_mount(tmp_path: Path) -> None:
    status = inspect_storage(
        Settings(environment="test", database_url=f"sqlite:///{tmp_path / 'test.db'}")
    )

    assert status.persistent_required is False
    assert status.mount_ready is True
    assert status.mount_path is None


def test_postgresql_storage_health_does_not_disclose_a_local_database_path() -> None:
    status = inspect_storage(
        Settings(
            environment="production",
            database_url="postgresql+psycopg://user:password@example.test:5432/echo_masque",
        )
    )

    assert status.database_kind == "postgresql"
    assert status.database_path is None
    assert status.persistent_required is False
    assert status.mount_ready is True


def test_production_sqlite_must_be_under_data() -> None:
    with pytest.raises(UnsafeProductionStorageError, match="must be under /data"):
        inspect_storage(
            Settings(environment="production", database_url="sqlite:////app/echo_masque.db"),
            mount_checker=lambda _: True,
        )


def test_production_rejects_image_local_data_directory() -> None:
    with pytest.raises(UnsafeProductionStorageError, match="not a mounted persistent volume"):
        inspect_storage(
            Settings(environment="production", database_url="sqlite:////data/echo_masque.db"),
            mount_checker=lambda _: False,
        )


def test_production_accepts_a_real_data_mount() -> None:
    status = inspect_storage(
        Settings(environment="production", database_url="sqlite:////data/echo_masque.db"),
        mount_checker=lambda path: path == Path("/data"),
    )

    assert status.database_path == "/data/echo_masque.db"
    assert status.persistent_required is True
    assert status.mount_path == "/data"
    assert status.mount_ready is True


def test_health_storage_identity_survives_application_restart(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'identity.db'}"
    settings = Settings(environment="test", database_url=database_url)

    first = TestClient(create_app(settings)).get("/health")
    second = TestClient(create_app(settings)).get("/health")

    assert first.status_code == 200
    assert second.status_code == 200
    first_storage = first.json()["storage"]
    second_storage = second.json()["storage"]
    assert first_storage["storage_instance_id"] == second_storage["storage_instance_id"]
    assert first_storage["database_path"] == str((tmp_path / "identity.db").resolve())
    assert first_storage["mount_ready"] is True
