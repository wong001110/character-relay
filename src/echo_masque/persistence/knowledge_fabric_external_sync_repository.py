"""Derived conditional-sync state for external Knowledge Fabric Sources."""

from __future__ import annotations

from datetime import UTC, datetime

from echo_masque.knowledge_fabric_external_policy import (
    WEBSITE_PUBLIC_HTTPS_SOURCE_TYPE,
    normalized_website_validator,
)
from echo_masque.persistence.database import Database
from echo_masque.persistence.knowledge_fabric_models import (
    KnowledgeExternalSourceSyncStateRecord,
    KnowledgeSourceRecord,
)


class KnowledgeFabricExternalSyncRepository:
    """Persist only bounded validators/outcomes, never a response body or source credential."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def require_website_source(self, source_id: str) -> KnowledgeSourceRecord:
        with self.database.session() as session:
            source = session.get(KnowledgeSourceRecord, source_id)
            if source is None:
                raise KeyError("source")
            if source.source_type != WEBSITE_PUBLIC_HTTPS_SOURCE_TYPE:
                raise ValueError("External Website sync requires a public HTTPS Website Source.")
            return source

    def get_state(self, source_id: str) -> KnowledgeExternalSourceSyncStateRecord | None:
        with self.database.session() as session:
            return session.get(KnowledgeExternalSourceSyncStateRecord, source_id)

    def record_outcome(
        self,
        *,
        source_id: str,
        outcome: str,
        error_code: str | None = None,
        etag: str | None = None,
        last_modified: str | None = None,
        changed: bool = False,
        checked_at: datetime | None = None,
    ) -> KnowledgeExternalSourceSyncStateRecord:
        """Atomically update a Source's visible timestamps and its derived validator state."""

        if outcome not in {"changed", "failed", "not_modified", "unchanged"}:
            raise ValueError("External Website sync outcome is invalid.")
        if error_code is not None and error_code not in {
            "authorization_failed",
            "content_size_rejected",
            "content_type_rejected",
            "fetch_failed",
            "http_failed",
            "invalid_encoding",
            "redirect_refused",
            "source_rejected",
            "validator_rejected",
        }:
            raise ValueError("External Website sync error code is invalid.")
        now = checked_at or datetime.now(UTC)
        with self.database.session() as session:
            source = session.get(KnowledgeSourceRecord, source_id)
            if source is None:
                raise KeyError("source")
            if source.source_type != WEBSITE_PUBLIC_HTTPS_SOURCE_TYPE:
                raise ValueError("External Website sync requires a public HTTPS Website Source.")
            state = session.get(KnowledgeExternalSourceSyncStateRecord, source_id)
            if state is None:
                state = KnowledgeExternalSourceSyncStateRecord(source_id=source_id)
                session.add(state)
            if etag is not None:
                normalized_etag = normalized_website_validator(etag)
                if normalized_etag is not None:
                    state.etag = normalized_etag
            if last_modified is not None:
                normalized_last_modified = normalized_website_validator(last_modified)
                if normalized_last_modified is not None:
                    state.last_modified = normalized_last_modified
            state.last_outcome = outcome
            state.last_error_code = error_code
            source.last_checked_at = now
            if changed:
                source.last_changed_at = now
            session.commit()
            session.refresh(state)
            return state


__all__ = ["KnowledgeFabricExternalSyncRepository"]
