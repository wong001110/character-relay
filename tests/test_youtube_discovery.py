import asyncio
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select

from echo_masque.config import Settings
from echo_masque.deployment_discovery_intelligence import DiscoveryCandidateRanker
from echo_masque.deployment_discovery_seeds_v3 import DeploymentDiscoverySeedBuilderV3
from echo_masque.discovery_contracts import DiscoveryCandidate, DiscoveryFetchRequest
from echo_masque.persistence.character_learned_state_event_models import (
    CharacterLearnedStateEventRecord,
)
from echo_masque.persistence.conversation_structure_models import ConversationThreadRecord
from echo_masque.persistence.database import Database
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord
from echo_masque.persistence.discovery_models import DiscoverySourceQueryCacheRecord
from echo_masque.youtube_discovery import YouTubeDiscoveryAdapter, YouTubeDiscoveryUnavailable


class FakeSemanticEncoder:
    model_name = "fake-e5"
    dimension = 2

    def __init__(self) -> None:
        self.query_calls = 0
        self.passage_calls = 0

    def embed_query(self, text: str) -> list[float]:
        self.query_calls += 1
        return [1.0, 0.0]

    def embed_passage(self, text: str) -> list[float]:
        self.passage_calls += 1
        lowered = text.casefold()
        return [1.0, 0.0] if "robot" in lowered else [0.0, 1.0]


def youtube_search_item(video_id: str, title: str) -> dict[str, object]:
    return {
        "id": {"videoId": video_id},
        "snippet": {
            "title": title,
            "description": f"Description for {title}",
            "channelTitle": "Maker",
            "channelId": "channel-maker",
            "publishedAt": "2026-08-17T08:00:00Z",
            "thumbnails": {"high": {"url": f"https://img.example/{video_id}.jpg"}},
        },
    }


def youtube_popular_item(video_id: str, title: str) -> dict[str, object]:
    return {
        "id": video_id,
        "snippet": {
            "title": title,
            "description": f"Popular {title}",
            "channelTitle": "Popular Maker",
            "channelId": "popular-channel",
            "publishedAt": "2026-08-18T01:00:00Z",
            "thumbnails": {"medium": {"url": f"https://img.example/{video_id}.jpg"}},
        },
        "contentDetails": {"duration": "PT4M"},
        "statistics": {"viewCount": "1234", "likeCount": "50", "commentCount": "7"},
    }


def test_youtube_adapter_caps_search_queries_dedupes_and_reuses_persisted_cache(
    tmp_path: Path,
) -> None:
    database = Database(f"sqlite:///{tmp_path / 'youtube-cache.db'}")
    database.initialize()
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/search"):
            query = request.url.params["q"]
            video_id = "robot-1" if "robot" in query else "agent-1"
            return httpx.Response(200, json={"items": [youtube_search_item(video_id, query)]})
        if request.url.path.endswith("/videos"):
            return httpx.Response(
                200,
                json={
                    "items": [
                        youtube_popular_item("robot-1", "AI robot duplicate"),
                        youtube_popular_item("popular-2", "Popular animation"),
                    ]
                },
            )
        return httpx.Response(404)

    adapter = YouTubeDiscoveryAdapter(
        database=database,
        api_key=SecretStr("public-data-api-key"),
        max_search_queries_per_session=2,
        http_transport=httpx.MockTransport(handler),
    )
    request = DiscoveryFetchRequest(
        queries=("desktop robot", "AI agent", "third query must not execute"),
        region="MY",
        language="zh-Hans",
        limit=10,
        include_popular=True,
    )
    first = asyncio.run(adapter.fetch_candidates(request))
    assert {item.canonical_key for item in first} == {
        "youtube:robot-1",
        "youtube:agent-1",
        "youtube:popular-2",
    }
    assert len([item for item in requests if item.url.path.endswith("/search")]) == 2
    assert len([item for item in requests if item.url.path.endswith("/videos")]) == 1
    assert all("authorization" not in item.headers for item in requests)
    assert all(item.url.params["key"] == "public-data-api-key" for item in requests)

    # Same source snapshot is served from SQLite without consuming another YouTube request.
    before = len(requests)
    second = asyncio.run(adapter.fetch_candidates(request))
    assert [item.canonical_key for item in second] == [item.canonical_key for item in first]
    assert len(requests) == before

    with database.session() as session:
        cache_rows = list(session.scalars(select(DiscoverySourceQueryCacheRecord)))
    assert len(cache_rows) == 3
    serialized = "\n".join(
        f"{row.normalized_query_hash}|{row.result_keys_json}" for row in cache_rows
    )
    assert "desktop robot" not in serialized
    assert "AI agent" not in serialized


def test_youtube_adapter_fails_softly_with_typed_unavailable_error(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'youtube-error.db'}")
    database.initialize()

    adapter = YouTubeDiscoveryAdapter(
        database=database,
        api_key=SecretStr("public-data-api-key"),
        http_transport=httpx.MockTransport(lambda request: httpx.Response(429, json={})),
    )
    with pytest.raises(YouTubeDiscoveryUnavailable, match="HTTP 429"):
        asyncio.run(
            adapter.fetch_candidates(
                DiscoveryFetchRequest(queries=("robot",), include_popular=False)
            )
        )


