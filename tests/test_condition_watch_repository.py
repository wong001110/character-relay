from datetime import UTC, datetime, timedelta
from pathlib import Path

from echo_masque.persistence import Database
from echo_masque.persistence.condition_watch_repository import ConditionWatchRepository
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord
from echo_masque.persistence.models import CharacterCardRecord, TargetRecord


def seeded_repository(path: Path) -> tuple[Database, ConditionWatchRepository]:
    database = Database(f"sqlite:///{path}")
    # Import the V2 model before schema initialization until persistence exports are wired.
    from echo_masque.persistence.condition_watch_models import ConditionWatchRecord  # noqa: F401

    database.initialize()
    with database.session() as session:
        session.add(
            TargetRecord(
                id="watch-target",
                name="Watch Target",
                target_kind="prompt_model",
            )
        )
        session.add(
            CharacterCardRecord(
                id="watch-character",
                owner_id="owner-a",
                target_id="watch-target",
                display_name="Watch Character",
            )
        )
        session.add(
            CharacterDeploymentRecord(
                id="watch-deployment",
                owner_id="owner-a",
                character_card_id="watch-character",
                connection_id="connection-a",
                platform="discord",
                channel_id="channel-a",
                channel_name="general",
            )
        )
        session.commit()
    return database, ConditionWatchRepository(database)


def test_condition_watch_is_owner_and_deployment_scoped(tmp_path: Path) -> None:
    database, repository = seeded_repository(tmp_path / "watch.db")
    now = datetime.now(UTC)
    created = repository.create(
        owner_id="owner-a",
        deployment_id="watch-deployment",
        condition_text="A release is available",
        notification_text="The release is available.",
        check_interval_seconds=300,
        expires_at=now + timedelta(days=1),
        max_attempts=12,
    )

    assert created.character_card_id == "watch-character"
    assert repository.get(owner_id="owner-a", watch_id=created.id) is not None
    assert repository.get(owner_id="owner-b", watch_id=created.id) is None
    assert [item.id for item in repository.list_for_deployment(
        owner_id="owner-a",
        deployment_id="watch-deployment",
    )] == [created.id]


def test_condition_watch_claim_and_trigger_lifecycle(tmp_path: Path) -> None:
    _, repository = seeded_repository(tmp_path / "watch-lifecycle.db")
    now = datetime.now(UTC)
    created = repository.create(
        owner_id="owner-a",
        deployment_id="watch-deployment",
        condition_text="A result is published",
        notification_text="The result is published.",
        check_interval_seconds=60,
        expires_at=now + timedelta(hours=2),
        max_attempts=3,
        next_check_at=now - timedelta(seconds=1),
    )

    due = repository.claim_due()
    assert [item.id for item in due] == [created.id]
    claimed = repository.get(owner_id="owner-a", watch_id=created.id)
    assert claimed is not None
    assert claimed.attempt_count == 1
    assert claimed.status == "active"
    assert claimed.last_checked_at is not None

    repository.mark_triggered(created.id)
    triggered = repository.get(owner_id="owner-a", watch_id=created.id)
    assert triggered is not None
    assert triggered.status == "triggered"
    assert triggered.triggered_at is not None


def test_condition_watch_cancel_and_delete_owner(tmp_path: Path) -> None:
    _, repository = seeded_repository(tmp_path / "watch-cancel.db")
    now = datetime.now(UTC)
    created = repository.create(
        owner_id="owner-a",
        deployment_id="watch-deployment",
        condition_text="Something changes",
        notification_text="Something changed.",
        check_interval_seconds=600,
        expires_at=now + timedelta(days=1),
        max_attempts=10,
    )

    cancelled = repository.cancel(
        owner_id="owner-a",
        deployment_id="watch-deployment",
        watch_id=created.id,
    )
    assert cancelled is not None
    assert cancelled.status == "cancelled"
    assert repository.delete_owner("owner-a") == 1
    assert repository.get(owner_id="owner-a", watch_id=created.id) is None
