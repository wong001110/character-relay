import asyncio
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from pydantic import SecretStr

from echo_masque.config import Settings
from echo_masque.deployment_activity import DeploymentBrowsingActivityService
from echo_masque.deployment_discovery_intelligence import (
    DeploymentDiscoverySeeds,
    RankedDiscoveryCandidate,
)
from echo_masque.deployment_discovery_service import DeploymentDiscoveryPreview
from echo_masque.discovery_contracts import DiscoveryCandidate, DiscoveryMode
from echo_masque.persistence.database import Database
from echo_masque.persistence.deployment_activity_repository import DeploymentActivityRepository
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord
from echo_masque.persistence.deployment_presence_repository import DeploymentPresenceRepository
from echo_masque.persistence.discovery_models import DeploymentDiscoveryProfileRecord
from echo_masque.persistence.discovery_repository import DiscoveryRepository


class FakePreviewRunner:
    def __init__(self, database: Database) -> None:
        self.database = database
        self.calls = 0
        self.items = DiscoveryRepository(database)

    async def run(
        self,
        *,
        owner_id: str,
        deployment_id: str,
        region: str = "",
        language: str = "",
        limit: int = 10,
    ) -> DeploymentDiscoveryPreview:
        del region, language
        self.calls += 1
        seeds = DeploymentDiscoverySeeds(
            deployment_id=deployment_id,
            owner_id=owner_id,
            character_card_id="character-1",
            connection_id="connection-1",
            guild_id="guild-a",
            queries=("robotics",),
            semantic_text="robotics",
            seeds=(),
        )
        values = (
            ("robot", "Desktop AI robot", 0.91),
            ("agent", "AI agent workflow", 0.61),
            ("food", "Cooking vlog", 0.20),
        )
        ranked: list[RankedDiscoveryCandidate] = []
        for key, title, score in values[:limit]:
            candidate = DiscoveryCandidate(
                source="youtube",
                canonical_key=f"youtube:{key}",
                content_kind="video",
                title=title,
                description=title,
                creator="Creator",
                url=f"https://www.youtube.com/watch?v={key}",
                published_at=datetime(2026, 8, 18, 8, 0, tzinfo=UTC),
            )
            item = self.items.upsert_item(candidate)
            ranked.append(
                RankedDiscoveryCandidate(
                    discovery_item_id=item.id,
                    candidate=candidate,
                    semantic_relevance=score,
                    sparse_relevance=score,
                    freshness=1.0,
                    novelty=1.0,
                    exploration=0.5,
                    final_score=score,
                    reason="fake_rank",
                )
            )
        return DeploymentDiscoveryPreview(
            deployment_id=deployment_id,
            seeds=seeds,
            ranked=tuple(ranked),
        )


def settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "environment": "test",
        "youtube_data_api_key": SecretStr("test-youtube-key"),
        "discovery_activity_session_probability_percent": 100,
        "discovery_activity_window_start_minute": 600,
        "discovery_activity_window_end_minute": 1200,
        "discovery_activity_duration_min_minutes": 12,
        "discovery_activity_duration_max_minutes": 30,
        "discovery_activity_candidate_budget": 12,
        "discovery_activity_open_budget": 1,
    }
    values.update(overrides)
    return Settings(**values)


def seed_deployment(
    database: Database,
    *,
    deployment_id: str,
    guild_id: str,
) -> None:
    with database.session() as session:
        session.add(
            CharacterDeploymentRecord(
                id=deployment_id,
                owner_id="owner-1",
                character_card_id="character-1",
                connection_id="connection-1",
                platform="discord",
                workspace_id=guild_id,
                workspace_name=guild_id,
                channel_id=f"channel-{guild_id}",
                channel_name="general",
                thread_id="",
                thread_name="",
                participation_mode="smart",
                memory_scope="server_shared",
                version_label="Current",
                sticker_count=0,
                status="active",
            )
        )
        session.add(
            DeploymentDiscoveryProfileRecord(
                deployment_id=deployment_id,
                owner_id="owner-1",
                mode=DiscoveryMode.SHADOW.value,
                youtube_enabled=True,
                bilibili_enabled=False,
            )
        )
        session.commit()


def test_daily_browsing_opportunity_is_stable_for_same_deployment_and_date(
    tmp_path: Path,
) -> None:
    database = Database(f"sqlite:///{tmp_path / 'stable-activity.db'}")
    database.initialize()
    service = DeploymentBrowsingActivityService(
        database,
        settings(),
        preview=FakePreviewRunner(database),
    )

    first = service.materialize_opportunity(
        deployment_id="deployment-a",
        local_date=date(2026, 8, 18),
        timezone="Asia/Kuala_Lumpur",
    )
    second = service.materialize_opportunity(
        deployment_id="deployment-a",
        local_date=date(2026, 8, 18),
        timezone="Asia/Kuala_Lumpur",
    )
    assert first == second
    assert first.should_browse is True
    assert first.scheduled_start_at is not None
    assert first.latest_start_at is not None
    assert 12 <= first.duration_minutes <= 30


