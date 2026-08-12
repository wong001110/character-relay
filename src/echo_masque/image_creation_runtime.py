"""Live image-generation Runtime service and bounded artifact materialization."""

from __future__ import annotations

import base64
import binascii
from typing import Literal, Protocol
from urllib.parse import urljoin

import httpx
from pydantic import BaseModel, Field, model_validator

from echo_masque.image_generation import (
    CanonicalAspectRatio,
    ImageGenerationProvider,
    ImageGenerationRequest,
    ImageReference,
)
from echo_masque.network_safety import PublicUrlGuard, PublicUrlRejected
from echo_masque.openrouter_image_scout import (
    AUTO_FREE_ANIME_MODEL,
    AutomaticFreeAnimeImageProvider,
)
from echo_masque.persistence.conversation_media_repository import (
    ConversationMediaReferenceRepository,
)
from echo_masque.persistence.generated_media_repository import GeneratedMediaArtifactRepository
from echo_masque.provider_credentials import (
    KeyGroupProviderCredentialResolver,
    ResolvedProviderCredential,
)
from echo_masque.providers.openrouter_image import OpenRouterImageGenerationProvider

_MAX_GENERATED_IMAGE_BYTES = 8 * 1024 * 1024
_MAX_REDIRECTS = 4


class ImageGenerateToolInput(BaseModel):
    """Intent-level Tool input; provider/model details remain Runtime-owned."""

    prompt: str = Field(min_length=1, max_length=4000)
    aspect_ratio: CanonicalAspectRatio = "1:1"
    resolution: str = Field(default="", max_length=30)
    reference_mode: Literal["none", "current", "reply", "recent"] = "none"

    @model_validator(mode="after")
    def normalize(self) -> ImageGenerateToolInput:
        self.prompt = self.prompt.strip()
        self.resolution = self.resolution.strip()
        return self


class ImageGenerationProviderFactory(Protocol):
    def __call__(self, credential: ResolvedProviderCredential) -> ImageGenerationProvider: ...


def default_image_generation_provider_factory(
    credential: ResolvedProviderCredential,
) -> ImageGenerationProvider:
    provider = credential.provider.casefold().strip()
    base_url = credential.base_url.strip()
    if provider == "openrouter":
        if credential.model == AUTO_FREE_ANIME_MODEL:
            return AutomaticFreeAnimeImageProvider(credential)
        base_url = base_url or "https://openrouter.ai/api/v1"
    elif provider in {"custom", "openai", "openai_compatible"}:
        if not base_url:
            raise ValueError("Custom Image Generation Key Group requires a base URL.")
    else:
        raise ValueError(
            f"Image Generation provider {credential.provider!r} is not wired yet."
        )
    return OpenRouterImageGenerationProvider(
        provider_id=credential.provider,
        api_key=credential.api_key,
        model=credential.model,
        base_url=base_url,
    )


