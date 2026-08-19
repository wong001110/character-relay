# ruff: noqa: I001
"""No-key YouTube Discovery adapter backed by yt-dlp metadata search."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from echo_masque.discovery_contracts import DiscoveryCandidate, DiscoveryFetchRequest
from echo_masque.discovery_source_cache import DiscoverySourceQueryCache
from echo_masque.persistence.database import Database
from echo_masque.persistence.discovery_models import DiscoveryItemRecord
from echo_masque.persistence.discovery_repository import DiscoveryRepository
from echo_masque.youtube_discovery import YouTubeDiscoveryUnavailable


type YouTubeSearchFunction = Callable[[str, int], list[dict[str, Any]]]


class YouTubeNoKeyDiscoveryAdapter:
    """Read-only YouTube metadata search that requires no Google API credential."""

    source = "youtube"

    def __init__(
        self,
        *,
        database: Database,
        search_cache_seconds: int = 4 * 60 * 60,
        max_search_queries_per_session: int = 2,
        search_function: YouTubeSearchFunction | None = None,
    ) -> None:
        self.database = database
        self.search_cache_seconds = max(300, search_cache_seconds)
        self.max_search_queries_per_session = max(0, min(max_search_queries_per_session, 5))
        self.search_function = search_function or self._search_sync
        self.items = DiscoveryRepository(database)
        self.query_cache = DiscoverySourceQueryCache(database)

    @staticmethod
    def _parse_timestamp(row: dict[str, Any]) -> datetime | None:
        raw = row.get("timestamp")
        if isinstance(raw, (int, float)) and raw > 0:
            return datetime.fromtimestamp(float(raw), tz=UTC)
        upload_date = str(row.get("upload_date") or "").strip()
        if len(upload_date) == 8 and upload_date.isdigit():
            try:
                return datetime.strptime(upload_date, "%Y%m%d").replace(tzinfo=UTC)
            except ValueError:
                return None
        return None

    @staticmethod
    def _candidate_from_record(record: DiscoveryItemRecord) -> DiscoveryCandidate:
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

    def _cached(
        self,
        *,
        query: str,
        region: str,
        language: str,
    ) -> tuple[DiscoveryCandidate, ...] | None:
        hit = self.query_cache.get(
            source=self.source,
            query_kind="search",
            query=query,
            region=region,
            language=language,
        )
        if hit is None:
            return None
        if not hit.result_keys:
            return ()
        from sqlalchemy import select

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
        if any(key not in by_key for key in hit.result_keys):
            return None
        return tuple(self._candidate_from_record(by_key[key]) for key in hit.result_keys)

    async def fetch_candidates(
        self,
        request: DiscoveryFetchRequest,
    ) -> tuple[DiscoveryCandidate, ...]:
        queries = tuple(
            dict.fromkeys(
                " ".join(value.split())
                for value in request.queries
                if " ".join(value.split())
            )
        )[: self.max_search_queries_per_session]
        total_limit = max(1, min(request.limit, 50))
        values: list[DiscoveryCandidate] = []

        for query in queries:
            if len(values) >= total_limit:
                break
            cached = self._cached(
                query=query,
                region=request.region,
                language=request.language,
            )
            if cached is not None:
                values.extend(cached)
                continue
            try:
                rows = await asyncio.to_thread(
                    self.search_function,
                    query,
                    min(8, total_limit - len(values)),
                )
            except Exception as exc:
                raise YouTubeDiscoveryUnavailable(
                    f"YouTube no-key search failed: {exc}"
                ) from exc
            candidates = tuple(
                candidate
                for row in rows
                if (candidate := self._normalize(row)) is not None
            )
            stored: list[DiscoveryCandidate] = []
            keys: list[str] = []
            for candidate in candidates:
                record = self.items.upsert_item(candidate)
                stored.append(self._candidate_from_record(record))
                keys.append(record.canonical_key)
            self.query_cache.put(
                source=self.source,
                query_kind="search",
                query=query,
                region=request.region,
                language=request.language,
                result_keys=tuple(keys),
                ttl_seconds=self.search_cache_seconds,
            )
            values.extend(stored)

        deduped: list[DiscoveryCandidate] = []
        seen: set[str] = set()
        for candidate in values:
            if candidate.canonical_key in seen:
                continue
            seen.add(candidate.canonical_key)
            deduped.append(candidate)
            if len(deduped) >= total_limit:
                break
        return tuple(deduped)

    @classmethod
    def _normalize(cls, row: dict[str, Any]) -> DiscoveryCandidate | None:
        video_id = str(row.get("id") or "").strip()
        webpage = str(row.get("webpage_url") or "").strip()
        raw_url = str(row.get("url") or "").strip()
        if not video_id and "watch?v=" in webpage:
            video_id = webpage.split("watch?v=", 1)[1].split("&", 1)[0]
        if not video_id and raw_url and not raw_url.startswith("http"):
            video_id = raw_url
        if not video_id:
            return None
        url = webpage if webpage.startswith("http") else ""
        if not url and raw_url.startswith("http"):
            url = raw_url
        if not url:
            url = f"https://www.youtube.com/watch?v={video_id}"
        thumbnail = str(row.get("thumbnail") or row.get("thumbnail_url") or "").strip()
        return DiscoveryCandidate(
            source=cls.source,
            canonical_key=f"youtube:{video_id}",
            content_kind="video",
            title=str(row.get("title") or "").strip(),
            description=str(row.get("description") or "").strip(),
            creator=str(
                row.get("uploader")
                or row.get("channel")
                or row.get("channel_name")
                or ""
            ).strip(),
            url=url,
            thumbnail_url=thumbnail,
            published_at=cls._parse_timestamp(row),
            metadata={
                "video_id": video_id,
                "source_kind": "search",
                "acquisition": "yt_dlp_no_key",
            },
        )

    @staticmethod
    def _search_sync(query: str, limit: int) -> list[dict[str, Any]]:
        import yt_dlp

        bounded = max(1, min(limit, 12))
        options: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extract_flat": True,
            "playlistend": bounded,
            "socket_timeout": 15,
            "retries": 1,
            "extractor_retries": 1,
            "noplaylist": False,
        }
        with yt_dlp.YoutubeDL(options) as ydl:
            raw = ydl.extract_info(f"ytsearch{bounded}:{query}", download=False)
            info = ydl.sanitize_info(raw)
        if not isinstance(info, dict):
            return []
        entries = info.get("entries")
        if not isinstance(entries, list):
            return []
        return [
            {str(key): value for key, value in item.items()}
            for item in entries[:bounded]
            if isinstance(item, dict)
        ]


__all__ = ["YouTubeNoKeyDiscoveryAdapter", "YouTubeSearchFunction"]
