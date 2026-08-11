"""Live image-generation Runtime service and bounded artifact materialization."""

from __future__ import annotations

import base64
import binascii
from typing import Literal, Protocol

import httpx
from pydantic import BaseModel, Field, model_validator

from echo_masque.image_generation import ImageGenerationRequest, ImageReference
from echo_masque.network_safety import PublicUrlGuard, PublicUrlRejected
from echo_masque.persistence.conversation_media_repository import ConversationMediaReferenceRepository
from echo_masque.persistence.generated_media_repository import GeneratedMediaArtifactRepository
from echo_masque.provider_credentials import (
    KeyGroupProviderCredentialResolver,
    ResolvedProviderCredential,
)
from echo_masque.providers.openrouter_image import OpenRouterImageGenerationProvider

_MAX_GENERATED_IMAGE_BYTES = 8 * 1024 * 1024


class ImageGenerateToolInput(BaseModel):
    """Intent-level Tool input; provider/model details remain Runtime-owned."""

    prompt: str = Field(min_length=1, max_length=4000)
    aspect_ratio: str = Field(default="1:1", max_length=20)
    resolution: str = Field(default="", max_length=30)
    reference_mode: Literal["none", "current", "reply", "recent"] = "none"

    @model_validator(mode="after")
    def normalize(self) -> ImageGenerateToolInput:
        self.prompt = self.prompt.strip()
        self.aspect_ratio = self.aspect_ratio.strip() or "1:1"
        self.resolution = self.resolution.strip()
        return self


class ImageGenerationProviderFactory(Protocol):
    def __call__(self, credential: ResolvedProviderCredential) -> OpenRouterImageGenerationProvider: ...


def default_image_generation_provider_factory(
    credential: ResolvedProviderCredential,
) -> OpenRouterImageGenerationProvider:
    provider = credential.provider.casefold().strip()
    base_url = credential.base_url.strip()
    if provider == "openrouter":
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
        provider_factory: ImageGenerationProviderFactory = default_image_generation_provider_factory,
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
                "No previously perceived image with a reusable source is available for that reference."
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
            content, mime_type = await self._materialize(image.b64_json, image.url, image.media_type)
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
            mime_type = declared_mime or self._sniff_mime(content)
        elif url:
            try:
                safe_url = await self.url_guard.validate(url)
            except PublicUrlRejected as exc:
                raise ValueError("Generated image URL failed public URL validation.") from exc
            try:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(30.0),
                    transport=self.http_transport,
                    follow_redirects=True,
                ) as client:
                    response = await client.get(safe_url)
            except httpx.HTTPError as exc:
                raise ValueError("Generated image download failed.") from exc
            if response.is_error:
                raise ValueError(
                    f"Generated image download returned HTTP {response.status_code}."
                )
            content = response.content
            mime_type = response.headers.get("content-type", declared_mime).split(";", 1)[0]
        else:
            raise ValueError("Image provider returned neither base64 data nor a URL.")

        if not content or len(content) > _MAX_GENERATED_IMAGE_BYTES:
            raise ValueError("Generated image is empty or exceeds the 8 MB delivery limit.")
        sniffed = self._sniff_mime(content)
        if not sniffed:
            raise ValueError("Generated artifact is not a supported image format.")
        if not mime_type.startswith("image/"):
            mime_type = sniffed
        return content, mime_type

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
