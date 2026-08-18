"""Selective public-media inspection for Deployment Character Discovery."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, cast

from echo_masque.config import Settings
from echo_masque.content_resolver import resolve_static_url
from echo_masque.deployment_discovery_intelligence import DeploymentDiscoverySeeds
from echo_masque.live_media import LiveMediaContext, LiveMediaContextService
from echo_masque.live_media_enhanced import EnhancedLiveMediaContextService
from echo_masque.semantic_participation import (
    FastEmbedSemanticEncoder,
    SemanticEmbeddingUnavailable,
    SemanticEncoder,
    _cosine,
)


class PublicMediaContextReader(Protocol):
    async def inspect_public_url(
        self,
        *,
        owner_id: str,
        character_card_id: str,
        url: str,
    ) -> LiveMediaContext | None: ...


class DiscoveryMediaContextService(EnhancedLiveMediaContextService):
    """Expose Enhanced Live Media's existing public-URL path without faking a Discord turn."""

    @classmethod
    def from_service(
        cls,
        service: LiveMediaContextService,
        *,
        browser_runtime: object | None,
    ) -> DiscoveryMediaContextService:
        # Keep the parent's dependency-preserving factory semantics while narrowing the return
        # type for callers. browser_runtime is intentionally passed through unchanged.
        return cast(
            DiscoveryMediaContextService,
            super().from_service(
                service,
                browser_runtime=browser_runtime,  # type: ignore[arg-type]
            ),
        )

    async def inspect_public_url(
        self,
        *,
        owner_id: str,
        character_card_id: str,
        url: str,
    ) -> LiveMediaContext | None:
        """Resolve one public URL through the same yt-dlp/MediaAnalysis cache used by chat turns."""

        try:
            source = resolve_static_url(url)
        except ValueError:
            return None

        if source.kind in {"article", "social_post", "unknown"}:
            return await self._article_context(source)
        if source.kind not in {"image", "video"}:
            return None

        credential = self.credential_resolver.resolve(
            owner_id=owner_id,
            character_card_id=character_card_id,
            capability="media",
        )
        if credential is not None:
            try:
                resolved = await self._resolve_public_media(source)
                analysis, _ = await self._analyze(resolved.asset, credential)
                return self._analysis_context(
                    resolved.source_key,
                    cast(Literal["image", "video"], source.kind),
                    source.platform,
                    analysis,
                )
            except Exception:
                # Existing Enhanced Live Media already defines transcript/metadata/article
                # fallback for platform URLs; keep the same failure semantics here.
                pass
        return await self._article_context(source)


@dataclass(frozen=True, slots=True)
class DiscoveryMediaInspection:
    source_key: str
    context_kind: str
    label: str
    deep_relevance: float
    reason: str


class DiscoveryMediaInspectionService:
    """Use existing objective media context plus shared E5 for one bounded deep-interest check."""

    def __init__(
        self,
        context_reader: PublicMediaContextReader,
        settings: Settings,
        *,
        encoder: SemanticEncoder | None = None,
    ) -> None:
        self.context_reader = context_reader
        self.settings = settings
        self.encoder = encoder
        if self.encoder is None and settings.semantic_embedding_runtime_enabled:
            self.encoder = FastEmbedSemanticEncoder(
                model_name=settings.semantic_embedding_model,
                model_file=settings.semantic_embedding_model_file,
                cache_dir=settings.semantic_embedding_cache_dir,
                dimension=settings.semantic_embedding_dimension,
            )

    @staticmethod
    def _context_text(context: LiveMediaContext) -> str:
        return "\n".join(
            value
            for value in (
                context.label.strip(),
                context.summary.strip(),
                context.visible_text.strip()[:12_000],
                "\n".join(context.notable_details[:20]),
            )
            if value
        )[:16_000]

    @staticmethod
    def _tokens(value: str) -> set[str]:
        return {
            part.strip(".,!?;:()[]{}\"'")
            for part in " ".join(value.casefold().split()).split()
            if len(part.strip(".,!?;:()[]{}\"'")) >= 2
        }

    @classmethod
    def _sparse_fallback(
        cls,
        *,
        seeds: DeploymentDiscoverySeeds,
        context_text: str,
    ) -> float:
        content_tokens = cls._tokens(context_text)
        if not content_tokens:
            return 0.0
        best = 0.0
        for seed in seeds.seeds:
            query_tokens = cls._tokens(seed.text)
            if not query_tokens:
                continue
            overlap = len(query_tokens & content_tokens) / len(query_tokens)
            best = max(best, overlap * seed.weight)
        return max(0.0, min(1.0, best))

    async def inspect(
        self,
        *,
        owner_id: str,
        character_card_id: str,
        url: str,
        seeds: DeploymentDiscoverySeeds,
    ) -> DiscoveryMediaInspection | None:
        context = await self.context_reader.inspect_public_url(
            owner_id=owner_id,
            character_card_id=character_card_id,
            url=url,
        )
        if context is None:
            return None
        context_text = self._context_text(context)
        if not context_text:
            return None

        deep_relevance: float
        reason: str
        if self.encoder is not None and seeds.semantic_text.strip():
            try:
                query_vector = self.encoder.embed_query(seeds.semantic_text)
                context_vector = self.encoder.embed_passage(context_text)
                deep_relevance = max(0.0, _cosine(query_vector, context_vector))
                reason = "existing_media_context_e5"
            except SemanticEmbeddingUnavailable:
                deep_relevance = self._sparse_fallback(
                    seeds=seeds,
                    context_text=context_text,
                )
                reason = "existing_media_context_sparse_fallback"
        else:
            deep_relevance = self._sparse_fallback(
                seeds=seeds,
                context_text=context_text,
            )
            reason = "existing_media_context_sparse_fallback"

        return DiscoveryMediaInspection(
            source_key=context.source_key,
            context_kind=context.kind,
            label=context.label[:240],
            deep_relevance=round(max(0.0, min(1.0, deep_relevance)), 6),
            reason=reason,
        )


__all__ = [
    "DiscoveryMediaContextService",
    "DiscoveryMediaInspection",
    "DiscoveryMediaInspectionService",
    "PublicMediaContextReader",
]
