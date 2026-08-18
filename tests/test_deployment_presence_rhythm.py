from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from echo_masque.deployment_presence_rhythm import DeploymentPresenceRhythmService
from echo_masque.persistence.database import Database
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord
from echo_masque.persistence.deployment_presence_repository import DeploymentPresenceRepository


def seed_deployment(database: Database, *, deployment_id: str = "deployment-rhythm") -> None:
    with database.session() as session:
        session.add(
            CharacterDeploymentRecord(
                id=deployment_id,
                owner_id="owner-1",
                character_card_id=f"character-{uuid4()}",
                connection_id="connection-1",
                platform="discord",
                workspace_id="guild-1",
                workspace_name="Guild One",
                channel_id="@server:guild-1",
                channel_name="All channels",
                thread_id="",
                thread_name="",
                participation_mode="smart",
                memory_scope="server_shared",
                version_label="Current",
                sticker_count=0,
                status="active",
            )
        )
        session.commit()


def test_rhythm_schedule_is_persisted_and_deterministic_across_service_restart(
    tmp_path: Path,
) -> None:
    database = Database(f"sqlite:///{tmp_path / 'rhythm-stable.db'}")
    database.initialize()
    seed_deployment(database)
    now = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)

    first_service = DeploymentPresenceRhythmService(database)
    configured = first_service.configure(
        owner_id="owner-1",
        deployment_id="deployment-rhythm",
        enabled=True,
        preferred_sleep_start_minute=60,
        sleep_duration_min_minutes=420,
        sleep_duration_max_minutes=540,
        variation_minutes=45,
        now=now,
    )
    assert configured is not None
    assert configured.enabled is True
    assert configured.schedule_timezone == "Asia/Kuala_Lumpur"
    assert configured.scheduled_sleep_at is not None
    assert configured.scheduled_wake_at is not None
    original = (
        configured.schedule_local_date,
        configured.schedule_timezone,
        configured.scheduled_sleep_at,
        configured.scheduled_wake_at,
        configured.next_transition_at,
        configured.next_state,
    )

    restarted_service = DeploymentPresenceRhythmService(database)
    restarted = restarted_service.reconcile_deployment(
        owner_id="owner-1",
        deployment_id="deployment-rhythm",
        now=now,
    )
    assert restarted is not None
    assert (
        restarted.schedule_local_date,
        restarted.schedule_timezone,
        restarted.scheduled_sleep_at,
        restarted.scheduled_wake_at,
        restarted.next_transition_at,
        restarted.next_state,
    ) == original


def test_rhythm_enters_sleep_and_wakes_without_any_model_dependency(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'rhythm-transition.db'}")
    database.initialize()
    seed_deployment(database)
    service = DeploymentPresenceRhythmService(database)
    initial = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)
    configured = service.configure(
        owner_id="owner-1",
        deployment_id="deployment-rhythm",
        enabled=True,
        preferred_sleep_start_minute=60,
        sleep_duration_min_minutes=480,
        sleep_duration_max_minutes=480,
        variation_minutes=0,
        now=initial,
    )
    assert configured is not None
    assert configured.scheduled_sleep_at is not None
    assert configured.scheduled_wake_at is not None

    sleep_at = configured.scheduled_sleep_at
    wake_at = configured.scheduled_wake_at
    if sleep_at.tzinfo is None:
        sleep_at = sleep_at.replace(tzinfo=UTC)
    if wake_at.tzinfo is None:
        wake_at = wake_at.replace(tzinfo=UTC)

    service.run_once(now=sleep_at + timedelta(minutes=1))
    sleeping = DeploymentPresenceRepository(database).get(
        owner_id="owner-1",
        deployment_id="deployment-rhythm",
    )
    assert sleeping is not None
    assert sleeping.state == "sleeping"
    assert sleeping.source == "rhythm"
    assert sleeping.reason == "scheduled_sleep_window"

    service.run_once(now=wake_at + timedelta(minutes=1))
    awake = DeploymentPresenceRepository(database).get(
        owner_id="owner-1",
        deployment_id="deployment-rhythm",
    )
    assert awake is not None
    assert awake.state == "idle"
    assert awake.source == "rhythm"
    assert awake.reason == "scheduled_wake"


def test_disabled_rhythm_never_changes_manual_presence(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'rhythm-disabled.db'}")
    database.initialize()
    seed_deployment(database)
    presence = DeploymentPresenceRepository(database)
    presence.set_state(
        owner_id="owner-1",
        deployment_id="deployment-rhythm",
        state="busy",
        source="manual",
        reason="manual test",
        now=datetime(2026, 8, 18, 0, 0, tzinfo=UTC),
    )
    service = DeploymentPresenceRhythmService(database)
    service.configure(
        owner_id="owner-1",
        deployment_id="deployment-rhythm",
        enabled=False,
        preferred_sleep_start_minute=60,
        sleep_duration_min_minutes=480,
        sleep_duration_max_minutes=480,
        variation_minutes=0,
        now=datetime(2026, 8, 18, 0, 0, tzinfo=UTC),
    )

    assert service.run_once(now=datetime(2026, 8, 19, 0, 0, tzinfo=UTC)) == 0
    current = presence.get(owner_id="owner-1", deployment_id="deployment-rhythm")
    assert current is not None
    assert current.state == "busy"
    assert current.source == "manual"
