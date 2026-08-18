"""Official YouTube Data API adapter for shared Character Discovery candidates."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import SecretStr
from sqlalchemy import select

from echo_masque.discovery_contracts import DiscoveryCandidate, DiscoveryFetchRequest
from echo_masque.discovery_source_cache import DiscoverySourceQueryCache
from echo_masque.persistence.database import Database
from echo_masque.persistence.discovery_models import DiscoveryItemRecord
from echo_masque.persistence.discovery_repository import DiscoveryRepository

_YOUTUBE_API = "https://www.googleapis.com/youtube/v3"


class YouTubeDiscoveryUnavailable(RuntimeError):
    """Raised when the public YouTube source cannot produce fresh candidates."""


class YouTubeDiscoveryAdapter:
    """Quota-conscious public YouTube collector with a persisted cross-Deployment query cache."""

    source = "youtube"

    def __init__(
        self,
        *,
        database: Database,
        api_key: SecretStr,
        search_cache_seconds: int = 4 * 60 * 60,
        popular_cache_seconds: int = 60 * 60,
        max_search_queries_per_session: int = 2,
        http_transport: httpx.AsyncBaseTransport | None = None,
        base_url: str = _YOUTUBE_API,
    ) -> None:
        self.database = database
        self.api_key = api_key
        self.search_cache_seconds = max(300, search_cache_seconds)
        self.popular_cache_seconds = max(300, popular_cache_seconds)
        self.max_search_queries_per_session = max(0, min(max_search_queries_per_session, 5))
        self.http_transport = http_transport
        self.base_url = base_url.rstrip("/")
        self.items = DiscoveryRepository(database)
        self.query_cache = DiscoverySourceQueryCache(database)

    @staticmethod
    def _parse_datetime(value: object) -> datetime | None:
        if not isinstance(value, str) or not value.strip():
            return None
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)

    @staticmethod
    def _thumbnail(snippet: dict[str, Any]) -> str:
        thumbnails = snippet.get("thumbnails")
        if not isinstance(thumbnails, dict):
            return ""
        for name in ("maxres", "standard", "high", "medium", "default"):
            raw = thumbnails.get(name)
            if isinstance(raw, dict) and isinstance(raw.get("url"), str):
                return raw["url"].strip()
        return ""

    @staticmethod
    def _candidate_from_item(record: DiscoveryItemRecord) -> DiscoveryCandidate:
        try:
            metadata = json.loads(record.metadata_json or "{}")
        except (json.JSONDecodeError, TypeError):
            metadata = {}
        if not isinstance(metadata, dict):
            metadata = {}
        return DiscoveryCandidate(
            source=record.source,
            canonical_key=record.canonical_key,
            content_kind=record.content_kind,
            title=record.title,
            description=record.description,
            creator=record.creator,
            url=record.url,
            thumbnail_url=record.thumbnail_url,
            published_at=record.published_at,
            metadata=metadata,
        )

    def _cached_candidates(
        self,
        *,
        query_kind: str,
        query: str,
        region: str,
        language: str,
    ) -> tuple[DiscoveryCandidate, ...] | None:
        hit = self.query_cache.get(
            source=self.source,
            query_kind=query_kind,
            query=query,
            region=region,
            language=language,
        )
        if hit is None:
            return None
        if not hit.result_keys:
            return ()
        with self.database.session() as session:
            rows = list(
                session.scalars(
                    select(DiscoveryItemRecord).where(
                        DiscoveryItemRecord.source == self.source,
                        DiscoveryItemRecord.canonical_key.in_(hit.result_keys),
                    )
                )
            )
        by_key = {row.canonical_key: row for row in rows}
        candidates = tuple(
            self._candidate_from_item(by_key[key])
            for key in hit.result_keys
            if key in by_key
        )
        # A partial shared-item cache should be refreshed rather than silently returning a
        # different set from the persisted source snapshot.
        return candidates if len(candidates) == len(hit.result_keys) else None

    async def fetch_candidates(
        self,
        request: DiscoveryFetchRequest,
    ) -> tuple[DiscoveryCandidate, ...]:
        queries = tuple(
            dict.fromkeys(
                " ".join(item.split())
                for item in request.queries
                if " ".join(item.split())
            )
        )[: self.max_search_queries_per_session]
        total_limit = max(1, min(request.limit, 50))
        candidates: list[DiscoveryCandidate] = []

        for query in queries:
            if len(candidates) >= total_limit:
                break
            candidates.extend(
                await self._search(
                    query=query,
                    region=request.region,
                    language=request.language,
                    limit=min(8, total_limit - len(candidates)),
                )
            )

        if request.include_popular and len(candidates) < total_limit:
            candidates.extend(
                await self._popular(
                    region=request.region,
                    language=request.language,
                    limit=min(12, total_limit - len(candidates)),
                )
            )

        deduped: list[DiscoveryCandidate] = []
        seen: set[str] = set()
        for candidate in candidates:
            if candidate.canonical_key in seen:
                continue
            seen.add(candidate.canonical_key)
            deduped.append(candidate)
            if len(deduped) >= total_limit:
                break
        return tuple(deduped)

    async def _search(
        self,
        *,
        query: str,
        region: str,
        language: str,
        limit: int,
    ) -> tuple[DiscoveryCandidate, ...]:
        cached = self._cached_candidates(
            query_kind="search",
            query=query,
            region=region,
            language=language,
        )
        if cached is not None:
            return cached[:limit]
        params: dict[str, str | int] = {
            "key": self.api_key.get_secret_value(),
            "part": "snippet",
            "q": query,
            "type": "video",
            "order": "relevance",
            "safeSearch": "moderate",
            "maxResults": max(1, min(limit, 50)),
        }
        if region.strip():
            params["regionCode"] = region.strip().upper()
        if language.strip():
            params["relevanceLanguage"] = language.strip()
        payload = await self._get("/search", params=params)
        values = payload.get("items")
        rows = values if isinstance(values, list) else []
        candidates: list[DiscoveryCandidate] = []
        for raw in rows:
            candidate = self._search_candidate(raw, query=query)
            if candidate is not None:
                candidates.append(candidate)
        stored = self._store_and_cache(
            candidates=tuple(candidates),
            query_kind="search",
            query=query,
            region=region,
            language=language,
            ttl_seconds=self.search_cache_seconds,
        )
        return stored[:limit]

    async def _popular(
        self,
        *,
        region: str,
        language: str,
        limit: int,
    ) -> tuple[DiscoveryCandidate, ...]:
        cached = self._cached_candidates(
            query_kind="popular",
            query="",
            region=region,
            language=language,
        )
        if cached is not None:
            return cached[:limit]
        params: dict[str, str | int] = {
            "key": self.api_key.get_secret_value(),
            "part": "snippet,contentDetails,statistics",
            "chart": "mostPopular",
            "maxResults": max(1, min(limit, 50)),
        }
        if region.strip():
            params["regionCode"] = region.strip().upper()
        payload = await self._get("/videos", params=params)
        values = payload.get("items")
        rows = values if isinstance(values, list) else []
        candidates: list[DiscoveryCandidate] = []
        for raw in rows:
            candidate = self._popular_candidate(raw)
            if candidate is not None:
                candidates.append(candidate)
        stored = self._store_and_cache(
            candidates=tuple(candidates),
            query_kind="popular",
            query="",
            region=region,
            language=language,
            ttl_seconds=self.popular_cache_seconds,
        )
        return stored[:limit]

    async def _get(
        self,
        path: str,
        *,
        params: dict[str, str | int],
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(15.0),
            transport=self.http_transport,
            follow_redirects=False,
            headers={"User-Agent": "CharacterRelay/0.2 Discovery"},
        ) as client:
            try:
                response = await client.get(f"{self.base_url}{path}", params=params)
            except httpx.HTTPError as exc:
                raise YouTubeDiscoveryUnavailable(f"YouTube request failed: {exc}") from exc
        if response.is_error:
            raise YouTubeDiscoveryUnavailable(
                f"YouTube Data API returned HTTP {response.status_code}."
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise YouTubeDiscoveryUnavailable("YouTube Data API returned invalid JSON.") from exc
        if not isinstance(payload, dict):
            raise YouTubeDiscoveryUnavailable("YouTube Data API returned an invalid payload.")
        return payload

    def _search_candidate(
        self,
        raw: object,
        *,
        query: str,
    ) -> DiscoveryCandidate | None:
        if not isinstance(raw, dict):
            return None
        identity = raw.get("id")
        snippet = raw.get("snippet")
        if not isinstance(identity, dict) or not isinstance(snippet, dict):
            return None
        video_id = identity.get("videoId")
        if not isinstance(video_id, str) or not video_id.strip():
            return None
        value = video_id.strip()
        return DiscoveryCandidate(
            source=self.source,
            canonical_key=f"youtube:{value}",
            content_kind="video",
            title=str(snippet.get("title") or "").strip(),
            description=str(snippet.get("description") or "").strip(),
            creator=str(snippet.get("channelTitle") or "").strip(),
            url=f"https://www.youtube.com/watch?v={value}",
            thumbnail_url=self._thumbnail(snippet),
            published_at=self._parse_datetime(snippet.get("publishedAt")),
            metadata={
                "video_id": value,
                "source_kind": "search",
                "query_hash": __import__("hashlib").sha256(
                    " ".join(query.casefold().split()).encode("utf-8")
                ).hexdigest(),
                "channel_id": str(snippet.get("channelId") or ""),
            },
        )

    def _popular_candidate(self, raw: object) -> DiscoveryCandidate | None:
        if not isinstance(raw, dict):
            return None
        video_id = raw.get("id")
        snippet = raw.get("snippet")
        if not isinstance(video_id, str) or not video_id.strip() or not isinstance(snippet, dict):
            return None
        value = video_id.strip()
        statistics = raw.get("statistics") if isinstance(raw.get("statistics"), dict) else {}
        content_details = (
            raw.get("contentDetails") if isinstance(raw.get("contentDetails"), dict) else {}
        )
        return DiscoveryCandidate(
            source=self.source,
            canonical_key=f"youtube:{value}",
            content_kind="video",
            title=str(snippet.get("title") or "").strip(),
            description=str(snippet.get("description") or "").strip(),
            creator=str(snippet.get("channelTitle") or "").strip(),
            url=f"https://www.youtube.com/watch?v={value}",
            thumbnail_url=self._thumbnail(snippet),
            published_at=self._parse_datetime(snippet.get("publishedAt")),
            metadata={
                "video_id": value,
                "source_kind": "popular",
                "channel_id": str(snippet.get("channelId") or ""),
                "duration": str(content_details.get("duration") or ""),
                "view_count": str(statistics.get("viewCount") or ""),
                "like_count": str(statistics.get("likeCount") or ""),
                "comment_count": str(statistics.get("commentCount") or ""),
            },
        )

    def _store_and_cache(
        self,
        *,
        candidates: tuple[DiscoveryCandidate, ...],
        query_kind: str,
        query: str,
        region: str,
        language: str,
        ttl_seconds: int,
    ) -> tuple[DiscoveryCandidate, ...]:
        stored: list[DiscoveryCandidate] = []
        keys: list[str] = []
        for candidate in candidates:
            record = self.items.upsert_item(candidate)
            stored.append(self._candidate_from_item(record))
            keys.append(record.canonical_key)
        self.query_cache.put(
            source=self.source,
            query_kind=query_kind,
            query=query,
            region=region,
            language=language,
            result_keys=tuple(keys),
            ttl_seconds=ttl_seconds,
        )
        return tuple(stored)


__all__ = ["YouTubeDiscoveryAdapter", "YouTubeDiscoveryUnavailable"]
