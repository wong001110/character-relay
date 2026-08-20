"""Runtime-observed model capabilities for provider-safe routing.

This registry intentionally records protocol/modality facts about one provider/model endpoint,
not Character Relay consumer capabilities. Unknown is optimistic for first use; only explicit
unsupported observations block a route. Observations are process-local in V1 so a provider
configuration change naturally starts clean while persisted Utility health/quota remains the
cross-process access authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Literal
from urllib.parse import urlparse

ModelCapability = Literal[
    "text_input",
    "image_input",
    "multi_image_input",
    "video_url",
    "data_uri_image",
    "remote_image_url",
    "remote_video_url",
    "youtube_video_url",
    "inline_image_data",
    "file_upload",
    "json_object",
    "json_schema",
    "native_tool_calling",
]
CapabilityStatus = Literal["unknown", "supported", "unsupported"]
CapabilityEvidenceSource = Literal["declared", "probe", "runtime"]


@dataclass(frozen=True, slots=True)
class CapabilityObservation:
    provider: str
    model: str
    endpoint_key: str
    capability: ModelCapability
    status: CapabilityStatus
    source: CapabilityEvidenceSource
    detail: str = ""


class ProviderModelCapabilityRegistry:
    """Process-shared capability evidence keyed by provider/model/endpoint."""

    _lock = RLock()
    _values: dict[tuple[str, str, str, ModelCapability], CapabilityObservation] = {}

    @staticmethod
    def endpoint_key(base_url: str) -> str:
        parsed = urlparse(base_url.strip())
        host = (parsed.hostname or parsed.netloc or base_url).casefold().strip()
        path = parsed.path.rstrip("/").casefold()
        return f"{host}{path}"[:400]

    @classmethod
    def _key(
        cls,
        *,
        provider: str,
        model: str,
        base_url: str,
        capability: ModelCapability,
    ) -> tuple[str, str, str, ModelCapability]:
        return (
            provider.casefold().strip(),
            model.casefold().strip(),
            cls.endpoint_key(base_url),
            capability,
        )

    @classmethod
    def observe(
        cls,
        *,
        provider: str,
        model: str,
        base_url: str,
        capability: ModelCapability,
        supported: bool,
        source: CapabilityEvidenceSource = "runtime",
        detail: str = "",
    ) -> CapabilityObservation:
        observation = CapabilityObservation(
            provider=provider.casefold().strip(),
            model=model.strip(),
            endpoint_key=cls.endpoint_key(base_url),
            capability=capability,
            status="supported" if supported else "unsupported",
            source=source,
            detail=" ".join(detail.split())[:500],
        )
        key = cls._key(
            provider=provider,
            model=model,
            base_url=base_url,
            capability=capability,
        )
        with cls._lock:
            cls._values[key] = observation
        return observation

    @classmethod
    def status(
        cls,
        *,
        provider: str,
        model: str,
        base_url: str,
        capability: ModelCapability,
    ) -> CapabilityStatus:
        key = cls._key(
            provider=provider,
            model=model,
            base_url=base_url,
            capability=capability,
        )
        with cls._lock:
            value = cls._values.get(key)
        return value.status if value is not None else "unknown"

    @classmethod
    def allows(
        cls,
        *,
        provider: str,
        model: str,
        base_url: str,
        capability: ModelCapability,
    ) -> bool:
        return (
            cls.status(
                provider=provider,
                model=model,
                base_url=base_url,
                capability=capability,
            )
            != "unsupported"
        )

    @classmethod
    def snapshot(
        cls,
        *,
        provider: str = "",
        model: str = "",
    ) -> tuple[CapabilityObservation, ...]:
        provider_key = provider.casefold().strip()
        model_key = model.casefold().strip()
        with cls._lock:
            values = tuple(cls._values.values())
        return tuple(
            item
            for item in values
            if (not provider_key or item.provider == provider_key)
            and (not model_key or item.model.casefold() == model_key)
        )

    @classmethod
    def reset_for_test(cls) -> None:
        with cls._lock:
            cls._values.clear()


__all__ = [
    "CapabilityEvidenceSource",
    "CapabilityObservation",
    "CapabilityStatus",
    "ModelCapability",
    "ProviderModelCapabilityRegistry",
]
