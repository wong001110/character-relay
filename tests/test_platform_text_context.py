import asyncio

from echo_masque.api.connector_schemas import DiscordInboundMessage
from echo_masque.live_media_enhanced import EnhancedLiveMediaContextService
from echo_masque.persistence import Database, MediaAnalysisRepository
from echo_masque.platform_media import PlatformMediaResolution


class NoCredentialResolver:
    def resolve(self, **_: object) -> None:
        return None


class FakePlatformResolver:
    def supports(self, url: str) -> bool:
        return "youtube.com" in url

    async def resolve(
        self,
        url: str,
        *,
        source_key: str,
    ) -> PlatformMediaResolution:
        assert url == "https://www.youtube.com/watch?v=abc123"
        assert source_key == "youtube:abc123"
        return PlatformMediaResolution(
            source_key=source_key,
            canonical_url=url,
            platform="youtube",
            media_id="abc123",
            title="Transcript-only demo",
            uploader="Example Channel",
            description="A public video about reusable media context.",
            duration_seconds=42,
            transcript="The video explains that shared context avoids duplicate analysis.",
            transcript_language="en",
            transcript_source="manual",
        )


def test_platform_transcript_is_available_without_media_key_group() -> None:
    database = Database("sqlite://")
    database.initialize()
    service = EnhancedLiveMediaContextService(
        media_repository=MediaAnalysisRepository(database),
        credential_resolver=NoCredentialResolver(),  # type: ignore[arg-type]
        discord_bot_token=None,
        platform_resolver=FakePlatformResolver(),  # type: ignore[arg-type]
    )
    payload = DiscordInboundMessage(
        connection_id="conn-1",
        deployment_id="deployment-1",
        message_id="message-1",
        guild_id="guild-1",
        channel_id="channel-1",
        author_id="user-1",
        author_display_name="Member",
        text="看这个 https://www.youtube.com/watch?v=abc123",
    )

    result = asyncio.run(
        service.contexts_for_turn(
            owner_id="owner-1",
            character_card_id="card-1",
            payload=payload,
        )
    )

    assert result.status == "completed"
    assert result.reason == "platform_text_context"
    assert result.contexts[0].kind == "video"
    assert result.contexts[0].label == "Transcript-only demo"
    assert "duplicate analysis" in result.contexts[0].visible_text
    assert "Uploader: Example Channel" in result.contexts[0].notable_details
