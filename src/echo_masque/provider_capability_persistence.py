"""Durable provider/model/endpoint capability evidence."""

from __future__ import annotations

from echo_masque.persistence import Database
from echo_masque.persistence.utility_gateway_models import UtilityProviderCapabilityRecord
from echo_masque.provider_capabilities import (
    CapabilityEvidenceSource,
    CapabilityObservation,
    CapabilityStatus,
    ModelCapability,
)

_CAPABILITIES: set[str] = {
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
}
_STATUSES: set[str] = {"unknown", "supported", "unsupported"}
_SOURCES: set[str] = {"declared", "probe", "runtime"}


class ProviderCapabilityPersistence:
    """Store capability observations in Character Relay's runtime database."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def load(
        self,
        *,
        provider: str,
        model: str,
        endpoint_key: str,
        capability: ModelCapability,
    ) -> CapabilityObservation | None:
        with self.database.session() as session:
            row = session.get(
                UtilityProviderCapabilityRecord,
                (provider.casefold().strip(), model.casefold().strip(), endpoint_key, capability),
            )
            if row is None:
                return None
            if (
                row.capability not in _CAPABILITIES
                or row.status not in _STATUSES
                or row.source not in _SOURCES
            ):
                return None
            return CapabilityObservation(
                provider=row.provider,
                model=row.model,
                endpoint_key=row.endpoint_key,
                capability=row.capability,  # type: ignore[arg-type]
                status=row.status,  # type: ignore[arg-type]
                source=row.source,  # type: ignore[arg-type]
                detail=row.detail,
            )

    def save(self, observation: CapabilityObservation) -> None:
        key = (
            observation.provider.casefold().strip(),
            observation.model.casefold().strip(),
            observation.endpoint_key,
            observation.capability,
        )
        with self.database.session() as session:
            row = session.get(UtilityProviderCapabilityRecord, key)
            if row is None:
                row = UtilityProviderCapabilityRecord(
                    provider=key[0],
                    model=key[1],
                    endpoint_key=observation.endpoint_key,
                    capability=observation.capability,
                    status=observation.status,
                    source=observation.source,
                    detail=observation.detail,
                )
                session.add(row)
            else:
                row.status = observation.status
                row.source = observation.source
                row.detail = observation.detail
            session.commit()


__all__ = ["ProviderCapabilityPersistence"]
