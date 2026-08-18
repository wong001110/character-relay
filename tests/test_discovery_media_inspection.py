import asyncio

from echo_masque.config import Settings
from echo_masque.deployment_discovery_intelligence import (
    DeploymentDiscoverySeeds,
    DiscoverySeed,
)
from echo_masque.discovery_media_inspection import DiscoveryMediaInspectionService
from echo_masque.live_media import LiveMediaContext


class FakeContextReader:
    def __init__(self, context: LiveMediaContext | None) -> None:
        self.context = context
        self.calls = 0

    async def inspect_public_url(
        self,
        *,
        owner_id: str,
        character_card_id: str,
        url: str,
    ) -> LiveMediaContext | None:
        assert owner_id == "owner-1"
        assert character_card_id == "character-1"
        assert url.startswith("https://www.youtube.com/")
        self.calls += 1
        return self.context


class FakeEncoder:
    model_name = "fake-e5"
    dimension = 2

    def __init__(self) -> None:
        self.query_calls = 0
        self.passage_calls = 0

    def embed_query(self, text: str) -> list[float]:
        assert "robotics" in text
        self.query_calls += 1
        return [1.0, 0.0]

    def embed_passage(self, text: str) -> list[float]:
        assert "desktop robot" in text.casefold()
        self.passage_calls += 1
        return [1.0, 0.0]


def seeds() -> DeploymentDiscoverySeeds:
    return DeploymentDiscoverySeeds(
        deployment_id="deployment-1",
        owner_id="owner-1",
        character_card_id="character-1",
        connection_id="connection-1",
        guild_id="guild-1",
        queries=("robotics",),
        semantic_text="Interest (topic, weight=0.90): robotics",
        seeds=(
            DiscoverySeed(
                text="robotics",
                weight=0.9,
                source="topic",
                evidence_ref="topic:robotics",
            ),
        ),
    )


def media_context() -> LiveMediaContext:
    return LiveMediaContext(
        source_key="youtube:abc",
        kind="video",
        label="Desktop AI robot",
        summary="A desktop robot uses an autonomous AI agent to interact with its owner.",
        visible_text="robotics autonomous agent",
        notable_details=("Small desktop companion robot",),
    )


def test_media_inspection_scores_existing_objective_context_with_shared_e5() -> None:
    reader = FakeContextReader(media_context())
    encoder = FakeEncoder()
    service = DiscoveryMediaInspectionService(
        reader,
        Settings(environment="test"),
        encoder=encoder,
    )

    result = asyncio.run(
        service.inspect(
            owner_id="owner-1",
            character_card_id="character-1",
            url="https://www.youtube.com/watch?v=abc",
            seeds=seeds(),
        )
    )
    assert result is not None
    assert result.source_key == "youtube:abc"
    assert result.deep_relevance == 1.0
    assert result.reason == "existing_media_context_e5"
    assert reader.calls == 1
    assert encoder.query_calls == 1
    assert encoder.passage_calls == 1


def test_media_inspection_uses_sparse_fallback_without_loading_embedding_runtime() -> None:
    reader = FakeContextReader(media_context())
    service = DiscoveryMediaInspectionService(
        reader,
        Settings(environment="test", semantic_embedding_enabled=False),
        encoder=None,
    )

    result = asyncio.run(
        service.inspect(
            owner_id="owner-1",
            character_card_id="character-1",
            url="https://www.youtube.com/watch?v=abc",
            seeds=seeds(),
        )
    )
    assert result is not None
    assert result.reason == "existing_media_context_sparse_fallback"
    assert 0.0 < result.deep_relevance <= 1.0


def test_media_inspection_returns_none_when_existing_media_runtime_has_no_context() -> None:
    service = DiscoveryMediaInspectionService(
        FakeContextReader(None),
        Settings(environment="test"),
    )
    result = asyncio.run(
        service.inspect(
            owner_id="owner-1",
            character_card_id="character-1",
            url="https://www.youtube.com/watch?v=abc",
            seeds=seeds(),
        )
    )
    assert result is None
