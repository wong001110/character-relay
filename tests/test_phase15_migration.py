from pathlib import Path

from echo_masque.persistence import Database
from echo_masque.persistence.models import CharacterCardRecord, TargetRecord
from scripts.phase15_migrate import run_migration


def test_phase15_migration_backs_up_and_is_idempotent(tmp_path: Path) -> None:
    database_path = tmp_path / "echo-masque.db"
    url = f"sqlite:///{database_path}"
    database = Database(url)
    database.initialize()
    database.ensure_storage_instance_id()
    with database.session() as session:
        session.add(TargetRecord(id="demo-stable", name="Legacy target", target_kind="stable"))
        session.flush()
        session.add(
            CharacterCardRecord(
                id="legacy-card",
                owner_id="local-user",
                target_id="demo-stable",
                display_name="Legacy Ann",
                subtitle="",
                subject_type="companion",
                persona_summary="",
                traits_json="[]",
                tags_json="[]",
                forbidden_behaviors_json="[]",
                preferred_suites_json="[]",
                portrait_variant="lavender",
            )
        )
        session.commit()

    first = run_migration(url, backup_directory=tmp_path / "backups")
    assert first["backup_path"] is not None
    assert Path(str(first["backup_path"])).exists()

    second = run_migration(url, backup_directory=tmp_path / "backups")
    assert second["storage_instance_id"] == first["storage_instance_id"]
    assert Path(str(second["backup_path"])).exists()

    restarted = Database(url)
    restarted.initialize()
    with restarted.session() as session:
        assert session.get(CharacterCardRecord, "legacy-card") is not None
