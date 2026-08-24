import asyncio

import httpx
from pydantic import SecretStr

from echo_masque.api.connector_schemas import DiscordInboundMessage
from echo_masque.live_media_enhanced import EnhancedLiveMediaContextService
from echo_masque.media_runtime import MediaAnalysis, MediaAsset
from echo_masque.network_safety import PublicUrlGuard
from echo_masque.persistence import Database, MediaAnalysisRepository
from echo_masque.provider_credentials import ResolvedProviderCredential


async def public_resolver(_: str) -> tuple[str, ...]:
    return ("8.8.8.8",)


class FakeCredentialResolver:
    def resolve(
        self,
        *,
        owner_id: str,
        character_card_id: str,
        capability: str,
    ) -> ResolvedProviderCredential | None:
        del owner_id
        if capability != "media":
            return None
        return ResolvedProviderCredential(
            key_group_id=f"kg-{character_card_id}",
            provider="openrouter",
            base_url="https://openrouter.ai/api/v1",
            model="test-vision",
            api_key=SecretStr("test-key"),
        )


class FakeMediaProvider:
    provider_id = "openrouter"
    model = "test-vision"

    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    async def analyze(self, asset: MediaAsset) -> MediaAnalysis:
        self.calls.append(asset.media_key)
        return MediaAnalysis(
            summary=f"Observed source asset {asset.media_key.rsplit(':', 1)[-1]}",
            objects=("reference image",),
        )


def test_fixupx_source_enrichment_perceives_all_four_original_images() -> None:
    database = Database("sqlite://")
    database.initialize()
    media_repository = MediaAnalysisRepository(database)
    provider_calls: list[str] = []
    network_calls = {"api": 0, "image": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.fxtwitter.com":
            network_calls["api"] += 1
            return httpx.Response(
                200,
                json={
                    "code": 200,
                    "status": {
                        "type": "status",
                        "id": "2091682495720722697",
                        "text": "Mejor me ahorro lo que pienso",
                        "author": {
                            "name": "Makalister",
                            "screen_name": "__Makalister__",
                        },
                        "media": {
                            "all": [
                                {
                                    "id": f"photo-{index}",
                                    "type": "photo",
                                    "url": f"https://8.8.8.8/photo-{index}.jpg",
                                    "width": 1200,
                                    "height": 1600,
                                }
                                for index in range(1, 5)
                            ]
                        },
                    },
                },
            )
        if request.url.host == "8.8.8.8":
            network_calls["image"] += 1
            return httpx.Response(
                200,
                content=f"image:{request.url.path}".encode(),
                headers={"content-type": "image/jpeg"},
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    def provider_factory(_: ResolvedProviderCredential) -> FakeMediaProvider:
        return FakeMediaProvider(provider_calls)

    service = EnhancedLiveMediaContextService(
        media_repository=media_repository,
        credential_resolver=FakeCredentialResolver(),
        discord_bot_token=None,
        provider_factory=provider_factory,
        http_transport=httpx.MockTransport(handler),
        url_guard=PublicUrlGuard(resolver=public_resolver),
    )
    payload = DiscordInboundMessage(
        connection_id="connection-1",
        deployment_id="deployment-1",
        message_id="message-1",
        guild_id="guild-1",
        channel_id="channel-1",
        author_id="user-1",
        author_display_name="Member",
        text=(
            "参考这张试试 "
            "https://fixupx.com/__makalister__/status/2091682495720722697?s=46"
        ),
    )

    result = asyncio.run(
        service.contexts_for_turn(
            owner_id="owner-1",
            character_card_id="card-1",
            payload=payload,
        )
    )

    assert result.status == "completed"
    assert result.reason == "shared_content_context"
    assert len(result.contexts) == 5
    assert result.contexts[0].kind == "article"
    assert result.contexts[0].summary == "Mejor me ahorro lo que pienso"
    assert "discovered=4" in " ".join(result.contexts[0].notable_details)
    assert [item.kind for item in result.contexts[1:]] == ["image"] * 4
    assert [item.label for item in result.contexts[1:]] == [
        "X post image 1",
        "X post image 2",
        "X post image 3",
        "X post image 4",
    ]
    assert network_calls == {"api": 1, "image": 4}
    assert len(provider_calls) == 4
