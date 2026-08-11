"""Discover genuinely free OpenRouter image models with an anime-first preference.

The full catalog is cached to avoid needless provider traffic. Before a generated image is
actually requested, the selected provider endpoint is re-checked so stale catalog data cannot
silently turn automatic free mode into a paid request.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from time import monotonic
from typing import Any
from urllib.parse import quote

import httpx

from echo_masque.image_generation import ImageGenerationRequest, ImageGenerationResult
from echo_masque.provider_credentials import ResolvedProviderCredential
from echo_masque.providers.openrouter_image import OpenRouterImageGenerationProvider

AUTO_FREE_ANIME_MODEL = "auto:openrouter-free-anime"
_DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
_CACHE_TTL_SECONDS = 6 * 60 * 60
_MAX_CONCURRENT_ENDPOINT_LOOKUPS = 6

# This is a preference heuristic, not a claim that one family is universally better. Explicit
# anime/manga metadata wins; known art-oriented family names only break otherwise weak ties.
_STYLE_WEIGHTS: tuple[tuple[str, int], ...] = (
    ("animagine", 120),
    ("noobai", 115),
    ("illustrious", 110),
    ("anime", 100),
    ("manga", 95),
    ("pony", 80),
    ("illustration", 65),
    ("illustrative", 60),
    ("character", 45),
    ("stylized", 42),
    ("2d", 40),
    ("cartoon", 28),
    ("art", 18),
    ("qwen-image", 24),
    ("seedream", 20),
    ("flux", 18),
)


class OpenRouterImageScoutError(RuntimeError):
    """Raised when OpenRouter model discovery cannot be completed safely."""


@dataclass(frozen=True, slots=True)
class ImageModelCandidate:
    model_id: str
    name: str
    description: str
    style_score: int
    style_matches: tuple[str, ...]
    free_endpoint_count: int
    provider_names: tuple[str, ...]
    provider_tags: tuple[str, ...]
    created: int = 0


@dataclass(frozen=True, slots=True)
class ImageModelScoutResult:
    selected_model: str | None
    candidates: tuple[ImageModelCandidate, ...]
    checked_at: datetime
    total_image_models: int
    inspected_models: int
    from_cache: bool = False


@dataclass(frozen=True, slots=True)
class _CacheEntry:
    expires_at: float
    result: ImageModelScoutResult


class OpenRouterImageModelScout:
    """Inspect OpenRouter image endpoints and choose a zero-cost anime-friendly model."""

    def __init__(
        self,
        *,
        cache_ttl_seconds: int = _CACHE_TTL_SECONDS,
        http_transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.cache_ttl_seconds = max(60, cache_ttl_seconds)
        self.http_transport = http_transport
        self._cache: dict[str, _CacheEntry] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def discover(
        self,
        credential: ResolvedProviderCredential,
        *,
        force_refresh: bool = False,
    ) -> ImageModelScoutResult:
        if credential.provider.casefold().strip() != "openrouter":
            raise OpenRouterImageScoutError(
                "Automatic free image-model discovery currently requires "
                "an OpenRouter Key Group."
            )

        cache_key = credential.key_group_id
        now = monotonic()
        cached = self._cache.get(cache_key)
        if not force_refresh and cached is not None and cached.expires_at > now:
            return replace(cached.result, from_cache=True)

        lock = self._locks.setdefault(cache_key, asyncio.Lock())
        async with lock:
            now = monotonic()
            cached = self._cache.get(cache_key)
            if not force_refresh and cached is not None and cached.expires_at > now:
                return replace(cached.result, from_cache=True)
            result = await self._fetch(credential)
            self._cache[cache_key] = _CacheEntry(
                expires_at=monotonic() + self.cache_ttl_seconds,
                result=result,
            )
            if len(self._cache) > 200:
                self._cache = {
                    key: value
                    for key, value in self._cache.items()
                    if value.expires_at > now
                }
            return result

    async def validate_candidate(
        self,
        credential: ResolvedProviderCredential,
        candidate: ImageModelCandidate,
    ) -> str:
        """Re-check the exact pinned endpoint immediately before a generated image request."""

        if credential.provider.casefold().strip() != "openrouter":
            raise OpenRouterImageScoutError(
                "Automatic free image-model validation requires an OpenRouter Key Group."
            )
        if not candidate.provider_tags:
            raise OpenRouterImageScoutError(
                "The selected free image endpoint no longer has a pinnable provider tag."
            )
        provider_tag = candidate.provider_tags[0]
        base_url = credential.base_url.strip() or _DEFAULT_OPENROUTER_BASE_URL
        headers = {
            "Authorization": f"Bearer {credential.api_key.get_secret_value()}",
            "Accept": "application/json",
        }
        try:
            async with httpx.AsyncClient(
                base_url=base_url.rstrip("/") + "/",
                headers=headers,
                timeout=httpx.Timeout(8.0),
                transport=self.http_transport,
                follow_redirects=True,
            ) as client:
                response = await client.get(self._endpoint_path(candidate.model_id))
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise OpenRouterImageScoutError(
                "Could not re-check the selected free image endpoint before generation."
            ) from exc
        raw_endpoints = payload.get("endpoints", []) if isinstance(payload, dict) else []
        for endpoint in raw_endpoints:
            if not isinstance(endpoint, dict):
                continue
            tag = endpoint.get("provider_tag")
            if not isinstance(tag, str) or tag.strip() != provider_tag:
                continue
            if self._endpoint_is_completely_free(endpoint):
                return provider_tag
        raise OpenRouterImageScoutError(
            "The selected OpenRouter image endpoint is no longer verified as free."
        )

    async def _fetch(self, credential: ResolvedProviderCredential) -> ImageModelScoutResult:
        base_url = credential.base_url.strip() or _DEFAULT_OPENROUTER_BASE_URL
        headers = {
            "Authorization": f"Bearer {credential.api_key.get_secret_value()}",
            "Accept": "application/json",
        }
        try:
            async with httpx.AsyncClient(
                base_url=base_url.rstrip("/") + "/",
                headers=headers,
                timeout=httpx.Timeout(12.0),
                transport=self.http_transport,
                follow_redirects=True,
            ) as client:
                response = await client.get("images/models")
                response.raise_for_status()
                payload = response.json()
                raw_models = payload.get("data", []) if isinstance(payload, dict) else []
                models = [item for item in raw_models if isinstance(item, dict)]
                semaphore = asyncio.Semaphore(_MAX_CONCURRENT_ENDPOINT_LOOKUPS)

                async def inspect(item: dict[str, Any]) -> ImageModelCandidate | None:
                    async with semaphore:
                        return await self._inspect_model(client, item)

                inspected = await asyncio.gather(
                    *(inspect(item) for item in models),
                    return_exceptions=True,
                )
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise OpenRouterImageScoutError(
                "OpenRouter image-model discovery failed."
            ) from exc

        candidates = [item for item in inspected if isinstance(item, ImageModelCandidate)]
        candidates.sort(
            key=lambda item: (
                -item.style_score,
                -item.free_endpoint_count,
                -item.created,
                item.name.casefold(),
            )
        )
        return ImageModelScoutResult(
            selected_model=candidates[0].model_id if candidates else None,
            candidates=tuple(candidates[:12]),
            checked_at=datetime.now(UTC),
            total_image_models=len(models),
            inspected_models=len(inspected),
        )

    async def _inspect_model(
        self,
        client: httpx.AsyncClient,
        model: dict[str, Any],
    ) -> ImageModelCandidate | None:
        model_id = str(model.get("id", "")).strip()
        if not model_id:
            return None
        endpoint_path = str(model.get("endpoints", "")).strip() or self._endpoint_path(model_id)
        try:
            response = await client.get(endpoint_path)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError, TypeError):
            return None
        raw_endpoints = payload.get("endpoints", []) if isinstance(payload, dict) else []
        endpoints = [item for item in raw_endpoints if isinstance(item, dict)]
        # A free endpoint is only safe for automatic use when OpenRouter exposes a provider_tag.
        # Runtime pins to that exact tag and disables fallbacks so another paid endpoint cannot
        # be selected for the same model ID.
        free_endpoints = [
            item
            for item in endpoints
            if self._endpoint_is_completely_free(item)
            and isinstance(item.get("provider_tag"), str)
            and item["provider_tag"].strip()
        ]
        if not free_endpoints:
            return None

        name = str(model.get("name", model_id)).strip() or model_id
        description = str(model.get("description", "")).strip()
        style_score, matches = self._style_score(model_id, name, description)
        providers = tuple(
            dict.fromkeys(
                item["provider_name"].strip()
                for item in free_endpoints
                if isinstance(item.get("provider_name"), str)
                and item["provider_name"].strip()
            )
        )
        provider_tags = tuple(
            dict.fromkeys(item["provider_tag"].strip() for item in free_endpoints)
        )
        created_raw = model.get("created", 0)
        created = int(created_raw) if isinstance(created_raw, (int, float)) else 0
        return ImageModelCandidate(
            model_id=model_id,
            name=name,
            description=description,
            style_score=style_score,
            style_matches=matches,
            free_endpoint_count=len(free_endpoints),
            provider_names=providers,
            provider_tags=provider_tags,
            created=created,
        )

    @staticmethod
    def _endpoint_path(model_id: str) -> str:
        author, separator, slug = model_id.partition("/")
        if not separator or not author or not slug:
            raise OpenRouterImageScoutError("OpenRouter image model ID is not routable.")
        return f"/api/v1/images/models/{quote(author, safe='')}/{quote(slug, safe='')}/endpoints"

    @staticmethod
    def _endpoint_is_completely_free(endpoint: dict[str, Any]) -> bool:
        raw_pricing = endpoint.get("pricing", [])
        if not isinstance(raw_pricing, list) or not raw_pricing:
            return False
        saw_price = False
        for item in raw_pricing:
            if not isinstance(item, dict) or "cost_usd" not in item:
                return False
            try:
                cost = Decimal(str(item["cost_usd"]))
            except (InvalidOperation, ValueError, TypeError):
                return False
            saw_price = True
            if cost != 0:
                return False
        return saw_price

    @staticmethod
    def _style_score(
        model_id: str,
        name: str,
        description: str,
    ) -> tuple[int, tuple[str, ...]]:
        haystack = " ".join((model_id, name, description)).casefold()
        score = 0
        matches: list[str] = []
        for keyword, weight in _STYLE_WEIGHTS:
            if keyword in haystack:
                score += weight
                matches.append(keyword)
        return score, tuple(matches[:6])


class AutomaticFreeAnimeImageProvider:
    """Resolve one free image endpoint at call time, with no paid fallback."""

    def __init__(
        self,
        credential: ResolvedProviderCredential,
        *,
        scout: OpenRouterImageModelScout | None = None,
    ) -> None:
        self.credential = credential
        self.scout = scout or default_openrouter_image_model_scout

    @property
    def provider_id(self) -> str:
        return "openrouter"

    @property
    def model(self) -> str:
        return AUTO_FREE_ANIME_MODEL

    async def _selected_candidate(self) -> tuple[ImageModelCandidate, str]:
        result = await self.scout.discover(self.credential)
        if result.selected_model is None or not result.candidates:
            raise ValueError(
                "No truly free OpenRouter image-generation model is available right now. "
                "Character Relay will not fall back to a paid model automatically."
            )
        selected = result.candidates[0]
        if selected.model_id != result.selected_model or not selected.provider_tags:
            raise ValueError("Free image-model discovery did not return a pinnable endpoint.")
        try:
            provider_tag = await self.scout.validate_candidate(self.credential, selected)
        except OpenRouterImageScoutError:
            # The cached candidate changed. Refresh the full shortlist once so another newly-free
            # anime-friendly model can take over without requiring a manual Settings visit.
            refreshed = await self.scout.discover(self.credential, force_refresh=True)
            if refreshed.selected_model is None or not refreshed.candidates:
                raise ValueError(
                    "No safely verified free OpenRouter image endpoint is available right now."
                )
            selected = refreshed.candidates[0]
            if selected.model_id != refreshed.selected_model or not selected.provider_tags:
                raise ValueError("Free image-model refresh did not return a pinnable endpoint.")
            try:
                provider_tag = await self.scout.validate_candidate(self.credential, selected)
            except OpenRouterImageScoutError as exc:
                raise ValueError(
                    "The refreshed OpenRouter image endpoint could not be verified as free."
                ) from exc
        return selected, provider_tag

    async def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        selected, provider_tag = await self._selected_candidate()
        credential = resolve_automatic_image_model(
            self.credential,
            selected.model_id,
        )
        provider = OpenRouterImageGenerationProvider(
            provider_id="openrouter",
            api_key=credential.api_key,
            model=credential.model,
            base_url=credential.base_url.strip() or _DEFAULT_OPENROUTER_BASE_URL,
            provider_only=(provider_tag,),
            allow_fallbacks=False,
        )
        return await provider.generate(request)


def resolve_automatic_image_model(
    credential: ResolvedProviderCredential,
    selected_model: str,
) -> ResolvedProviderCredential:
    """Return a concrete credential copy after automatic discovery selected a model."""

    return replace(credential, model=selected_model)


default_openrouter_image_model_scout = OpenRouterImageModelScout()


__all__ = [
    "AUTO_FREE_ANIME_MODEL",
    "AutomaticFreeAnimeImageProvider",
    "ImageModelCandidate",
    "ImageModelScoutResult",
    "OpenRouterImageModelScout",
    "OpenRouterImageScoutError",
    "default_openrouter_image_model_scout",
    "resolve_automatic_image_model",
]
