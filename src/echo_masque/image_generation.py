"""Provider-neutral image generation contracts for Character Relay Tools."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field


class ImageReference(BaseModel):
    model_config = ConfigDict(frozen=True)

    uri: str = Field(min_length=1, max_length=4096)
    role: str = Field(default="reference", max_length=80)


class ImageGenerationRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    prompt: str = Field(min_length=1, max_length=8000)
    aspect_ratio: str = Field(default="1:1", max_length=20)
    resolution: str = Field(default="", max_length=30)
    n: int = Field(default=1, ge=1, le=10)
    references: tuple[ImageReference, ...] = ()


class GeneratedImage(BaseModel):
    model_config = ConfigDict(frozen=True)

    media_type: str = Field(default="image/png", max_length=120)
    b64_json: str = ""
    url: str = Field(default="", max_length=4096)


class ImageGenerationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    images: tuple[GeneratedImage, ...]
    provider: str
    model: str


class ImageGenerationProvider(Protocol):
    @property
    def provider_id(self) -> str: ...

    @property
    def model(self) -> str: ...

    async def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult: ...


class ImageGenerationService:
    """Thin capability boundary; Character Runtime does not depend on provider request shapes."""

    def __init__(self, provider: ImageGenerationProvider) -> None:
        self.provider = provider

    async def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        return await self.provider.generate(request)
