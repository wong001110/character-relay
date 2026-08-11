import asyncio

from pydantic import SecretStr

from echo_masque.api.connector_schemas import DiscordInboundMessage
from echo_masque.jina_reader import JinaArticle
from echo_masque.live_media_enhanced import EnhancedLiveMediaContextService
from echo_masque.persistence import Database, MediaAnalysisRepository
from echo_masque.provider_credentials import ResolvedProviderCredential


class MediaCredentialResolver:
    def resolve(
        self,
        *,
        owner_id: str,
        character_card_id: str,
        capability: str,
    ) -> ResolvedProviderCredential | None:
        del owner_id, character_card_id
        if capability != "media":
            return None
        return ResolvedProviderCredential(
            key_group_id="kg-media",
            provider="openrouter",
            base_url="https://openrouter.ai/api/v1",
            model="xiaomi/mimo-v2.5",
            api_key=SecretStr("test-key"),
        )


class UnavailablePlatformResolver:
    @staticmethod
    def supports(url: str) -> bool:
        return "bilibili.com" in url

    async def resolve(self, url: str, *, source_key: str):
        del url, source_key
        return None


class FakeJinaReader:
    calls = 0

    async def read(self, url: str) -> JinaArticle:
        self.calls += 1
        return JinaArticle(
            final_url=url,
            title="Bilibili page fallback",
            summary="The public page describes a demonstration video.",
            content="Fallback page content remains available when playurl extraction is blocked.",
            structured=True,
        )


def test_failed_bilibili_platform_resolution_uses_page_context_not_vision() -> None:
    database = Database("sqlite://")
    database.initialize()
    media_repository = MediaAnalysisRepository(database)
    provider_factory_calls = 0

    def provider_factory(_: ResolvedProviderCredential):
        nonlocal provider_factory_calls
        provider_factory_calls += 1
        raise AssertionError("Vision provider must not receive an unresolved Bilibili page URL")

    jina = FakeJinaReader()
    service = EnhancedLiveMediaContextService(
        media_repository=media_repository,
        credential_resolver=MediaCredentialResolver(),
        discord_bot_token=None,
        provider_factory=provider_factory,
        jina_reader=jina,  # type: ignore[arg-type]
        platform_resolver=UnavailablePlatformResolver(),  # type: ignore[arg-type]
    )
    payload = DiscordInboundMessage(
        connection_id="conn-1",
        deployment_id="deployment-1",
        message_id="message-1",
        guild_id="guild-1",
        channel_id="channel-1",
        author_id="user-1",
        author_display_name="Member",
        text="看看这个 https://www.bilibili.com/video/BV1abc123",
    )

    result = asyncio.run(
        service.contexts_for_turn(
            owner_id="owner-1",
            character_card_id="character-1",
            payload=payload,
        )
    )

    assert result.status == "completed"
    assert result.contexts[0].kind == "article"
    assert result.contexts[0].summary == "The public page describes a demonstration video."
    assert "playurl extraction is blocked" in result.contexts[0].visible_text
    assert jina.calls == 1
    assert provider_factory_calls == 0
