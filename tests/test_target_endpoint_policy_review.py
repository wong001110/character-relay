from __future__ import annotations

import asyncio

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from echo_masque.config import Settings
from echo_masque.image_generation import ImageGenerationRequest
from echo_masque.media_runtime import MediaAsset
from echo_masque.providers import ChatMessage, OpenAICompatibleProvider, ProviderProtocolError
from echo_masque.providers.openai_multimodal import OpenAICompatibleMultimodalProvider
from echo_masque.providers.openrouter_image import OpenRouterImageGenerationProvider
from echo_masque.target_endpoint_policy import (
    EndpointPolicyRejected,
    TargetEndpointPolicy,
    canonical_endpoint_origin,
    validated_operator_origin,
)
from echo_masque.targets import HttpTarget, HttpTargetConfig


def test_production_http_targets_require_an_operator_approved_exact_origin() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"response": "ok"})

    target = HttpTarget(
        name="Review target",
        config=HttpTargetConfig(message_url="https://target.example.test/api/chat"),
        transport=httpx.MockTransport(handler),
        settings=Settings(environment="production"),
    )

    with pytest.raises(ProviderProtocolError, match="not approved"):
        asyncio.run(target.send("hello"))

    assert requests == []


def test_approved_production_http_target_and_known_provider_can_use_mock_transport() -> None:
    requests: list[str] = []

    async def target_handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        return httpx.Response(200, json={"response": "ok"})

    target = HttpTarget(
        name="Approved target",
        config=HttpTargetConfig(message_url="https://target.example.test/api/chat"),
        transport=httpx.MockTransport(target_handler),
        settings=Settings(
            environment="production",
            http_target_allowed_origins=("https://target.example.test",),
        ),
    )
    response = asyncio.run(target.send("hello"))

    assert response.text == "ok"
    assert requests == ["https://target.example.test/api/chat"]

    async def provider_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.deepseek.com"
        return httpx.Response(
            200,
            json={
                "model": "test-model",
                "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 2},
            },
        )

    provider = OpenAICompatibleProvider(
        base_url="https://api.deepseek.com",
        api_key=SecretStr("synthetic-provider-value"),
        transport=httpx.MockTransport(provider_handler),
        settings=Settings(environment="production"),
    )
    completion = asyncio.run(
        provider.complete(
            messages=(ChatMessage(role="user", content="hello"),),
            model="test-model",
            temperature=0.1,
        )
    )

    assert completion.text == "ok"


def test_unapproved_production_provider_never_reaches_transport() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={})

    provider = OpenAICompatibleProvider(
        base_url="https://unapproved.example.test",
        api_key=SecretStr("synthetic-provider-value"),
        transport=httpx.MockTransport(handler),
        settings=Settings(environment="production"),
    )

    with pytest.raises(ProviderProtocolError, match="not approved"):
        asyncio.run(
            provider.complete(
                messages=(ChatMessage(role="user", content="hello"),),
                model="test-model",
                temperature=0.1,
            )
        )

    assert requests == []


def test_unapproved_multimodal_and_image_provider_endpoints_never_reach_transport() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={})

    settings = Settings(environment="production")
    multimodal = OpenAICompatibleMultimodalProvider(
        provider_id="custom",
        api_key=SecretStr("synthetic-provider-value"),
        model="vision-model",
        base_url="https://unapproved.example.test/v1",
        transport=httpx.MockTransport(handler),
        settings=settings,
    )
    with pytest.raises(ProviderProtocolError, match="not approved"):
        asyncio.run(
            multimodal.analyze(
                MediaAsset(
                    media_key="sha256:example",
                    media_type="image",
                    source_uri="https://cdn.example.test/image.png",
                )
            )
        )

    image = OpenRouterImageGenerationProvider(
        api_key=SecretStr("synthetic-provider-value"),
        model="image-model",
        base_url="https://unapproved.example.test/v1",
        transport=httpx.MockTransport(handler),
        settings=settings,
    )
    with pytest.raises(ProviderProtocolError, match="not approved"):
        asyncio.run(image.generate(ImageGenerationRequest(prompt="synthetic image")))

    assert requests == []


