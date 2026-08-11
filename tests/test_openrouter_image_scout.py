import asyncio
import base64
import json

import httpx
from pydantic import SecretStr

from echo_masque.image_creation_runtime import default_image_generation_provider_factory
from echo_masque.image_generation import ImageGenerationRequest
from echo_masque.openrouter_image_scout import (
    AUTO_FREE_ANIME_MODEL,
    AutomaticFreeAnimeImageProvider,
    OpenRouterImageModelScout,
)
from echo_masque.provider_credentials import ResolvedProviderCredential
from echo_masque.providers.openrouter_image import OpenRouterImageGenerationProvider


def credential(*, model: str = AUTO_FREE_ANIME_MODEL) -> ResolvedProviderCredential:
    return ResolvedProviderCredential(
        key_group_id="kg-openrouter",
        provider="openrouter",
        base_url="https://openrouter.ai/api/v1",
        model=model,
        api_key=SecretStr("secret"),
    )


def test_scout_only_accepts_pinnable_zero_cost_endpoints_and_prefers_anime() -> None:
    calls = {"models": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/images/models":
            calls["models"] += 1
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "example/general-free",
                            "name": "General Free",
                            "description": "A general purpose image model.",
                            "created": 10,
                            "endpoints": "/api/v1/images/models/example/general-free/endpoints",
                        },
                        {
                            "id": "example/animagine-free",
                            "name": "Animagine Free",
                            "description": "Anime and manga character illustration model.",
                            "created": 5,
                            "endpoints": "/api/v1/images/models/example/animagine-free/endpoints",
                        },
                        {
                            "id": "example/anime-paid",
                            "name": "Anime Paid",
                            "description": "Anime illustration model.",
                            "created": 20,
                            "endpoints": "/api/v1/images/models/example/anime-paid/endpoints",
                        },
                        {
                            "id": "example/free-without-tag",
                            "name": "Unpinnable Free",
                            "description": "Anime image model without a provider tag.",
                            "created": 30,
                            "endpoints": "/api/v1/images/models/example/free-without-tag/endpoints",
                        },
                    ]
                },
            )
        if request.url.path.endswith("/general-free/endpoints"):
            return httpx.Response(
                200,
                json={
                    "endpoints": [
                        {
                            "provider_name": "FreeHost",
                            "provider_tag": "free-host",
                            "pricing": [{"billable": "output_image", "cost_usd": 0}],
                        }
                    ]
                },
            )
        if request.url.path.endswith("/animagine-free/endpoints"):
            return httpx.Response(
                200,
                json={
                    "endpoints": [
                        {
                            "provider_name": "AnimeHost",
                            "provider_tag": "anime-host",
                            "pricing": [
                                {"billable": "input_token", "cost_usd": "0"},
                                {"billable": "output_image", "cost_usd": "0.000"},
                            ],
                        }
                    ]
                },
            )
        if request.url.path.endswith("/anime-paid/endpoints"):
            return httpx.Response(
                200,
                json={
                    "endpoints": [
                        {
                            "provider_name": "PaidHost",
                            "provider_tag": "paid-host",
                            "pricing": [
                                {"billable": "input_token", "cost_usd": 0},
                                {"billable": "output_image", "cost_usd": 0.01},
                            ],
                        }
                    ]
                },
            )
        if request.url.path.endswith("/free-without-tag/endpoints"):
            return httpx.Response(
                200,
                json={
                    "endpoints": [
                        {
                            "provider_name": "MysteryHost",
                            "provider_tag": None,
                            "pricing": [{"billable": "output_image", "cost_usd": 0}],
                        }
                    ]
                },
            )
        return httpx.Response(404)

    scout = OpenRouterImageModelScout(
        cache_ttl_seconds=3600,
        http_transport=httpx.MockTransport(handler),
    )
    first = asyncio.run(scout.discover(credential()))
    second = asyncio.run(scout.discover(credential()))

    assert first.selected_model == "example/animagine-free"
    assert [item.model_id for item in first.candidates] == [
        "example/animagine-free",
        "example/general-free",
    ]
    assert first.candidates[0].provider_tags == ("anime-host",)
    assert first.candidates[0].style_score > first.candidates[1].style_score
    assert second.from_cache is True
    assert calls["models"] == 1


def test_default_provider_factory_recognizes_auto_free_anime_mode() -> None:
    provider = default_image_generation_provider_factory(credential())

    assert isinstance(provider, AutomaticFreeAnimeImageProvider)
    assert provider.model == AUTO_FREE_ANIME_MODEL


def test_image_provider_can_pin_one_endpoint_and_disable_fallbacks() -> None:
    observed: dict[str, object] = {}
    png = b"\x89PNG\r\n\x1a\nprovider-test"

    def handler(request: httpx.Request) -> httpx.Response:
        observed.update(json.loads(request.content.decode("utf-8")))
        return httpx.Response(
            200,
            json={
                "model": "example/animagine-free",
                "data": [{"b64_json": base64.b64encode(png).decode("ascii")}],
            },
        )

    provider = OpenRouterImageGenerationProvider(
        api_key=SecretStr("secret"),
        model="example/animagine-free",
        provider_only=("anime-host",),
        allow_fallbacks=False,
        transport=httpx.MockTransport(handler),
    )
    asyncio.run(provider.generate(ImageGenerationRequest(prompt="anime character portrait")))

    assert observed["provider"] == {
        "only": ["anime-host"],
        "allow_fallbacks": False,
    }