class ImageCreationRuntimeService:
    """Resolve provider credentials, references, and temporary delivery artifacts."""

    def __init__(
        self,
        *,
        credential_resolver: KeyGroupProviderCredentialResolver,
        conversation_media_repository: ConversationMediaReferenceRepository,
        artifact_repository: GeneratedMediaArtifactRepository,
        provider_factory: ImageGenerationProviderFactory = (
            default_image_generation_provider_factory
        ),
        http_transport: httpx.AsyncBaseTransport | None = None,
        url_guard: PublicUrlGuard | None = None,
    ) -> None:
        self.credential_resolver = credential_resolver
        self.conversation_media_repository = conversation_media_repository
        self.artifact_repository = artifact_repository
        self.provider_factory = provider_factory
        self.http_transport = http_transport
        self.url_guard = url_guard or PublicUrlGuard()

    async def generate(
        self,
        *,
        owner_id: str,
        deployment_id: str,
        character_card_id: str,
        guild_id: str,
        channel_id: str,
        thread_id: str,
        message_id: str,
        reply_to_message_id: str,
        payload: ImageGenerateToolInput,
    ) -> tuple[str, ...]:
        credential = self.credential_resolver.resolve(
            owner_id=owner_id,
            character_card_id=character_card_id,
            capability="image_generation",
        )
        if credential is None:
            raise ValueError("No Image Generation Key Group is assigned to this Character.")

        references = self._references(
            deployment_id=deployment_id,
            character_card_id=character_card_id,
            guild_id=guild_id,
            channel_id=channel_id,
            thread_id=thread_id,
            message_id=message_id,
            reply_to_message_id=reply_to_message_id,
            reference_mode=payload.reference_mode,
        )
        if payload.reference_mode != "none" and not references:
            raise ValueError(
                "No previously perceived image with a reusable source is available "
                "for that reference."
            )

        provider = self.provider_factory(credential)
        result = await provider.generate(
            ImageGenerationRequest(
                prompt=payload.prompt,
                aspect_ratio=payload.aspect_ratio,
                resolution=payload.resolution,
                n=1,
                references=references,
            )
        )
        artifact_ids: list[str] = []
        for index, image in enumerate(result.images[:1], start=1):
            content, mime_type = await self._materialize(
                image.b64_json,
                image.url,
                image.media_type,
            )
            extension = self._extension(mime_type)
            media_key = self._media_key(content)
            record = self.artifact_repository.create(
                owner_id=owner_id,
                deployment_id=deployment_id,
                character_card_id=character_card_id,
                media_key=media_key,
                mime_type=mime_type,
                filename=f"character-generated-{index}.{extension}",
                provider=result.provider,
                model=result.model,
                content=content,
            )
            artifact_ids.append(record.id)
        if not artifact_ids:
            raise ValueError("Image generation returned no deliverable image.")
        return tuple(artifact_ids)

    def _references(
        self,
        *,
        deployment_id: str,
        character_card_id: str,
        guild_id: str,
        channel_id: str,
        thread_id: str,
        message_id: str,
        reply_to_message_id: str,
        reference_mode: Literal["none", "current", "reply", "recent"],
    ) -> tuple[ImageReference, ...]:
        if reference_mode == "none":
            return ()
        if reference_mode == "current":
            records = self.conversation_media_repository.for_message(
                deployment_id=deployment_id,
                character_card_id=character_card_id,
                guild_id=guild_id,
                channel_id=channel_id,
                thread_id=thread_id,
                message_id=message_id,
            )
        elif reference_mode == "reply":
            if not reply_to_message_id:
                return ()
            records = self.conversation_media_repository.for_message(
                deployment_id=deployment_id,
                character_card_id=character_card_id,
                guild_id=guild_id,
                channel_id=channel_id,
                thread_id=thread_id,
                message_id=reply_to_message_id,
            )
        else:
            records = self.conversation_media_repository.recent(
                deployment_id=deployment_id,
                character_card_id=character_card_id,
                guild_id=guild_id,
                channel_id=channel_id,
                thread_id=thread_id,
                limit=8,
            )
        return tuple(
            ImageReference(uri=item.source_uri, role="conversation_reference")
            for item in records
            if item.kind == "image" and item.source_uri
        )[:2]

    async def _materialize(
        self,
        b64_json: str,
        url: str,
        declared_mime: str,
    ) -> tuple[bytes, str]:
        if b64_json:
            try:
                content = base64.b64decode(b64_json, validate=True)
            except (ValueError, binascii.Error) as exc:
                raise ValueError("Image provider returned invalid base64 image data.") from exc
        elif url:
            content = await self._download_generated_image(url)
        else:
            raise ValueError("Image provider returned neither base64 data nor a URL.")

        if not content or len(content) > _MAX_GENERATED_IMAGE_BYTES:
            raise ValueError("Generated image is empty or exceeds the 8 MB delivery limit.")
        sniffed = self._sniff_mime(content)
        if not sniffed:
            raise ValueError("Generated artifact is not a supported image format.")
        return content, sniffed

    async def _download_generated_image(self, url: str) -> bytes:
        try:
            current = await self.url_guard.validate(url)
        except PublicUrlRejected as exc:
            raise ValueError("Generated image URL failed public URL validation.") from exc
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                transport=self.http_transport,
                follow_redirects=False,
            ) as client:
                for redirect_index in range(_MAX_REDIRECTS + 1):
                    response = await client.get(current)
                    if response.status_code in {301, 302, 303, 307, 308}:
                        if redirect_index >= _MAX_REDIRECTS:
                            raise ValueError("Generated image exceeded the redirect limit.")
                        location = response.headers.get("location", "").strip()
                        if not location:
                            raise ValueError("Generated image redirect omitted a destination.")
                        current = await self.url_guard.validate(urljoin(current, location))
                        continue
                    if response.is_error:
                        raise ValueError(
                            f"Generated image download returned HTTP {response.status_code}."
                        )
                    if len(response.content) > _MAX_GENERATED_IMAGE_BYTES:
                        raise ValueError("Generated image exceeds the 8 MB delivery limit.")
                    return response.content
        except (httpx.HTTPError, PublicUrlRejected) as exc:
            raise ValueError("Generated image download failed safely.") from exc
        raise ValueError("Generated image could not be downloaded.")

    @staticmethod
    def _sniff_mime(content: bytes) -> str:
        if content.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        if content.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        if content.startswith((b"GIF87a", b"GIF89a")):
            return "image/gif"
        if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
            return "image/webp"
        return ""

    @staticmethod
    def _extension(mime_type: str) -> str:
        return {
            "image/jpeg": "jpg",
            "image/gif": "gif",
            "image/webp": "webp",
        }.get(mime_type, "png")

    @staticmethod
    def _media_key(content: bytes) -> str:
        import hashlib

        return f"sha256:{hashlib.sha256(content).hexdigest()}"