def test_approved_target_does_not_follow_redirects_to_another_origin() -> None:
    requests: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        return httpx.Response(302, headers={"location": "https://unapproved.example.test/next"})

    target = HttpTarget(
        name="Redirect review",
        config=HttpTargetConfig(message_url="https://target.example.test/api/chat"),
        transport=httpx.MockTransport(handler),
        settings=Settings(
            environment="production",
            http_target_allowed_origins=("https://target.example.test",),
        ),
    )

    with pytest.raises(ProviderProtocolError, match="redirect was refused"):
        asyncio.run(target.send("hello"))

    assert requests == ["https://target.example.test/api/chat"]


def test_unapproved_reset_url_and_suffix_origin_never_reach_transport() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(204)

    settings = Settings(
        environment="production",
        http_target_allowed_origins=("https://target.example.test",),
    )
    target = HttpTarget(
        name="Reset review",
        config=HttpTargetConfig(
            message_url="https://target.example.test/api/chat",
            reset_url="https://unapproved.example.test/api/reset",
        ),
        transport=httpx.MockTransport(handler),
        settings=settings,
    )

    with pytest.raises(ProviderProtocolError, match="not approved"):
        asyncio.run(target.reset())
    with pytest.raises(EndpointPolicyRejected, match="not approved"):
        TargetEndpointPolicy.from_settings(settings).require_http_target_url(
            "https://sub.target.example.test/api/chat"
        )

    assert requests == []


def test_development_allows_local_http_models_but_production_does_not() -> None:
    development = TargetEndpointPolicy.from_settings(Settings(environment="development"))
    production = TargetEndpointPolicy.from_settings(Settings(environment="production"))

    development.require_provider_url("http://127.0.0.1:11434/v1")
    with pytest.raises(EndpointPolicyRejected, match="not approved"):
        production.require_provider_url("http://127.0.0.1:11434/v1")


def test_operator_origin_configuration_uses_character_relay_prefix_and_rejects_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "CHARACTER_RELAY_HTTP_TARGET_ALLOWED_ORIGINS",
        "https://target.example.test,https://target.example.test:8443",
    )
    settings = Settings(environment="production")

    assert settings.http_target_allowed_origins == (
        "https://target.example.test:443",
        "https://target.example.test:8443",
    )
    with pytest.raises(ValidationError, match="HTTPS origin"):
        Settings(
            environment="production",
            http_target_allowed_origins=("https://target.example.test/path",),
        )


def test_canonical_origin_rejects_missing_host_credentials_and_bad_scheme() -> None:
    for value in (
        "https://",
        "ftp://target.example.test",
        "https://operator@target.example.test",
        "https://:secret@target.example.test",
    ):
        with pytest.raises(EndpointPolicyRejected):
            canonical_endpoint_origin(value)


def test_canonical_origin_normalizes_ports_trailing_dot_and_ipv6() -> None:
    assert canonical_endpoint_origin("https://Target.Example.Test.") == (
        "https://target.example.test:443"
    )
    assert canonical_endpoint_origin("http://target.example.test") == (
        "http://target.example.test:80"
    )
    assert canonical_endpoint_origin("https://[::1]") == "https://[::1]:443"


def test_operator_origins_reject_query_fragment_and_credentials_but_allow_root_slash() -> None:
    assert validated_operator_origin("https://target.example.test/") == (
        "https://target.example.test:443"
    )
    for value in (
        "https://target.example.test/?next=private",
        "https://target.example.test/#fragment",
        "https://operator@target.example.test",
    ):
        with pytest.raises(ValueError):
            validated_operator_origin(value)


def test_development_local_http_allowance_is_limited_to_all_loopback_origins() -> None:
    policy = TargetEndpointPolicy.from_settings(Settings(environment="development"))

    policy.require_provider_url("http://localhost:11434/v1")
    policy.require_provider_url("http://[::1]:11434/v1")
    with pytest.raises(EndpointPolicyRejected, match="not allowed"):
        policy.require_provider_url("http://public.example.test/v1")
