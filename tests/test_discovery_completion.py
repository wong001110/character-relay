import asyncio
from datetime import UTC, datetime
from pathlib import Path

import httpx
from pydantic import SecretStr

from echo_masque.bilibili_discovery import BilibiliDiscoveryAdapter
from echo_masque.character_relationships import CharacterRelationshipService
from echo_masque.config import Settings
from echo_masque.discovery_contracts import (
    DiscoveryAttentionLevel,
    DiscoveryCandidate,
    DiscoveryFetchRequest,
    DiscoveryMode,
)
from echo_masque.discovery_share import DiscoveryShareCoordinator, DiscoveryShareDeliveryService
from echo_masque.discovery_social_association import (
    DiscoveryRelationshipAssociation,
    DiscoverySocialAssociationResult,
    DiscoverySocialAssociationService,
    DiscoveryThreadAssociation,
)
from echo_masque.persistence.conversation_runtime_models import ConversationEpisodeV3Record
from echo_masque.persistence.conversation_structure_repository import ConversationStructureRepository
from echo_masque.persistence.database import Database
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord
from echo_masque.persistence.discovery_repository import DiscoveryRepository
from echo_masque.persistence.discovery_share_repository import DiscoveryShareRepository
from echo_masque.persistence.discord_identity_repository import DiscordIdentityRepository
from echo_masque.persistence.episodic_sql_rag_repository import EpisodicSqlRagRepository


class FakeEncoder:
    model_name = "fake-e5"
    dimension = 2

    def embed_query(self, text: str) -> list[float]:
        return [1.0, 0.0]

    def embed_passage(self, text: str) -> list[float]:
        return [1.0, 0.0]


class FakeDraftGenerator:
    async def draft(
        self,
        *,
        owner_id: str,
        deployment_id: str,
        discovery_item_id: str,
        association: DiscoverySocialAssociationResult,
    ) -> str:
        assert owner_id == "owner-1"
        assert association.would_share
        return f"这个我觉得挺有意思的 {deployment_id} https://example.com/{discovery_item_id}"


