"""Integrated, source-isolated Character Discovery preview for one Deployment."""

from __future__ import annotations

from dataclasses import dataclass

from echo_masque.bilibili_discovery import (
    BilibiliDiscoveryAdapter,
    BilibiliDiscoveryUnavailable,
)
from echo_masque.config import Settings
from echo_masque.deployment_discovery_intelligence import (
    DeploymentDiscoverySeedBuilder,
    DeploymentDiscoverySeeds,
    DiscoveryCandidateRanker,
    RankedDiscoveryCandidate,
)
from echo_masque.discovery_contracts import (
    DiscoveryCandidate,
    DiscoveryFetchRequest,
    DiscoveryMode,
)
from echo_masque.persistence.database import Database
from echo_masque.persistence.deployment_presence_repository import DeploymentPresenceRepository
from echo_masque.persistence.discovery_repository import DiscoveryRepository
from echo_masque.youtube_discovery import YouTubeDiscoveryAdapter, YouTubeDiscoveryUnavailable


class DeploymentDiscoveryUnavailable(RuntimeError):
    """Raised when an enabled Deployment cannot safely execute Discovery."""


@dataclass(frozen=True, slots=True)
class DeploymentDiscoveryPreview:
    deployment_id: str
    seeds: DeploymentDiscoverySeeds
    ranked: tuple[RankedDiscoveryCandidate, ...]
    sources: tuple[str, ...] = ()
    source_errors: tuple[str, ...] = ()


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
        sources: tuple[str, ...] = (),
    ) -> DeploymentDiscoveryPreview:
        profile = self.profiles.get_profile(owner_id=owner_id, deployment_id=deployment_id)
        if profile is None:
            raise DeploymentDiscoveryUnavailable("Deployment not found.")
        if profile.mode is DiscoveryMode.OFF:
            raise DeploymentDiscoveryUnavailable("Discovery is disabled for this Deployment.")
        presence = self.presence.get(owner_id=owner_id, deployment_id=deployment_id)
        if presence is None:
            raise DeploymentDiscoveryUnavailable("Deployment not found.")
        if not presence.discovery_allowed:
            raise DeploymentDiscoveryUnavailable(
                f"Discovery is unavailable while Deployment Presence is {presence.state}."
            )
        enabled: list[str] = []
        if profile.youtube_enabled:
            enabled.append("youtube")
        if profile.bilibili_enabled:
            enabled.append("bilibili")
        requested = tuple(
            dict.fromkeys(value.casefold().strip() for value in sources if value.strip())
        ) or tuple(enabled)
        if not requested:
            raise DeploymentDiscoveryUnavailable("No Discovery source is enabled.")
        unsupported = [value for value in requested if value not in enabled]
        if unsupported:
            raise DeploymentDiscoveryUnavailable(
                "Discovery source is not enabled for this Deployment: " + ", ".join(unsupported)
            )
        seeds = self.seed_builder.build(owner_id=owner_id, deployment_id=deployment_id)
        if seeds is None:
            raise DeploymentDiscoveryUnavailable("Deployment not found.")
        bounded_limit = max(1, min(limit, 30))
        fetch_limit = min(50, max(15, bounded_limit * 3))
        candidates: list[DiscoveryCandidate] = []
        used_sources: list[str] = []
        errors: list[str] = []

        if "youtube" in requested:
            key = self.settings.youtube_data_api_key
            if key is None or not key.get_secret_value().strip():
                errors.append("youtube:api_key_missing")
            else:
                try:
                    values = await YouTubeDiscoveryAdapter(
                        database=self.database,
                        api_key=key,
                        search_cache_seconds=self.settings.youtube_discovery_search_cache_seconds,
                        popular_cache_seconds=self.settings.youtube_discovery_popular_cache_seconds,
                        max_search_queries_per_session=(
                            self.settings.youtube_discovery_max_search_queries_per_session
                        ),
                    ).fetch_candidates(
                        DiscoveryFetchRequest(
                            queries=seeds.queries,
                            region=region,
                            language=language,
                            limit=fetch_limit,
                            include_popular=True,
                        )
                    )
                except YouTubeDiscoveryUnavailable as exc:
                    errors.append(f"youtube:{exc}")
                else:
                    candidates.extend(values)
                    used_sources.append("youtube")

        if "bilibili" in requested:
            if not self.settings.bilibili_discovery_experimental_enabled:
                errors.append("bilibili:experimental_source_disabled")
            else:
                try:
                    values = await BilibiliDiscoveryAdapter(
                        database=self.database,
                        search_cache_seconds=self.settings.bilibili_discovery_search_cache_seconds,
                        max_search_queries_per_session=(
                            self.settings.bilibili_discovery_max_search_queries_per_session
                        ),
                        max_results_per_query=(
                            self.settings.bilibili_discovery_max_results_per_query
                        ),
                    ).fetch_candidates(
                        DiscoveryFetchRequest(
                            queries=seeds.queries,
                            limit=fetch_limit,
                            include_popular=False,
                        )
                    )
                except BilibiliDiscoveryUnavailable as exc:
                    errors.append(f"bilibili:{exc}")
                else:
                    candidates.extend(values)
                    used_sources.append("bilibili")

        if not candidates and errors:
            raise DeploymentDiscoveryUnavailable("; ".join(errors))
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
            sources=tuple(used_sources),
            source_errors=tuple(errors),
        )


__all__ = [
    "DeploymentDiscoveryPreview",
    "DeploymentDiscoveryPreviewService",
    "DeploymentDiscoveryUnavailable",
]
