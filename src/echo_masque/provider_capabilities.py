"""Runtime-observed model capabilities for provider-safe routing.

This registry records protocol/modality facts about one provider/model endpoint, not Character
Relay consumer capabilities. Unknown is optimistic for first use; only explicit unsupported
observations block a route. When a runtime persistence store is configured, observations survive
process restarts. Standalone/test usage remains in-memory only.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from threading import RLock
from typing import Literal, Protocol
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

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
    observed_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def current(self, *, now: datetime | None = None) -> bool:
        return capability_observation_is_current(
            self.status, self.observed_at, now or datetime.now(UTC)
        )


def capability_observation_is_current(
    status: CapabilityStatus,
    observed_at: datetime,
    now: datetime,
) -> bool:
    """A negative capability expires at fifteen minutes and becomes probeable again."""
    if status != "unsupported":
        return True
    observed = observed_at.replace(tzinfo=UTC) if observed_at.tzinfo is None else observed_at
    return now < observed + timedelta(minutes=15)


class CapabilityPersistence(Protocol):
    def load(
        self,
        *,
        provider: str,
        model: str,
        endpoint_key: str,
        capability: ModelCapability,
    ) -> CapabilityObservation | None: ...

    def save(self, observation: CapabilityObservation) -> None: ...


class ProviderModelCapabilityRegistry:
    """Process-shared capability evidence keyed by provider/model/endpoint."""

    _lock = RLock()
    _values: dict[tuple[str, str, str, ModelCapability], CapabilityObservation] = {}
    _persistence: CapabilityPersistence | None = None

    @staticmethod
    def endpoint_key(base_url: str) -> str:
        parsed = urlparse(base_url.strip())
        scheme = parsed.scheme.casefold()
        host = (parsed.hostname or "").casefold()
        port = parsed.port or {"http": 80, "https": 443}.get(scheme, 0)
        # Preserve case-sensitive path/query identity, but never persist URL credentials.
        canonical = f"{scheme}://{host}:{port}{parsed.path.rstrip('/')}?{parsed.query}"
        return "v2:" + hashlib.sha256(canonical.encode()).hexdigest()

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
    def configure_persistence(cls, persistence: CapabilityPersistence | None) -> None:
        """Switch the durable authority used for cache misses.

        Clearing process-local observations avoids leaking evidence between databases in tests and
        ensures a newly configured runtime reloads durable evidence for its own storage identity.
        """

        with cls._lock:
            cls._persistence = persistence
            cls._values.clear()

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
            model=model.casefold().strip(),
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
            persistence = cls._persistence
        if persistence is not None:
            try:
                persistence.save(observation)
            except Exception:
                # Capability telemetry must never make the provider call itself fail.
                logger.exception("Failed to persist provider capability observation")
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
            persistence = cls._persistence
        if value is not None and value.current():
            return value.status
        if value is not None:
            with cls._lock:
                cls._values.pop(key, None)
        if persistence is None:
            return "unknown"
        try:
            loaded = persistence.load(
                provider=key[0],
                model=key[1],
                endpoint_key=key[2],
                capability=capability,
            )
        except Exception:
            logger.exception("Failed to load provider capability observation")
            return "unknown"
        if loaded is None or not loaded.current():
            return "unknown"
        with cls._lock:
            cls._values[key] = loaded
        return loaded.status

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
            and item.current()
        )

    @classmethod
    def reset_for_test(cls) -> None:
        with cls._lock:
            cls._values.clear()
            cls._persistence = None


__all__ = [
    "CapabilityEvidenceSource",
    "CapabilityObservation",
    "CapabilityPersistence",
    "CapabilityStatus",
    "ModelCapability",
    "ProviderModelCapabilityRegistry",
]
