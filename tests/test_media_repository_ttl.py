from datetime import UTC, datetime, timedelta

from echo_masque.persistence import Database, MediaAnalysisRepository


def utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def test_custom_ttl_is_preserved_when_cache_hit_refreshes_access() -> None:
    database = Database("sqlite://")
    database.initialize()
    repository = MediaAnalysisRepository(
        database,
        ttl=timedelta(days=30),
        access_refresh_after=timedelta(hours=1),
    )
    created = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
    article_ttl = timedelta(days=7)
    repository.put(
        media_key="url:https://example.com/article",
        media_type="article",
        analysis_version="article-v3",
        provider="jina-reader",
        model="readerlm-v2",
        result_json='{"summary":"Article","visible_text":"Body"}',
        now=created,
        ttl=article_ttl,
    )

    accessed = created + timedelta(hours=2)
    record = repository.get(
        media_key="url:https://example.com/article",
        analysis_version="article-v3",
        provider="jina-reader",
        model="readerlm-v2",
        now=accessed,
        ttl=article_ttl,
    )

    assert record is not None
    assert utc(record.last_accessed_at) == accessed
    assert utc(record.expires_at) == accessed + article_ttl
