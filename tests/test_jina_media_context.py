import asyncio

from echo_masque.api.connector_schemas import DiscordInboundMessage
from echo_masque.jina_reader import JinaArticle
from echo_masque.live_media_enhanced import EnhancedLiveMediaContextService
from echo_masque.persistence import Database, MediaAnalysisRepository


class NoCredentialResolver:
    def resolve(self, **_: object) -> None:
        return None


class FakeJinaReader:
    async def read(self, url: str) -> JinaArticle:
        assert url == "https://example.com/article"
        return JinaArticle(
            final_url=url,
            title="Clean article",
            summary="The article explains how Jina supplies a concise factual summary.",
            content=(
                "The cleaned article body keeps the evidence needed for downstream follow-up "
                "questions without navigation or unrelated page chrome."
            ),
            published_time="2026-08-10T12:00:00Z",
            structured=True,
        )


class NoPlatformResolver:
    def supports(self, _: str) -> bool:
        return False


def test_jina_summary_and_clean_content_reach_media_context() -> None:
    database = Database("sqlite://")
    database.initialize()
    repository = MediaAnalysisRepository(database)
    service = EnhancedLiveMediaContextService(
        media_repository=repository,
        credential_resolver=NoCredentialResolver(),  # type: ignore[arg-type]
        discord_bot_token=None,
        jina_reader=FakeJinaReader(),  # type: ignore[arg-type]
        platform_resolver=NoPlatformResolver(),  # type: ignore[arg-type]
    )
    payload = DiscordInboundMessage(
        connection_id="conn-1",
        deployment_id="deployment-1",
        message_id="message-1",
        guild_id="guild-1",
        channel_id="channel-1",
        author_id="user-1",
        author_display_name="Member",
        text="帮我看 https://example.com/article",
    )

    result = asyncio.run(
        service.contexts_for_turn(
            owner_id="owner-1",
            character_card_id="card-1",
            payload=payload,
        )
    )

    assert result.status == "completed"
    assert result.contexts[0].kind == "article"
    assert result.contexts[0].label == "Clean article"
    assert result.contexts[0].summary.startswith("The article explains")
    assert "downstream follow-up" in result.contexts[0].visible_text
    assert "Extracted with Jina ReaderLM-v2" in result.contexts[0].notable_details
    assert (
        repository.get(
            media_key="url:https://example.com/article",
            analysis_version="article-v3",
            provider="jina-reader",
            model="readerlm-v2",
        )
        is not None
    )
