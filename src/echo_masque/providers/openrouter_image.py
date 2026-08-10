"""Optional OpenRouter Image API adapter behind the provider-neutral image contract."""

from __future__ import annotations

import httpx
from pydantic import SecretStr

from echo_masque.image_generation import (
    GeneratedImage,
    ImageGenerationRequest,
    ImageGenerationResult,
)
from echo_masque.providers.errors import (
    ProviderAuthenticationError,
    ProviderProtocolError,
    ProviderTimeoutError,
)


class OpenRouterImageGenerationProvider:
    """Generate images through OpenRouter without making OpenRouter a runtime dependency."""

    provider_id = "openrouter"

    def __init__(
        self,
        *,
        api_key: SecretStr,
        model: str,
        base_url: str = "https://openrouter.ai/api/v1",
        timeout_seconds: float = 120.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model.strip()
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._transport = transport

    @property
    def model(self) -> str:
        return self._model

    @property
    def endpoint(self) -> str:
        if self._base_url.endswith("/api/v1") or self._base_url.endswith("/v1"):
            return f"{self._base_url}/images"
        return f"{self._base_url}/api/v1/images"

    async def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        payload: dict[str, object] = {
            "model": self._model,
            "prompt": request.prompt,
            "n": request.n,
        }
        if request.aspect_ratio:
            payload["aspect_ratio"] = request.aspect_ratio
        if request.resolution:
            payload["resolution"] = request.resolution
        if request.references:
            payload["input_references"] = [
                {
                    "type": "image_url",
                    "image_url": {"url": reference.uri},
                }
                for reference in request.references
            ]

        headers = {
            "Authorization": f"Bearer {self._api_key.get_secret_value()}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout,
                transport=self._transport,
            ) as client:
                response = await client.post(self.endpoint, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("Image generation provider timed out.") from exc

        if response.status_code in {401, 403}:
            raise ProviderAuthenticationError("Image generation provider rejected the credential.")
        if response.is_error:
            raise ProviderProtocolError(
                f"Image generation provider returned HTTP {response.status_code}."
            )

        try:
            body = response.json()
            raw_images = body["data"]
            if not isinstance(raw_images, list) or not raw_images:
                raise TypeError("Image generation data must be a non-empty list.")
            images = tuple(
                GeneratedImage(
                    b64_json=str(item.get("b64_json") or ""),
                    url=str(item.get("url") or ""),
                    media_type=str(item.get("media_type") or "image/png"),
                )
                for item in raw_images
                if isinstance(item, dict)
            )
            if not images or any(not item.b64_json and not item.url for item in images):
                raise TypeError("Generated image entries must contain b64_json or url.")
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderProtocolError(
                "Image generation provider returned an invalid response payload."
            ) from exc

        return ImageGenerationResult(
            images=images,
            provider=self.provider_id,
            model=str(body.get("model") or self._model),
        )