def seed_deployment(
    database: Database,
    *,
    deployment_id: str,
    guild_id: str = "guild-1",
    channel_id: str = "channel-1",
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
                workspace_name="Guild",
                channel_id=channel_id,
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
        session.commit()


def seed_item_and_exposure(
    database: Database,
    *,
    deployment_id: str,
    canonical_key: str,
    attention: DiscoveryAttentionLevel = DiscoveryAttentionLevel.ENGAGE,
    score: float = 0.9,
) -> str:
    repository = DiscoveryRepository(database)
    item = repository.upsert_item(
        DiscoveryCandidate(
            source="youtube",
            canonical_key=canonical_key,
            content_kind="video",
            title="Desktop AI robot",
            description="An autonomous robotics companion project",
            creator="Maker",
            url=f"https://www.youtube.com/watch?v={canonical_key}",
            published_at=datetime(2026, 8, 18, 8, 0, tzinfo=UTC),
        )
    )
    exposure = repository.record_exposure(
        owner_id="owner-1",
        deployment_id=deployment_id,
        discovery_item_id=item.id,
        attention_level=attention,
        interest_score=score,
        subjective_reason="test",
    )
    assert exposure is not None
    return item.id


def test_bilibili_experimental_adapter_uses_persisted_hashed_query_cache(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'bilibili.db'}")
    database.initialize()
    calls: list[str] = []

    def search(query: str, limit: int) -> list[dict[str, object]]:
        calls.append(query)
        return [
            {
                "id": "BV1TEST123",
                "title": "AI 桌面机器人",
                "description": "robotics",
                "uploader": "Maker",
                "webpage_url": "https://www.bilibili.com/video/BV1TEST123",
                "timestamp": 1787040000,
            }
        ][:limit]

    adapter = BilibiliDiscoveryAdapter(
        database=database,
        search_function=search,
        max_search_queries_per_session=1,
    )
    request = DiscoveryFetchRequest(
        queries=("desktop robot", "ignored second query"),
        limit=6,
        include_popular=False,
    )
    first = asyncio.run(adapter.fetch_candidates(request))
    second = asyncio.run(adapter.fetch_candidates(request))
    assert [item.canonical_key for item in first] == ["bilibili:BV1TEST123"]
    assert [item.canonical_key for item in second] == ["bilibili:BV1TEST123"]
    assert calls == ["desktop robot"]


def test_social_association_uses_accessible_v3_episode_thread_and_social_model(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'association.db'}")
    database.initialize()
    seed_deployment(database, deployment_id="deployment-1")
    now = datetime(2026, 8, 18, 8, 0, tzinfo=UTC)
    thread = ConversationStructureRepository(database).create_thread(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="channel-1",
        discord_thread_id="",
        canonical_label="Desktop robots",
        anchor_summary="AI desktop robots",
        working_summary="AI desktop robots and robotics",
        now=now,
    )
    with database.session() as session:
        session.add(
            ConversationEpisodeV3Record(
                id="episode-1",
                owner_id="owner-1",
                platform="discord",
                connection_id="connection-1",
                guild_id="guild-1",
                channel_id="channel-1",
                discord_thread_id="",
                conversation_thread_id=thread.id,
                episode_key="episode-1",
                segment_ids_json='["segment-1"]',
                source_message_ids_json='["message-1"]',
                participant_ids_json='["user-123"]',
                entity_ids_json="[]",
                media_refs_json="[]",
                summary="We discussed building a desktop AI robot.",
                key_events_json='["robotics"]',
                segment_count=1,
                status="closed",
                checkpoint_reason="test",
                started_at=now,
                ended_at=now,
                updated_at=now,
            )
        )
        session.commit()
    CharacterRelationshipService(database).record_evidence(
        owner_id="owner-1",
        source_deployment_id="deployment-1",
        target_type="actor",
        target_key="user-123",
        dimension="familiarity",
        delta=0.8,
        confidence=0.9,
        reason_code="direct_interaction",
        source_message_id="message-1",
        now=now,
    )
    EpisodicSqlRagRepository(database).grant_character_access(
        owner_id="owner-1",
        character_card_id="character-1",
        deployment_id="deployment-1",
        episode_id="episode-1",
        now=now,
    )
    item_id = seed_item_and_exposure(
        database,
        deployment_id="deployment-1",
        canonical_key="robot-video",
    )
    result = DiscoverySocialAssociationService(
        database,
        Settings(environment="test"),
        encoder=FakeEncoder(),
    ).evaluate(
        owner_id="owner-1",
        deployment_id="deployment-1",
        discovery_item_id=item_id,
        now=now,
    )
    assert result is not None and result.would_share
    assert result.episode is not None and result.episode.episode_id == "episode-1"
    assert result.thread is not None and result.thread.conversation_thread_id == thread.id
    assert result.relationship is not None
    assert result.relationship.subject_key == "actor:user-123"


def association(item_id: str, deployment_id: str) -> DiscoverySocialAssociationResult:
    return DiscoverySocialAssociationResult(
        deployment_id=deployment_id,
        discovery_item_id=item_id,
        thread=DiscoveryThreadAssociation(
            conversation_thread_id="thread-1",
            label="Desktop robots",
            status="hot",
            channel_id="channel-1",
            discord_thread_id="",
            score=0.9,
        ),
        episode=None,
        relationship=DiscoveryRelationshipAssociation(
            subject_key="actor:user-123",
            label="Alice",
            score=0.7,
        ),
        would_share=True,
        motivation="REMIND_ME_OF_SOMEONE",
        confidence=0.88,
    )


def test_review_requires_approval_and_auto_requires_both_opt_ins(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'review-auto.db'}")
    database.initialize()
    seed_deployment(database, deployment_id="review-deployment")
    seed_deployment(
        database,
        deployment_id="auto-deployment",
        guild_id="guild-2",
        channel_id="channel-2",
    )
    discovery = DiscoveryRepository(database)
    shares = DiscoveryShareRepository(database)

    review_item = seed_item_and_exposure(
        database,
        deployment_id="review-deployment",
        canonical_key="review-item",
    )
    discovery.set_profile(
        owner_id="owner-1",
        deployment_id="review-deployment",
        mode=DiscoveryMode.REVIEW,
        youtube_enabled=True,
        bilibili_enabled=False,
    )
    shares.set_policy(
        owner_id="owner-1",
        deployment_id="review-deployment",
        auto_share_enabled=False,
        daily_share_budget=1,
        share_cooldown_minutes=180,
    )
    review = DiscoveryShareCoordinator(
        database,
        Settings(environment="test"),
        draft_generator=FakeDraftGenerator(),
    )
    proposal = asyncio.run(
        review.maybe_propose(
            owner_id="owner-1",
            deployment_id="review-deployment",
            discovery_item_id=review_item,
            association=association(review_item, "review-deployment"),
        )
    )
    assert proposal is not None and proposal.status == "pending_review"
    assert proposal.conversation_thread_id == "thread-1"
    approved = review.approve(owner_id="owner-1", share_id=proposal.id)
    assert approved is not None and approved.status == "queued"

    auto_item = seed_item_and_exposure(
        database,
        deployment_id="auto-deployment",
        canonical_key="auto-item",
    )
    discovery.set_profile(
        owner_id="owner-1",
        deployment_id="auto-deployment",
        mode=DiscoveryMode.AUTO,
        youtube_enabled=True,
        bilibili_enabled=False,
    )
    shares.set_policy(
        owner_id="owner-1",
        deployment_id="auto-deployment",
        auto_share_enabled=True,
        daily_share_budget=1,
        share_cooldown_minutes=180,
    )
    disabled = DiscoveryShareCoordinator(
        database,
        Settings(environment="test", discovery_auto_share_global_enabled=False),
        draft_generator=FakeDraftGenerator(),
    )
    assert asyncio.run(
        disabled.maybe_propose(
            owner_id="owner-1",
            deployment_id="auto-deployment",
            discovery_item_id=auto_item,
            association=association(auto_item, "auto-deployment"),
        )
    ) is None
    enabled = DiscoveryShareCoordinator(
        database,
        Settings(environment="test", discovery_auto_share_global_enabled=True),
        draft_generator=FakeDraftGenerator(),
    )
    queued = asyncio.run(
        enabled.maybe_propose(
            owner_id="owner-1",
            deployment_id="auto-deployment",
            discovery_item_id=auto_item,
            association=association(auto_item, "auto-deployment"),
        )
    )
    assert queued is not None and queued.status == "queued"


def test_approved_review_share_delivers_through_real_bot_identity(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'delivery.db'}")
    database.initialize()
    seed_deployment(database, deployment_id="deployment-1")
    discovery = DiscoveryRepository(database)
    shares = DiscoveryShareRepository(database)
    item_id = seed_item_and_exposure(
        database,
        deployment_id="deployment-1",
        canonical_key="delivery-item",
    )
    discovery.set_profile(
        owner_id="owner-1",
        deployment_id="deployment-1",
        mode=DiscoveryMode.REVIEW,
        youtube_enabled=True,
        bilibili_enabled=False,
    )
    shares.set_policy(
        owner_id="owner-1",
        deployment_id="deployment-1",
        auto_share_enabled=False,
        daily_share_budget=1,
        share_cooldown_minutes=180,
    )
    share = shares.create_proposal(
        owner_id="owner-1",
        deployment_id="deployment-1",
        discovery_item_id=item_id,
        source_decision_id="",
        mode="review",
        status="queued",
        motivation="RELATED_TO_CURRENT_THREAD",
        confidence=0.9,
        conversation_thread_id="thread-1",
        relationship_subject_key="",
        channel_id="channel-1",
        thread_id="",
        draft_text="这个挺有意思 https://example.com",
    )
    assert share is not None
    DiscordIdentityRepository(database).upsert_identity(
        deployment_id="deployment-1",
        owner_id="owner-1",
        mode="bot",
        display_name="Character",
        avatar_url="",
    )
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"id": "discord-message-1"})

    service = DiscoveryShareDeliveryService(
        database,
        Settings(environment="test", discord_tool_bot_token=SecretStr("bot-token")),
        http_transport=httpx.MockTransport(handler),
    )
    assert asyncio.run(service.deliver_due_once()) == 1
    assert len(requests) == 1
    assert requests[0].headers["Authorization"] == "Bot bot-token"
    delivered = shares.get(owner_id="owner-1", share_id=share.id)
    assert delivered is not None and delivered.status == "delivered"
    assert delivered.discord_message_id == "discord-message-1"