def test_sleeping_deployment_does_not_start_scheduled_browsing(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'sleep-block.db'}")
    database.initialize()
    seed_deployment(database, deployment_id="deployment-a", guild_id="guild-a")
    preview = FakePreviewRunner(database)
    service = DeploymentBrowsingActivityService(database, settings(), preview=preview)
    presence = DeploymentPresenceRepository(database)
    activities = DeploymentActivityRepository(database)
    now = datetime(2026, 8, 18, 8, 0, tzinfo=UTC)
    presence.set_state(
        owner_id="owner-1",
        deployment_id="deployment-a",
        state="sleeping",
        source="test",
        now=now,
    )
    activity = activities.create_manual(
        owner_id="owner-1",
        deployment_id="deployment-a",
        platform="youtube",
        planned_duration_minutes=15,
        candidate_budget=10,
        open_budget=2,
        watch_budget=1,
        share_intent_budget=0,
        exploration_percent=20,
        now=now,
    )
    assert activity is not None

    result = asyncio.run(service.run_session(activity, now=now))
    assert result is not None
    assert result.status == "scheduled"
    assert preview.calls == 0
    current = presence.get(owner_id="owner-1", deployment_id="deployment-a")
    assert current is not None and current.state == "sleeping"


def test_manual_shadow_browsing_persists_exposure_and_presence_until_end(
    tmp_path: Path,
) -> None:
    database = Database(f"sqlite:///{tmp_path / 'browsing-session.db'}")
    database.initialize()
    seed_deployment(database, deployment_id="deployment-a", guild_id="guild-a")
    preview = FakePreviewRunner(database)
    service = DeploymentBrowsingActivityService(database, settings(), preview=preview)
    presence = DeploymentPresenceRepository(database)
    discovery = DiscoveryRepository(database)
    activities = DeploymentActivityRepository(database)
    now = datetime(2026, 8, 18, 8, 0, tzinfo=UTC)

    activity = asyncio.run(
        service.run_manual(
            owner_id="owner-1",
            deployment_id="deployment-a",
            duration_minutes=12,
            candidate_budget=3,
            open_budget=1,
            now=now,
        )
    )
    assert activity.status == "active"
    assert activity.candidate_count == 3
    assert activity.open_count == 1
    assert activity.watch_count == 0
    assert activity.engage_count == 0
    assert preview.calls == 1

    current = presence.get(owner_id="owner-1", deployment_id="deployment-a")
    assert current is not None
    assert current.state == "browsing"
    assert current.activity_type == "youtube"
    assert current.reason == f"activity_session:{activity.id}"

    session_items = activities.list_items(owner_id="owner-1", session_id=activity.id)
    assert [item.attention_level for item in session_items] == [
        "open",
        "notice",
        "scroll_past",
    ]
    assert all(item.attention_level not in {"watch", "engage"} for item in session_items)
    exposures = discovery.list_exposures(
        owner_id="owner-1",
        deployment_id="deployment-a",
    )
    assert len(exposures) == 3

    service.reconcile_active_sessions(now=now + timedelta(minutes=13))
    completed = activities.get(owner_id="owner-1", session_id=activity.id)
    assert completed is not None and completed.status == "completed"
    current = presence.get(owner_id="owner-1", deployment_id="deployment-a")
    assert current is not None and current.state == "idle"


def test_sleep_interrupt_cancels_browsing_without_waking_character(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'sleep-interrupt.db'}")
    database.initialize()
    seed_deployment(database, deployment_id="deployment-a", guild_id="guild-a")
    service = DeploymentBrowsingActivityService(
        database,
        settings(),
        preview=FakePreviewRunner(database),
    )
    presence = DeploymentPresenceRepository(database)
    activities = DeploymentActivityRepository(database)
    now = datetime(2026, 8, 18, 8, 0, tzinfo=UTC)

    activity = asyncio.run(
        service.run_manual(
            owner_id="owner-1",
            deployment_id="deployment-a",
            duration_minutes=30,
            now=now,
        )
    )
    assert activity.status == "active"
    presence.set_state(
        owner_id="owner-1",
        deployment_id="deployment-a",
        state="sleeping",
        source="rhythm",
        reason="scheduled_sleep_window",
        now=now + timedelta(minutes=2),
    )

    service.reconcile_active_sessions(now=now + timedelta(minutes=3))
    cancelled = activities.get(owner_id="owner-1", session_id=activity.id)
    assert cancelled is not None and cancelled.status == "cancelled"
    current = presence.get(owner_id="owner-1", deployment_id="deployment-a")
    assert current is not None and current.state == "sleeping"


def test_same_card_other_server_keeps_independent_presence(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'cross-server-activity.db'}")
    database.initialize()
    seed_deployment(database, deployment_id="deployment-a", guild_id="guild-a")
    seed_deployment(database, deployment_id="deployment-b", guild_id="guild-b")
    service = DeploymentBrowsingActivityService(
        database,
        settings(),
        preview=FakePreviewRunner(database),
    )
    presence = DeploymentPresenceRepository(database)
    now = datetime(2026, 8, 18, 8, 0, tzinfo=UTC)

    activity = asyncio.run(
        service.run_manual(
            owner_id="owner-1",
            deployment_id="deployment-a",
            now=now,
        )
    )
    assert activity.status == "active"
    first = presence.get(owner_id="owner-1", deployment_id="deployment-a")
    second = presence.get(owner_id="owner-1", deployment_id="deployment-b")
    assert first is not None and first.state == "browsing"
    assert second is not None and second.state == "idle"
