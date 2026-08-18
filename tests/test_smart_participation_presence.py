from pathlib import Path

from echo_masque.persistence.database import Database
from echo_masque.persistence.deployment_presence_models import DeploymentPresenceRecord
from echo_masque.smart_participation_durable_state import SmartParticipationDurableStateService


def test_sleeping_deployment_is_hard_blocked_before_smart_participation(
    tmp_path: Path,
) -> None:
    database = Database(f"sqlite:///{tmp_path / 'participation-presence.db'}")
    database.initialize()
    with database.session() as session:
        session.add(
            DeploymentPresenceRecord(
                deployment_id="deployment-sleeping",
                owner_id="owner-1",
                state="sleeping",
                source="test",
            )
        )
        session.add(
            DeploymentPresenceRecord(
                deployment_id="deployment-browsing",
                owner_id="owner-1",
                state="browsing",
                activity_type="youtube",
                source="test",
            )
        )
        session.commit()

    result = SmartParticipationDurableStateService(database).preflight(
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="channel-1",
        thread_id="",
        candidate_cooldowns={
            "deployment-sleeping": 0,
            "deployment-browsing": 0,
            "deployment-default-idle": 0,
        },
        channel_cooldown_seconds=0,
        window_seconds=600,
        max_replies_per_window=10,
    )

    assert result.channel_blocked is False
    assert result.rate_limited is False
    assert result.blocked_deployment_ids == frozenset({"deployment-sleeping"})


def test_sleeping_presence_block_is_independent_of_participation_cooldown(
    tmp_path: Path,
) -> None:
    database = Database(f"sqlite:///{tmp_path / 'participation-sleep-no-cooldown.db'}")
    database.initialize()
    with database.session() as session:
        session.add(
            DeploymentPresenceRecord(
                deployment_id="deployment-sleeping",
                owner_id="owner-1",
                state="sleeping",
                source="test",
            )
        )
        session.commit()

    result = SmartParticipationDurableStateService(database).preflight(
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="channel-1",
        thread_id="",
        candidate_cooldowns={"deployment-sleeping": 0},
        channel_cooldown_seconds=0,
        window_seconds=600,
        max_replies_per_window=10,
    )

    assert "deployment-sleeping" in result.blocked_deployment_ids
