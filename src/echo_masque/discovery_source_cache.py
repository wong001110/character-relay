"""Persisted source-query cache so public Discovery API quota is shared across sessions."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import delete, select

from echo_masque.persistence.database import Database
from echo_masque.persistence.discovery_models import DiscoverySourceQueryCacheRecord


@dataclass(frozen=True, slots=True)
class DiscoverySourceCacheHit:
    source: str
    query_kind: str
    query_key: str
    result_keys: tuple[str, ...]
    fetched_at: datetime
    expires_at: datetime


class DiscoverySourceQueryCache:
    """Cache only hashes/canonical result keys; raw server interest queries are not persisted."""

    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(value.casefold().split())

    @classmethod
    def identity(
        cls,
        *,
        source: str,
        query_kind: str,
        query: str,
        region: str,
        language: str,
    ) -> tuple[str, str]:
        normalized = cls._normalize(query)
        query_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        payload = "|".join(
            (
                source.casefold().strip(),
                query_kind.casefold().strip(),
                query_hash,
                region.casefold().strip(),
                language.casefold().strip(),
            )
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest(), query_hash

    def get(
        self,
        *,
        source: str,
        query_kind: str,
        query: str = "",
        region: str = "",
        language: str = "",
        now: datetime | None = None,
    ) -> DiscoverySourceCacheHit | None:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        query_key, _ = self.identity(
            source=source,
            query_kind=query_kind,
            query=query,
            region=region,
            language=language,
        )
        with self.database.session() as session:
            record = session.scalar(
                select(DiscoverySourceQueryCacheRecord).where(
                    DiscoverySourceQueryCacheRecord.source == source.casefold().strip(),
                    DiscoverySourceQueryCacheRecord.query_key == query_key,
                )
            )
            if record is None:
                return None
            expires_at = record.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if expires_at <= current:
                return None
            try:
                decoded = json.loads(record.result_keys_json or "[]")
            except (json.JSONDecodeError, TypeError):
                decoded = []
            keys = tuple(
                dict.fromkeys(
                    str(item).strip()
                    for item in decoded
                    if isinstance(item, str) and str(item).strip()
                )
            )
            fetched_at = record.fetched_at
            if fetched_at.tzinfo is None:
                fetched_at = fetched_at.replace(tzinfo=UTC)
            return DiscoverySourceCacheHit(
                source=record.source,
                query_kind=record.query_kind,
                query_key=record.query_key,
                result_keys=keys,
                fetched_at=fetched_at,
                expires_at=expires_at,
            )

    def put(
        self,
        *,
        source: str,
        query_kind: str,
        query: str = "",
        region: str = "",
        language: str = "",
        result_keys: tuple[str, ...],
        ttl_seconds: int,
        now: datetime | None = None,
    ) -> DiscoverySourceCacheHit:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        normalized_source = source.casefold().strip()[:32]
        normalized_region = region.casefold().strip()[:16]
        normalized_language = language.casefold().strip()[:32]
        query_key, query_hash = self.identity(
            source=normalized_source,
            query_kind=query_kind,
            query=query,
            region=normalized_region,
            language=normalized_language,
        )
        keys = tuple(dict.fromkeys(key.strip() for key in result_keys if key.strip()))[:100]
        expires_at = current + timedelta(seconds=max(300, ttl_seconds))
        with self.database.session() as session:
            record = session.scalar(
                select(DiscoverySourceQueryCacheRecord).where(
                    DiscoverySourceQueryCacheRecord.source == normalized_source,
                    DiscoverySourceQueryCacheRecord.query_key == query_key,
                )
            )
            if record is None:
                record = DiscoverySourceQueryCacheRecord(
                    id=str(uuid4()),
                    source=normalized_source,
                    query_key=query_key,
                )
                session.add(record)
            record.query_kind = query_kind.casefold().strip()[:32]
            record.normalized_query_hash = query_hash
            record.region = normalized_region
            record.language = normalized_language
            record.result_keys_json = json.dumps(
                keys,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            record.result_count = len(keys)
            record.fetched_at = current
            record.expires_at = expires_at
            record.updated_at = current
            session.commit()
        return DiscoverySourceCacheHit(
            source=normalized_source,
            query_kind=query_kind,
            query_key=query_key,
            result_keys=keys,
            fetched_at=current,
            expires_at=expires_at,
        )

    def cleanup_expired(self, *, now: datetime | None = None) -> int:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        with self.database.session() as session:
            result = session.execute(
                delete(DiscoverySourceQueryCacheRecord).where(
                    DiscoverySourceQueryCacheRecord.expires_at <= current
                )
            )
            session.commit()
            return int(getattr(result, "rowcount", 0) or 0)


__all__ = ["DiscoverySourceCacheHit", "DiscoverySourceQueryCache"]
