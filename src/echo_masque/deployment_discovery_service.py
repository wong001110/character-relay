"""Integrated, side-effect-free Shadow Discovery preview for one Deployment."""

from __future__ import annotations

from dataclasses import dataclass

from echo_masque.config import Settings
from echo_masque.deployment_discovery_intelligence import (
    DeploymentDiscoverySeedBuilder,
    DeploymentDiscoverySeeds,
    DiscoveryCandidateRanker,
    RankedDiscoveryCandidate,
)
from echo_masque.discovery_contracts import DiscoveryFetchRequest, DiscoveryMode
from echo_masque.persistence.database import Database
from echo_masque.persistence.deployment_presence_repository import DeploymentPresenceRepository
from echo_masque.persistence.discovery_repository import DiscoveryRepository
from echo_masque.youtube_discovery import YouTubeDiscoveryAdapter


class DeploymentDiscoveryUnavailable(RuntimeError):
    """Raised when an enabled Deployment cannot safely execute a Discovery preview."""


@dataclass(frozen=True, slots=True)
class DeploymentDiscoveryPreview:
    deployment_id: str
    seeds: DeploymentDiscoverySeeds
    ranked: tuple[RankedDiscoveryCandidate, ...]


class DeploymentDiscoveryPreviewService:
    """Collect + rank without recording exposure, calling Character LLMs, or posting anywhere."""

    def __init__(self, database: Database, settings: Settings) -> None:
        self.database = database
        self.settings = settings
        self.profiles = DiscoveryRepository(database)
        self.presence = DeploymentPresenceRepository(database)
        self.seed_builder = DeploymentDiscoverySeedBuilder(database)
        self.ranker = DiscoveryCandidateRanker(database, settings)

    async def run(
        self,
        *,
        owner_id: str,
        deployment_id: str,
        region: str = "",
        language: str = "",
        limit: int = 10,
    ) -> DeploymentDiscoveryPreview:
        profile = self.profiles.get_profile(
            owner_id=owner_id,
            deployment_id=deployment_id,
        )
        if profile is None:
            raise DeploymentDiscoveryUnavailable("Deployment not found.")
        if profile.mode is not DiscoveryMode.SHADOW:
            raise DeploymentDiscoveryUnavailable(
                "Discovery Shadow preview requires Deployment mode=shadow."
            )
        if not profile.youtube_enabled:
            raise DeploymentDiscoveryUnavailable("YouTube Discovery is not enabled.")
        presence = self.presence.get(owner_id=owner_id, deployment_id=deployment_id)
        if presence is None:
            raise DeploymentDiscoveryUnavailable("Deployment not found.")
        if not presence.discovery_allowed:
            raise DeploymentDiscoveryUnavailable(
                f"Discovery is unavailable while Deployment Presence is {presence.state}."
            )
        key = self.settings.youtube_data_api_key
        if key is None or not key.get_secret_value().strip():
            raise DeploymentDiscoveryUnavailable(
                "CHARACTER_RELAY_YOUTUBE_DATA_API_KEY is not configured."
            )
        seeds = self.seed_builder.build(owner_id=owner_id, deployment_id=deployment_id)
        if seeds is None:
            raise DeploymentDiscoveryUnavailable("Deployment not found.")
        bounded_limit = max(1, min(limit, 30))
        adapter = YouTubeDiscoveryAdapter(
            database=self.database,
            api_key=key,
            search_cache_seconds=self.settings.youtube_discovery_search_cache_seconds,
            popular_cache_seconds=self.settings.youtube_discovery_popular_cache_seconds,
            max_search_queries_per_session=(
                self.settings.youtube_discovery_max_search_queries_per_session
            ),
        )
        candidates = await adapter.fetch_candidates(
            DiscoveryFetchRequest(
                queries=seeds.queries,
                region=region,
                language=language,
                limit=min(50, max(15, bounded_limit * 3)),
                include_popular=True,
            )
        )
        ranked = self.ranker.rank(
            owner_id=owner_id,
            deployment_id=deployment_id,
            seeds=seeds,
            candidates=candidates,
            limit=bounded_limit,
        )
        return DeploymentDiscoveryPreview(
            deployment_id=deployment_id,
            seeds=seeds,
            ranked=ranked,
        )


__all__ = [
    "DeploymentDiscoveryPreview",
    "DeploymentDiscoveryPreviewService",
    "DeploymentDiscoveryUnavailable",
]
