from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from echo_masque.deployment_presence_rhythm import DeploymentPresenceRhythmService
from echo_masque.persistence.database import Database
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord
from echo_masque.persistence.deployment_presence_repository import DeploymentPresenceRepository


def as_utc(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)


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

    sleep_at = as_utc(configured.scheduled_sleep_at)
    wake_at = as_utc(configured.scheduled_wake_at)

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


def test_overnight_window_remains_sleeping_after_local_midnight(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'rhythm-overnight.db'}")
    database.initialize()
    seed_deployment(database)
    service = DeploymentPresenceRhythmService(database)

    configured = service.configure(
        owner_id="owner-1",
        deployment_id="deployment-rhythm",
        enabled=True,
        preferred_sleep_start_minute=23 * 60,
        sleep_duration_min_minutes=480,
        sleep_duration_max_minutes=480,
        variation_minutes=0,
        now=datetime(2026, 8, 18, 12, 0, tzinfo=UTC),
    )
    assert configured is not None
    assert configured.schedule_timezone == "Asia/Kuala_Lumpur"
    assert configured.scheduled_sleep_at is not None
    assert configured.scheduled_wake_at is not None
    assert as_utc(configured.scheduled_sleep_at) == datetime(2026, 8, 18, 15, 0, tzinfo=UTC)
    assert as_utc(configured.scheduled_wake_at) == datetime(2026, 8, 18, 23, 0, tzinfo=UTC)

    # 18:00 UTC is 02:00 on Aug 19 in Kuala Lumpur. The active sleep schedule still
    # belongs to Aug 18 and must not be replaced by the next night's schedule.
    reconciled = service.reconcile_deployment(
        owner_id="owner-1",
        deployment_id="deployment-rhythm",
        now=datetime(2026, 8, 18, 18, 0, tzinfo=UTC),
    )
    assert reconciled is not None
    assert reconciled.schedule_local_date == "2026-08-18"
    assert reconciled.next_state == "idle"
    assert reconciled.next_transition_at is not None
    assert as_utc(reconciled.next_transition_at) == datetime(2026, 8, 18, 23, 0, tzinfo=UTC)

    presence = DeploymentPresenceRepository(database).get(
        owner_id="owner-1",
        deployment_id="deployment-rhythm",
    )
    assert presence is not None
    assert presence.state == "sleeping"
    assert presence.expected_end_at is not None
    assert as_utc(presence.expected_end_at) == datetime(2026, 8, 18, 23, 0, tzinfo=UTC)


def test_disabling_rhythm_releases_rhythm_owned_sleep(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'rhythm-disable-active.db'}")
    database.initialize()
    seed_deployment(database)
    service = DeploymentPresenceRhythmService(database)

    service.configure(
        owner_id="owner-1",
        deployment_id="deployment-rhythm",
        enabled=True,
        preferred_sleep_start_minute=23 * 60,
        sleep_duration_min_minutes=480,
        sleep_duration_max_minutes=480,
        variation_minutes=0,
        now=datetime(2026, 8, 18, 12, 0, tzinfo=UTC),
    )
    service.run_once(now=datetime(2026, 8, 18, 16, 0, tzinfo=UTC))

    sleeping = DeploymentPresenceRepository(database).get(
        owner_id="owner-1",
        deployment_id="deployment-rhythm",
    )
    assert sleeping is not None
    assert sleeping.state == "sleeping"
    assert sleeping.source == "rhythm"

    disabled = service.configure(
        owner_id="owner-1",
        deployment_id="deployment-rhythm",
        enabled=False,
        preferred_sleep_start_minute=23 * 60,
        sleep_duration_min_minutes=480,
        sleep_duration_max_minutes=480,
        variation_minutes=0,
        now=datetime(2026, 8, 18, 16, 30, tzinfo=UTC),
    )
    assert disabled is not None
    assert disabled.enabled is False
    assert disabled.next_transition_at is None
    assert disabled.next_state == ""

    awake = DeploymentPresenceRepository(database).get(
        owner_id="owner-1",
        deployment_id="deployment-rhythm",
    )
    assert awake is not None
    assert awake.state == "idle"
    assert awake.source == "rhythm"
    assert awake.reason == "scheduled_rhythm_disabled"


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
