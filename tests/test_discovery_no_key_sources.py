import asyncio
from pathlib import Path

from echo_masque.config import Settings
from echo_masque.discovery_contracts import DiscoveryFetchRequest
from echo_masque.persistence.database import Database
from echo_masque.youtube_no_key_discovery import YouTubeNoKeyDiscoveryAdapter


def test_youtube_no_key_adapter_searches_metadata_and_reuses_cache(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'youtube-no-key.db'}")
    database.initialize()
    calls: list[str] = []

    def search(query: str, limit: int) -> list[dict[str, object]]:
        calls.append(query)
        video_id = "robot-1" if "robot" in query else "agent-1"
        return [
            {
                "id": video_id,
                "title": query,
                "description": f"Description for {query}",
                "uploader": "Maker",
                "webpage_url": f"https://www.youtube.com/watch?v={video_id}",
                "thumbnail": f"https://img.example/{video_id}.jpg",
                "timestamp": 1787040000,
            }
        ][:limit]

    adapter = YouTubeNoKeyDiscoveryAdapter(
        database=database,
        search_function=search,
        max_search_queries_per_session=2,
    )
    request = DiscoveryFetchRequest(
        queries=("desktop robot", "AI agent", "ignored third query"),
        limit=10,
        include_popular=True,
    )

    first = asyncio.run(adapter.fetch_candidates(request))
    assert [item.canonical_key for item in first] == [
        "youtube:robot-1",
        "youtube:agent-1",
    ]
    assert all(item.metadata.get("acquisition") == "yt_dlp_no_key" for item in first)
    assert calls == ["desktop robot", "AI agent"]

    second = asyncio.run(adapter.fetch_candidates(request))
    assert [item.canonical_key for item in second] == [item.canonical_key for item in first]
    assert calls == ["desktop robot", "AI agent"]


def test_bilibili_experimental_source_is_available_without_env_opt_in() -> None:
    settings = Settings(environment="test")
    assert settings.youtube_data_api_key is None
    assert settings.bilibili_discovery_experimental_enabled is True
