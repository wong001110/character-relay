import pytest

from scripts.railway_smoke import validate_storage_health


def test_production_postgresql_storage_health_is_accepted() -> None:
    assert (
        validate_storage_health(
            {
                "environment": "production",
                "storage": {
                    "database_kind": "postgresql",
                    "database_path": None,
                    "persistent_required": False,
                    "mount_path": None,
                    "mount_ready": True,
                    "storage_instance_id": "storage-1",
                },
            },
            required=True,
        )
        == "storage-1"
    )


def test_production_sqlite_storage_health_is_rejected() -> None:
    with pytest.raises(RuntimeError, match="not PostgreSQL"):
        validate_storage_health(
            {
                "environment": "production",
                "storage": {
                    "database_kind": "sqlite",
                    "database_path": "/data/echo_masque.db",
                    "persistent_required": True,
                    "mount_path": "/data",
                    "mount_ready": True,
                    "storage_instance_id": "storage-1",
                },
            },
            required=True,
        )
