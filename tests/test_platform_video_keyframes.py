import asyncio

from pydantic import SecretStr

from echo_masque.api.connector_schemas import DiscordInboundMessage
from echo_masque.live_media_enhanced import EnhancedLiveMediaContextService
from echo_masque.media_runtime import MediaAnalysis, MediaAsset
from echo_masque.persistence import Database, MediaAnalysisRepository
from echo_masque.platform_keyframes import PlatformKeyframes
from echo_masque.platform_media import PlatformMediaResolution
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


class FakePlatformResolver:
    @staticmethod
    def supports(url: str) -> bool:
        return "bilibili.com" in url

    async def resolve(self, url: str, *, source_key: str) -> PlatformMediaResolution:
        del url
        return PlatformMediaResolution(
            source_key=source_key,
            canonical_url="https://www.bilibili.com/video/BV1test",
            platform="bilibili",
            media_id="BV1test",
            title="Bilibili demo",
            uploader="Demo uploader",
            duration_seconds=40,
            media_url="https://upos.example.test/video.m4s?token=must-stay-local",
            media_ext="mp4",
            media_headers=(("Referer", "https://www.bilibili.com/"),),
            transcript="A short transcript from the public video.",
            transcript_language="zh-CN",
            transcript_source="manual",
        )


class FakeKeyframeExtractor:
    calls = 0

    async def extract(self, resolution: PlatformMediaResolution) -> PlatformKeyframes:
        self.calls += 1
        assert "must-stay-local" in resolution.media_url
        assert resolution.media_headers == (("Referer", "https://www.bilibili.com/"),)
        return PlatformKeyframes(
            source_key=resolution.source_key,
            frame_data_uris=(
                "data:image/jpeg;base64,QUFB",
                "data:image/jpeg;base64,QkJC",
            ),
            timestamps_seconds=(4.0, 20.0),
        )


class CapturingProvider:
    provider_id = "fake-media"
    model = "fake-vision"

    def __init__(self) -> None:
        self.assets: list[MediaAsset] = []

    async def analyze(self, asset: MediaAsset) -> MediaAnalysis:
        self.assets.append(asset)
        assert asset.source_uri == "https://www.bilibili.com/video/BV1test"
        assert "upos" not in asset.source_uri
        assert "must-stay-local" not in asset.source_uri
        assert len(asset.keyframe_uris) == 2
        return MediaAnalysis(
            summary="Two sampled frames show a public demonstration video.",
            visible_text="Demo",
            objects=("screen",),
            notable_details=("A screen is visible in both sampled frames.",),
            topics=("demo",),
            tone="informational",
        )


def test_bilibili_cdn_url_stays_local_and_transcript_merges_with_keyframes() -> None:
    database = Database("sqlite://")
    database.initialize()
    media_repository = MediaAnalysisRepository(database)
    provider = CapturingProvider()
    keyframes = FakeKeyframeExtractor()

    service = EnhancedLiveMediaContextService(
        media_repository=media_repository,
        credential_resolver=MediaCredentialResolver(),
        discord_bot_token=None,
        provider_factory=lambda _: provider,
        platform_resolver=FakePlatformResolver(),  # type: ignore[arg-type]
        platform_keyframe_extractor=keyframes,  # type: ignore[arg-type]
    )
    payload = DiscordInboundMessage(
        connection_id="conn-1",
        deployment_id="deployment-1",
        message_id="message-1",
        guild_id="guild-1",
        channel_id="channel-1",
        author_id="user-1",
        author_display_name="Member",
        text="看看这个 https://www.bilibili.com/video/BV1test",
    )

    result = asyncio.run(
        service.contexts_for_turn(
            owner_id="owner-1",
            character_card_id="character-1",
            payload=payload,
        )
    )

    assert result.status == "completed"
    assert len(provider.assets) == 1
    assert provider.assets[0].media_key.endswith(":platform-keyframes-v1")
    assert result.contexts[0].kind == "video"
    assert "Bilibili demo" in result.contexts[0].summary
    assert "short transcript" in result.contexts[0].visible_text
    assert keyframes.calls == 1
