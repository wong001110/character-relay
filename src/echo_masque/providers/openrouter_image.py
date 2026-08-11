"""OpenAI-compatible Image API adapter behind the provider-neutral image contract."""

from __future__ import annotations

import json

import httpx
from pydantic import SecretStr

from echo_masque.image_generation import (
    GeneratedImage,
    ImageGenerationRequest,
    ImageGenerationResult,
)
from echo_masque.providers.base import ChatMessage
from echo_masque.providers.errors import (
    ProviderAuthenticationError,
    ProviderProtocolError,
    ProviderTimeoutError,
)
from echo_masque.providers.trace import ProviderTrace

_IMAGE_GENERATION_MARKER = "[IMAGE_GENERATION]"
_IMAGE_GENERATION_RESULT_MARKER = "[IMAGE_GENERATION_RESULT]"


class OpenRouterImageGenerationProvider:
    """Generate through an OpenAI-compatible image endpoint; OpenRouter remains optional."""

    def __init__(
        self,
        *,
        api_key: SecretStr,
        model: str,
        provider_id: str = "openrouter",
        base_url: str = "https://openrouter.ai/api/v1",
        timeout_seconds: float = 120.0,
        transport: httpx.AsyncBaseTransport | None = None,
        provider_only: tuple[str, ...] = (),
        allow_fallbacks: bool = True,
    ) -> None:
        self._provider_id = provider_id.strip() or "openrouter"
        self._api_key = api_key
        self._model = model.strip()
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._transport = transport
        self._provider_only = tuple(item.strip() for item in provider_only if item.strip())
        self._allow_fallbacks = allow_fallbacks

    @property
    def provider_id(self) -> str:
        return self._provider_id

    @property
    def model(self) -> str:
        return self._model

    @property
    def endpoint(self) -> str:
        if self._base_url.endswith("/api/v1") or self._base_url.endswith("/v1"):
            return f"{self._base_url}/images"
        return f"{self._base_url}/api/v1/images"

    async def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        trace = ProviderTrace.start(
            endpoint=self.endpoint,
            model=self._model,
            temperature=0.0,
            messages=(
                ChatMessage(
                    role="user",
                    content=(
                        f"{_IMAGE_GENERATION_MARKER}\n"
                        + json.dumps(
                            {
                                "operation": "image.generate",
                                "prompt_chars": len(request.prompt),
                                "aspect_ratio": request.aspect_ratio,
                                "resolution": request.resolution,
                                "image_count": request.n,
                                "reference_count": len(request.references),
                            },
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                    ),
                ),
            ),
        )
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
        if self._provider_only:
            payload["provider"] = {
                "only": list(self._provider_only),
                "allow_fallbacks": self._allow_fallbacks,
            }

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
            trace.error(
                reason="provider_timeout",
                detail="Image generation provider did not respond before the timeout.",
            )
            raise ProviderTimeoutError("Image generation provider timed out.") from exc
        except httpx.HTTPError as exc:
            trace.error(
                reason="provider_unavailable",
                detail="Image generation provider connection failed before a response arrived.",
            )
            raise ProviderProtocolError("Image generation provider could not be reached.") from exc

        if response.status_code in {401, 403}:
            trace.error(
                reason="provider_authentication_rejected",
                status_code=response.status_code,
                detail="Image generation provider rejected the configured credential.",
            )
            raise ProviderAuthenticationError("Image generation provider rejected the credential.")
        if response.is_error:
            trace.error(
                reason="provider_http_error",
                status_code=response.status_code,
                response_body=response.text,
                detail=f"Image generation provider returned HTTP {response.status_code}.",
            )
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
            trace.error(
                reason="invalid_response_payload",
                status_code=response.status_code,
                detail="Image generation response did not contain usable image entries.",
            )
            raise ProviderProtocolError(
                "Image generation provider returned an invalid response payload."
            ) from exc

        response_model = str(body.get("model") or self._model)
        trace.response(
            status_code=response.status_code,
            response_model=response_model,
            text=(
                f"{_IMAGE_GENERATION_RESULT_MARKER}\n"
                + json.dumps(
                    {"image_count": len(images)},
                    separators=(",", ":"),
                )
            ),
            input_tokens=None,
            output_tokens=None,
            finish_reason="image_generated",
        )
        return ImageGenerationResult(
            images=images,
            provider=self.provider_id,
            model=response_model,
        )
