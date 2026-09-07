"""Defensive import authorization contracts using local synthetic records only."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from echo_masque.persistence import Database
from echo_masque.persistence.models import (
    Base,
    CharacterCardRecord,
    CharacterTrialRecord,
    CustomScenarioRecord,
    RunSnapshotRecord,
    TargetRecord,
    TrialRunRecord,
    TurnRecord,
)
from echo_masque.persistence.models import TestPackItemRecord as PackItemRecord
from echo_masque.persistence.models import TestPackRecord as PackRecord
from echo_masque.persistence.workspace_repository import WorkspaceRepository
from echo_masque.workspace import WorkspaceArchive


@pytest.fixture
def repository(tmp_path: Path) -> WorkspaceRepository:
    database = Database(f"sqlite:///{tmp_path / 'import-authorization.db'}")
    Base.metadata.create_all(database.engine)
    with database.session() as session:
        for owner in ("alice", "bob"):
            session.add(TargetRecord(id=f"{owner}-target", name=owner, target_kind="stable"))
            session.flush()
            session.add_all([
                CharacterCardRecord(
                    id=f"{owner}-card", owner_id=owner,
                    target_id=f"{owner}-target", display_name=owner,
                ),
                CustomScenarioRecord(
                    id=f"{owner}-scenario", owner_id=owner, name=owner,
                    category="identity_integrity", language="en", expected_behavior="Stay in role",
                ),
                PackRecord(id=f"{owner}-pack", owner_id=owner, name=owner),
                TrialRunRecord(
                    id=f"{owner}-run", target_id=f"{owner}-target",
                    status="completed", suite_json="[]",
                ),
            ])
            session.flush()
            session.add_all([
                RunSnapshotRecord(
                    run_id=f"{owner}-run", owner_id=owner,
                    character_card_id=f"{owner}-card", test_pack_id=f"{owner}-pack",
                ),
                CharacterTrialRecord(run_id=f"{owner}-run", character_card_id=f"{owner}-card"),
                PackItemRecord(
                    pack_id=f"{owner}-pack", scenario_id=f"{owner}-scenario", position=0,
                ),
                TurnRecord(
                    run_id=f"{owner}-run", scenario_id=f"{owner}-scenario",
                    turn_index=0, tester_message="Hello", target_response="Hello",
                ),
            ])
        session.commit()
    yield WorkspaceRepository(database)
    database.engine.dispose()


def empty_archive(**rows: object) -> WorkspaceArchive:
    return WorkspaceArchive.model_validate({
        "exported_at": datetime.now(UTC), "owner_id": "alice",
        **{key: [] for key in (
            "targets", "character_cards", "scenarios", "test_packs", "trial_runs",
            "character_trials", "run_snapshots", "turns", "events", "evidence",
        )},
        **rows,
    })


@pytest.mark.parametrize("mode", ["merge", "replace"])
@pytest.mark.parametrize("rows", [
    {"targets": [{"id": "bob-target"}]},
    {"scenarios": [{"id": "bob-scenario"}]},
    {"test_packs": [{"id": "bob-pack"}]},
    {"character_cards": [{"id": "new-card", "target_id": "bob-target"}]},
    {"character_cards": [{"id": "bob-card", "target_id": "alice-target"}]},
    {"test_packs": [{"id": "new-pack", "items": [
        {"pack_id": "new-pack", "scenario_id": "bob-scenario"},
    ]}]},
    {"test_packs": [{"id": "new-pack", "items": [
        {"pack_id": "bob-pack", "scenario_id": "alice-scenario"},
    ]}]},
    {"turns": [{"run_id": "bob-run"}]},
    {"events": [{"run_id": "bob-run"}]},
    {"evidence": [{"run_id": "bob-run"}]},
    {"character_trials": [{"run_id": "alice-run", "character_card_id": "bob-card"}]},
    {"run_snapshots": [{"run_id": "bob-run", "owner_id": "alice"}]},
    {"run_snapshots": [{"run_id": "alice-run", "character_card_id": "bob-card"}]},
    {"run_snapshots": [{"run_id": "alice-run", "test_pack_id": "bob-pack"}]},
    {"run_snapshots": [{"run_id": "alice-run", "rerun_of": "bob-run"}]},
    {"trial_runs": [{"id": "new-run", "target_id": "alice-target"}]},
    {"targets": [{"id": "demo-new", "target_kind": "stable"}]},
])
def test_import_rejects_unavailable_graph_before_changes(
    repository: WorkspaceRepository, mode: str, rows: dict[str, object],
) -> None:
    before_alice = repository.export_workspace("alice")
    before_bob = repository.export_workspace("bob")
    with pytest.raises(ValueError):
        repository.import_workspace("alice", empty_archive(**rows), mode)
    for owner, before in (("alice", before_alice), ("bob", before_bob)):
        assert repository.export_workspace(owner).model_dump(exclude={"exported_at"}) == (
            before.model_dump(exclude={"exported_at"})
        )


@pytest.mark.parametrize("mode", ["merge", "replace"])
def test_own_archive_roundtrip_preserves_records(
    repository: WorkspaceRepository, mode: str,
) -> None:
    original = repository.export_workspace("alice")
    repository.import_workspace("alice", original, mode)
    restored = repository.export_workspace("alice")
    assert restored.character_cards == original.character_cards
    assert restored.run_snapshots == original.run_snapshots
    assert len(restored.test_packs[0]["items"]) == 1
    assert len(restored.turns) == 1


def test_valid_new_graph_and_owner_existing_references_are_accepted(
    repository: WorkspaceRepository,
) -> None:
    archive = empty_archive(
        character_cards=[{
            "id": "new-card", "target_id": "alice-target", "display_name": "New",
        }],
        trial_runs=[{
            "id": "new-run", "target_id": "alice-target", "status": "completed", "suite_json": "[]",
        }],
        run_snapshots=[{"run_id": "new-run", "character_card_id": "new-card"}],
    )
    result = repository.import_workspace("alice", archive, "merge")
    assert result.imported["trial_runs"] == 1
    assert repository.get_run_snapshot("new-run", "alice") is not None


def test_replace_requires_references_to_records_that_survive(
    repository: WorkspaceRepository,
) -> None:
    archive = empty_archive(run_snapshots=[{"run_id": "alice-run"}])
    with pytest.raises(ValueError, match="retained graph"):
        repository.import_workspace("alice", archive, "replace")
    assert repository.get_run_snapshot("alice-run", "alice") is not None


def test_foreign_child_identity_cannot_be_reused_for_own_parent(
    repository: WorkspaceRepository,
) -> None:
    foreign_turn = repository.export_workspace("bob").turns[0]
    archive = empty_archive(turns=[{**foreign_turn, "run_id": "alice-run"}])
    with pytest.raises(ValueError, match="unavailable record"):
        repository.import_workspace("alice", archive, "merge")


def test_archive_restores_complete_new_graph_in_empty_database(
    repository: WorkspaceRepository, tmp_path: Path,
) -> None:
    archive = repository.export_workspace("alice")
    database = Database(f"sqlite:///{tmp_path / 'restored.db'}")
    Base.metadata.create_all(database.engine)
    try:
        restored = WorkspaceRepository(database)
        restored.import_workspace("alice", archive, "merge")
        assert restored.get_run_snapshot("alice-run", "alice") is not None
        assert restored.export_workspace("alice").character_cards == archive.character_cards
    finally:
        database.engine.dispose()
