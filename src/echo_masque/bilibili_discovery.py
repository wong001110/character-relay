"""Experimental, low-rate Bilibili public Discovery adapter backed by yt-dlp search."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from echo_masque.discovery_contracts import DiscoveryCandidate, DiscoveryFetchRequest
from echo_masque.discovery_source_cache import DiscoverySourceQueryCache
from echo_masque.persistence.database import Database
from echo_masque.persistence.discovery_models import DiscoveryItemRecord
from echo_masque.persistence.discovery_repository import DiscoveryRepository


class BilibiliDiscoveryUnavailable(RuntimeError):
    """Raised when the experimental public Bilibili source cannot return candidates."""


type BilibiliSearchFunction = Callable[[str, int], list[dict[str, Any]]]


class BilibiliDiscoveryAdapter:
    """Read-only Bilibili search with no login/cookies/account actions."""

    source = "bilibili"

    def __init__(
        self,
        *,
        database: Database,
        search_cache_seconds: int = 4 * 60 * 60,
        max_search_queries_per_session: int = 1,
        max_results_per_query: int = 6,
        search_function: BilibiliSearchFunction | None = None,
    ) -> None:
        self.database = database
        self.search_cache_seconds = max(300, search_cache_seconds)
        self.max_search_queries_per_session = max(0, min(max_search_queries_per_session, 3))
        self.max_results_per_query = max(1, min(max_results_per_query, 12))
        self.search_function = search_function or self._search_sync
        self.items = DiscoveryRepository(database)
        self.query_cache = DiscoverySourceQueryCache(database)

    @staticmethod
    def _parse_timestamp(raw: object) -> datetime | None:
        if isinstance(raw, (int, float)) and raw > 0:
            return datetime.fromtimestamp(float(raw), tz=UTC)
        value = str(raw or "").strip()
        if len(value) == 8 and value.isdigit():
            try:
                return datetime.strptime(value, "%Y%m%d").replace(tzinfo=UTC)
            except ValueError:
                return None
        return None

    @staticmethod
    def _candidate_from_record(record: DiscoveryItemRecord) -> DiscoveryCandidate:
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
        )

    def _cached(self, query: str) -> tuple[DiscoveryCandidate, ...] | None:
        hit = self.query_cache.get(source=self.source, query_kind="search", query=query)
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
        self, request: DiscoveryFetchRequest
    ) -> tuple[DiscoveryCandidate, ...]:
        queries = tuple(
            dict.fromkeys(
                " ".join(value.split())
                for value in request.queries
                if " ".join(value.split())
            )
        )[: self.max_search_queries_per_session]
        total_limit = max(1, min(request.limit, 30))
        values: list[DiscoveryCandidate] = []
        for query in queries:
            if len(values) >= total_limit:
                break
            cached = self._cached(query)
            if cached is not None:
                values.extend(cached)
                continue
            try:
                rows = await asyncio.to_thread(
                    self.search_function,
                    query,
                    min(self.max_results_per_query, total_limit - len(values)),
                )
            except Exception as exc:
                raise BilibiliDiscoveryUnavailable(
                    f"Bilibili public search failed: {exc}"
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
        raw_id = str(row.get("id") or row.get("bvid") or "").strip()
        webpage = str(row.get("webpage_url") or row.get("url") or "").strip()
        if raw_id.startswith("BV"):
            canonical_id = raw_id
        elif "/video/BV" in webpage:
            canonical_id = "BV" + webpage.split("/video/BV", 1)[1].split("/", 1)[0].split("?", 1)[0]
        else:
            canonical_id = raw_id
        if not canonical_id:
            return None
        url = webpage if webpage.startswith("http") else f"https://www.bilibili.com/video/{canonical_id}"
        thumbnail = str(row.get("thumbnail") or row.get("thumbnail_url") or "").strip()
        return DiscoveryCandidate(
            source=cls.source,
            canonical_key=f"bilibili:{canonical_id}",
            content_kind="video",
            title=str(row.get("title") or "").strip(),
            description=str(row.get("description") or "").strip(),
            creator=str(row.get("uploader") or row.get("channel") or row.get("creator") or "").strip(),
            url=url,
            thumbnail_url=thumbnail,
            published_at=cls._parse_timestamp(row.get("timestamp") or row.get("upload_date")),
            metadata={"video_id": canonical_id, "source_kind": "search", "experimental": True},
        )

    @staticmethod
    def _search_sync(query: str, limit: int) -> list[dict[str, Any]]:
        import yt_dlp

        options: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extract_flat": True,
            "playlistend": max(1, min(limit, 12)),
            "socket_timeout": 15,
            "retries": 1,
            "extractor_retries": 1,
            "noplaylist": False,
        }
        search_url = f"bilisearch{max(1, min(limit, 12))}:{query}"
        with yt_dlp.YoutubeDL(options) as ydl:
            raw = ydl.extract_info(search_url, download=False)
            info = ydl.sanitize_info(raw)
        if not isinstance(info, dict):
            return []
        entries = info.get("entries")
        if not isinstance(entries, list):
            return []
        return [
            {str(key): value for key, value in item.items()}
            for item in entries[:limit]
            if isinstance(item, dict)
        ]


__all__ = ["BilibiliDiscoveryAdapter", "BilibiliDiscoveryUnavailable"]
