"""Persistence for temporary generated-image delivery data."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import delete, select

from echo_masque.persistence.database import Database
from echo_masque.persistence.generated_media_models import GeneratedMediaArtifactRecord


class GeneratedMediaArtifactRepository:
    def __init__(self, database: Database, *, ttl: timedelta = timedelta(hours=24)) -> None:
        self.database = database
        self.ttl = ttl

    def create(
        self,
        *,
        owner_id: str,
        deployment_id: str,
        character_card_id: str,
        media_key: str,
        mime_type: str,
        filename: str,
        provider: str,
        model: str,
        content: bytes,
        now: datetime | None = None,
    ) -> GeneratedMediaArtifactRecord:
        current = now or datetime.now(UTC)
        record = GeneratedMediaArtifactRecord(
            id=str(uuid4()),
            owner_id=owner_id,
            deployment_id=deployment_id,
            character_card_id=character_card_id,
            media_key=media_key,
            mime_type=mime_type[:100],
            filename=filename[:255],
            provider=provider[:80],
            model=model[:200],
            content=content,
            created_at=current,
            expires_at=current + self.ttl,
        )
        with self.database.session() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def get(
        self,
        artifact_id: str,
        *,
        owner_id: str | None = None,
        now: datetime | None = None,
    ) -> GeneratedMediaArtifactRecord | None:
        current = now or datetime.now(UTC)
        with self.database.session() as session:
            query = select(GeneratedMediaArtifactRecord).where(
                GeneratedMediaArtifactRecord.id == artifact_id,
                GeneratedMediaArtifactRecord.expires_at > current,
            )
            if owner_id:
                query = query.where(GeneratedMediaArtifactRecord.owner_id == owner_id)
            return session.scalar(query)

    def purge_expired(self, *, now: datetime | None = None, limit: int = 200) -> int:
        current = now or datetime.now(UTC)
        bounded = max(1, min(limit, 2000))
        with self.database.session() as session:
            ids = list(
                session.scalars(
                    select(GeneratedMediaArtifactRecord.id)
                    .where(GeneratedMediaArtifactRecord.expires_at <= current)
                    .order_by(GeneratedMediaArtifactRecord.expires_at.asc())
                    .limit(bounded)
                )
            )
            if not ids:
                return 0
            session.execute(
                delete(GeneratedMediaArtifactRecord).where(
                    GeneratedMediaArtifactRecord.id.in_(ids)
                )
            )
            session.commit()
            return len(ids)