def seed_deployment(
    database: Database,
    *,
    deployment_id: str,
    guild_id: str,
    channel_id: str,
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


def conversation_thread(
    *,
    thread_id: str,
    guild_id: str,
    label: str,
) -> ConversationThreadRecord:
    now = datetime(2026, 8, 18, 8, 0, tzinfo=UTC)
    return ConversationThreadRecord(
        id=thread_id,
        owner_id="owner-1",
        platform="discord",
        connection_id="connection-1",
        guild_id=guild_id,
        channel_id=f"channel-{guild_id}",
        discord_thread_id="",
        canonical_label=label,
        anchor_summary=label,
        working_summary=label,
        representative_segment_ids_json="[]",
        participant_ids_json="[]",
        active_entity_ids_json="[]",
        status="hot",
        last_active_at=now,
        created_at=now,
        updated_at=now,
    )


def interest_event(
    *,
    event_id: str,
    guild_id: str,
    subject_key: str,
) -> CharacterLearnedStateEventRecord:
    now = datetime(2026, 8, 18, 8, 0, tzinfo=UTC)
    return CharacterLearnedStateEventRecord(
        id=event_id,
        state_id=f"state-{event_id}",
        owner_id="owner-1",
        character_card_id="character-1",
        state_type="interest",
        subject_type="concept",
        subject_key=subject_key,
        connection_id="connection-1",
        guild_id=guild_id,
        channel_id=f"channel-{guild_id}",
        conversation_thread_id="",
        delta=0.8,
        evidence_confidence=0.9,
        value_before=0.0,
        value_after=0.18,
        confidence_before=0.0,
        confidence_after=0.225,
        contradiction=False,
        source_type="test",
        source_message_id="message-1",
        source_burst_id="burst-1",
        reason_code="test_interest",
        recorded_at=now,
    )


def test_seed_builder_does_not_leak_other_server_interests(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'discovery-seeds.db'}")
    database.initialize()
    seed_deployment(
        database,
        deployment_id="deployment-a",
        guild_id="guild-a",
        channel_id="channel-a",
    )
    seed_deployment(
        database,
        deployment_id="deployment-b",
        guild_id="guild-b",
        channel_id="channel-b",
    )
    with database.session() as session:
        session.add(
            conversation_thread(
                thread_id="thread-a",
                guild_id="guild-a",
                label="Desktop robots",
            )
        )
        session.add(
            conversation_thread(
                thread_id="thread-b",
                guild_id="guild-b",
                label="Anime music",
            )
        )
        session.add(
            interest_event(
                event_id="event-a",
                guild_id="guild-a",
                subject_key="concept:robotics",
            )
        )
        session.add(
            interest_event(
                event_id="event-b",
                guild_id="guild-b",
                subject_key="concept:cooking",
            )
        )
        session.commit()

    seeds_a = DeploymentDiscoverySeedBuilderV3(database).build(
        owner_id="owner-1",
        deployment_id="deployment-a",
        now=datetime(2026, 8, 18, 8, 0, tzinfo=UTC),
    )
    assert seeds_a is not None
    joined = " | ".join(seeds_a.queries).casefold()
    assert "desktop robots" in joined
    assert "robotics" in joined
    assert "anime music" not in joined
    assert "cooking" not in joined


def test_e5_ranker_reuses_candidate_vectors_and_prefers_server_interest(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'discovery-ranker.db'}")
    database.initialize()
    seed_deployment(
        database,
        deployment_id="deployment-a",
        guild_id="guild-a",
        channel_id="channel-a",
    )
    with database.session() as session:
        session.add(
            conversation_thread(
                thread_id="thread-a",
                guild_id="guild-a",
                label="Desktop robot",
            )
        )
        session.commit()

    seeds = DeploymentDiscoverySeedBuilderV3(database).build(
        owner_id="owner-1",
        deployment_id="deployment-a",
        now=datetime(2026, 8, 18, 8, 0, tzinfo=UTC),
    )
    assert seeds is not None
    encoder = FakeSemanticEncoder()
    ranker = DiscoveryCandidateRanker(
        database,
        Settings(environment="test"),
        encoder=encoder,
    )
    candidates = (
        DiscoveryCandidate(
            source="youtube",
            canonical_key="youtube:robot",
            content_kind="video",
            title="I built an AI desktop robot",
            description="Autonomous companion robot project",
            creator="Maker",
            url="https://www.youtube.com/watch?v=robot",
            published_at=datetime(2026, 8, 18, 1, 0, tzinfo=UTC),
        ),
        DiscoveryCandidate(
            source="youtube",
            canonical_key="youtube:cooking",
            content_kind="video",
            title="Cooking noodles tonight",
            description="A food vlog",
            creator="Cook",
            url="https://www.youtube.com/watch?v=cooking",
            published_at=datetime(2026, 8, 18, 1, 0, tzinfo=UTC),
        ),
    )
    first = ranker.rank(
        owner_id="owner-1",
        deployment_id="deployment-a",
        seeds=seeds,
        candidates=candidates,
        limit=2,
        now=datetime(2026, 8, 18, 8, 0, tzinfo=UTC),
    )
    assert first[0].candidate.canonical_key == "youtube:robot"
    assert first[0].semantic_relevance > first[1].semantic_relevance
    assert encoder.query_calls == 1
    assert encoder.passage_calls == 2

    # Candidate vectors are persisted in the existing SemanticVectorRepository namespace.
    ranker.rank(
        owner_id="owner-1",
        deployment_id="deployment-a",
        seeds=seeds,
        candidates=candidates,
        limit=2,
        now=datetime(2026, 8, 18, 8, 5, tzinfo=UTC),
    )
    assert encoder.query_calls == 2
    assert encoder.passage_calls == 2
