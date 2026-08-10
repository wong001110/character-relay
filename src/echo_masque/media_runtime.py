"""Provider-neutral Media Understanding runtime with shared cache reuse."""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from echo_masque.persistence.media_repository import MediaAnalysisRepository

MediaType = Literal["image", "video", "audio"]


class MediaAsset(BaseModel):
    """Resolved media reference. Raw media retention is intentionally not required."""

    model_config = ConfigDict(frozen=True)

    media_key: str = Field(min_length=1, max_length=300)
    media_type: MediaType
    mime_type: str = Field(default="", max_length=120)
    filename: str = Field(default="", max_length=255)
    source_uri: str = Field(default="", max_length=4096)
    size_bytes: int | None = Field(default=None, ge=0)


class MediaAnalysis(BaseModel):
    """Objective media-derived context shared by every Character that inspects the content."""

    model_config = ConfigDict(frozen=True)

    summary: str = Field(min_length=1, max_length=12000)
    visible_text: str = Field(default="", max_length=16000)
    people: tuple[str, ...] = ()
    objects: tuple[str, ...] = ()
    notable_details: tuple[str, ...] = ()
    topics: tuple[str, ...] = ()
    tone: str = Field(default="", max_length=160)


class MediaUnderstandingProvider(Protocol):
    @property
    def provider_id(self) -> str: ...

    @property
    def model(self) -> str: ...

    async def analyze(self, asset: MediaAsset) -> MediaAnalysis: ...


class MediaUnderstandingService:
    """Run Level-1 media understanding once, then share the cached objective context."""

    def __init__(
        self,
        repository: MediaAnalysisRepository,
        provider: MediaUnderstandingProvider,
        *,
        analysis_version: str = "general-v1",
    ) -> None:
        self.repository = repository
        self.provider = provider
        self.analysis_version = analysis_version

    async def analyze(self, asset: MediaAsset) -> tuple[MediaAnalysis, bool]:
        cached = self.repository.get(
            media_key=asset.media_key,
            analysis_version=self.analysis_version,
            provider=self.provider.provider_id,
            model=self.provider.model,
        )
        if cached is not None:
            try:
                return MediaAnalysis.model_validate_json(cached.result_json), True
            except ValidationError:
                # Schema evolution or corrupt cache entries are repaired lazily.
                pass

        analysis = await self.provider.analyze(asset)
        self.repository.put(
            media_key=asset.media_key,
            media_type=asset.media_type,
            analysis_version=self.analysis_version,
            provider=self.provider.provider_id,
            model=self.provider.model,
            result_json=analysis.model_dump_json(),
        )
        # Opportunistic bounded cleanup keeps SQLite growth controlled without a hot-cache service.
        self.repository.purge_expired(limit=100)
        return analysis, False
