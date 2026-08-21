import asyncio
from datetime import UTC, datetime
from pathlib import Path

from pydantic import SecretStr

from echo_masque.config import Settings
from echo_masque.deployment_activity_media import (
    MediaAwareDeploymentBrowsingActivityService,
)
from echo_masque.deployment_discovery_intelligence import (
    DeploymentDiscoverySeeds,
    RankedDiscoveryCandidate,
)
from echo_masque.deployment_discovery_service import DeploymentDiscoveryPreview
from echo_masque.discovery_contracts import DiscoveryCandidate, DiscoveryMode
from echo_masque.discovery_media_inspection import DiscoveryMediaInspection
from echo_masque.persistence.conversation_structure_models import ConversationThreadRecord
from echo_masque.persistence.database import Database
from echo_masque.persistence.deployment_activity_repository import DeploymentActivityRepository
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord
from echo_masque.persistence.discovery_models import DeploymentDiscoveryProfileRecord
from echo_masque.persistence.discovery_repository import DiscoveryRepository


class FakePreviewRunner:
    def __init__(self, database: Database) -> None:
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
        seeds = DeploymentDiscoverySeeds(
            deployment_id=deployment_id,
            owner_id=owner_id,
            character_card_id="character-1",
            connection_id="connection-1",
            guild_id="guild-1",
            queries=("desktop robot",),
            semantic_text="desktop robot",
            seeds=(),
        )
        values = (
            ("robot", "Desktop robot", 0.91),
            ("agent", "AI agent", 0.71),
        )
        ranked: list[RankedDiscoveryCandidate] = []
        for key, title, score in values[:limit]:
            candidate = DiscoveryCandidate(
                source="youtube",
                canonical_key=f"youtube:{key}",
                content_kind="video",
                title=title,
                description=title,
                creator="Maker",
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


class FakeMediaInspector:
    def __init__(self) -> None:
        self.urls: list[str] = []

    async def inspect(
        self,
        *,
        owner_id: str,
        character_card_id: str,
        url: str,
        seeds: DeploymentDiscoverySeeds,
    ) -> DiscoveryMediaInspection | None:
        assert owner_id == "owner-1"
        assert character_card_id == "character-1"
        assert seeds.queries
        self.urls.append(url)
        return DiscoveryMediaInspection(
            source_key="youtube:robot",
            context_kind="video",
            label="Desktop robot",
            deep_relevance=0.9,
            reason="existing_media_context_e5",
        )


def seed_runtime(database: Database) -> None:
    now = datetime(2026, 8, 18, 8, 0, tzinfo=UTC)
    with database.session() as session:
        session.add(
            CharacterDeploymentRecord(
                id="deployment-1",
                owner_id="owner-1",
                character_card_id="character-1",
                connection_id="connection-1",
                platform="discord",
                workspace_id="guild-1",
                workspace_name="Guild",
                channel_id="channel-1",
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
                deployment_id="deployment-1",
                owner_id="owner-1",
                mode=DiscoveryMode.SHADOW.value,
                youtube_enabled=True,
                bilibili_enabled=False,
            )
        )
        session.add(
            ConversationThreadRecord(
                id="thread-1",
                owner_id="owner-1",
                platform="discord",
                connection_id="connection-1",
                guild_id="guild-1",
                channel_id="channel-1",
                discord_thread_id="",
                canonical_label="Desktop robots",
                anchor_summary="AI desktop companion robots",
                working_summary="Looking at AI desktop companion robots",
                representative_segment_ids_json="[]",
                participant_ids_json="[]",
                active_entity_ids_json="[]",
                status="hot",
                last_active_at=now,
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()


def test_media_aware_activity_promotes_one_open_item_without_double_exposure(
    tmp_path: Path,
) -> None:
    database = Database(f"sqlite:///{tmp_path / 'media-aware-activity.db'}")
    database.initialize()
    seed_runtime(database)
    inspector = FakeMediaInspector()
    settings = Settings(
        environment="test",
        youtube_data_api_key=SecretStr("test-key"),
        discovery_activity_open_budget=2,
        discovery_activity_watch_budget=1,
    )
    service = MediaAwareDeploymentBrowsingActivityService(
        database,
        settings,
        preview=FakePreviewRunner(database),
        media_inspector=inspector,
    )
    now = datetime(2026, 8, 18, 8, 0, tzinfo=UTC)

    activity = asyncio.run(
        service.run_manual(
            owner_id="owner-1",
            deployment_id="deployment-1",
            duration_minutes=15,
            candidate_budget=2,
            open_budget=2,
            now=now,
        )
    )
    assert activity.status == "active"
    assert activity.engage_count == 1
    assert activity.watch_count == 0
    assert activity.open_count == 1
    assert inspector.urls == ["https://www.youtube.com/watch?v=robot"]

    activity_items = DeploymentActivityRepository(database).list_items(
        owner_id="owner-1",
        session_id=activity.id,
    )
    assert [item.attention_level for item in activity_items] == ["engage", "open"]

    exposures = DiscoveryRepository(database).list_exposures(
        owner_id="owner-1",
        deployment_id="deployment-1",
    )
    by_item = {row.discovery_item_id: row for row in exposures}
    promoted_item = next(
        item for item in activity_items if item.attention_level == "engage"
    )
    assert by_item[promoted_item.discovery_item_id].attention_level == "engage"
    assert by_item[promoted_item.discovery_item_id].exposure_count == 1
