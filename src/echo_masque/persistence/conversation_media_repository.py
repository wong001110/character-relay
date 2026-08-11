"""Persistence for Character-scoped conversation media references."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import delete, select, update

from echo_masque.persistence.conversation_media_models import ConversationMediaReferenceRecord
from echo_masque.persistence.database import Database
from echo_masque.persistence.semantic_vector_repository import SemanticVectorRepository

if TYPE_CHECKING:
    from echo_masque.live_media import LiveMediaContext

_MEDIA_VECTOR_NAMESPACE = "conversation-media"


class ConversationMediaReferenceRepository:
    """Remember only media a Character actually perceived in a conversation."""

    def __init__(
        self,
        database: Database,
        *,
        ttl: timedelta = timedelta(days=30),
    ) -> None:
        self.database = database
        self.ttl = ttl
        self.semantic_vectors = SemanticVectorRepository(database)

    def remember(
        self,
        *,
        owner_id: str,
        deployment_id: str,
        character_card_id: str,
        guild_id: str,
        channel_id: str,
        thread_id: str,
        message_id: str,
        context: LiveMediaContext,
        source_uri: str = "",
        now: datetime | None = None,
    ) -> ConversationMediaReferenceRecord:
        current = now or datetime.now(UTC)
        with self.database.session() as session:
            record = session.scalar(
                select(ConversationMediaReferenceRecord).where(
                    ConversationMediaReferenceRecord.deployment_id == deployment_id,
                    ConversationMediaReferenceRecord.character_card_id == character_card_id,
                    ConversationMediaReferenceRecord.message_id == message_id,
                    ConversationMediaReferenceRecord.source_key == context.source_key,
                )
            )
            if record is None:
                record = ConversationMediaReferenceRecord(
                    id=str(uuid4()),
                    owner_id=owner_id,
                    deployment_id=deployment_id,
                    character_card_id=character_card_id,
                    guild_id=guild_id,
                    channel_id=channel_id,
                    thread_id=thread_id,
                    message_id=message_id,
                    source_key=context.source_key,
                    kind=context.kind,
                    label=context.label,
                    context_json=context.model_dump_json(),
                    source_uri=source_uri[:6000],
                    created_at=current,
                    expires_at=current + self.ttl,
                )
                session.add(record)
            else:
                record.kind = context.kind
                record.label = context.label
                record.context_json = context.model_dump_json()
                if source_uri:
                    record.source_uri = source_uri[:6000]
                record.expires_at = current + self.ttl
            session.commit()
            session.refresh(record)
            return record

    def remember_generated_reference(
        self,
        *,
        owner_id: str,
        deployment_id: str,
        character_card_id: str,
        guild_id: str,
        channel_id: str,
        thread_id: str,
        message_id: str,
        source_key: str,
        label: str,
        source_uri: str,
        now: datetime | None = None,
    ) -> ConversationMediaReferenceRecord:
        """Keep a generated-image source reusable without inventing visual perception facts."""

        clean_uri = source_uri.strip()
        if not clean_uri:
            raise ValueError("Generated media reference requires a source URI.")
        current = now or datetime.now(UTC)
        bounded_source_key = source_key[:500]
        generated_ttl = min(self.ttl, timedelta(hours=24))
        with self.database.session() as session:
            record = session.scalar(
                select(ConversationMediaReferenceRecord).where(
                    ConversationMediaReferenceRecord.deployment_id == deployment_id,
                    ConversationMediaReferenceRecord.character_card_id == character_card_id,
                    ConversationMediaReferenceRecord.message_id == message_id,
                    ConversationMediaReferenceRecord.source_key == bounded_source_key,
                )
            )
            if record is None:
                record = ConversationMediaReferenceRecord(
                    id=str(uuid4()),
                    owner_id=owner_id,
                    deployment_id=deployment_id,
                    character_card_id=character_card_id,
                    guild_id=guild_id,
                    channel_id=channel_id,
                    thread_id=thread_id,
                    message_id=message_id,
                    source_key=bounded_source_key,
                    kind="image",
                    label=label[:300],
                    context_json="",
                    source_uri=clean_uri[:6000],
                    created_at=current,
                    expires_at=current + generated_ttl,
                )
                session.add(record)
            else:
                record.kind = "image"
                record.label = label[:300]
                record.context_json = ""
                record.source_uri = clean_uri[:6000]
                record.expires_at = current + generated_ttl
            session.commit()
            session.refresh(record)
            return record

    def for_message(
        self,
        *,
        deployment_id: str,
        character_card_id: str,
        guild_id: str,
        channel_id: str,
        thread_id: str,
        message_id: str,
        now: datetime | None = None,
        limit: int = 5,
    ) -> list[ConversationMediaReferenceRecord]:
        current = now or datetime.now(UTC)
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(ConversationMediaReferenceRecord)
                    .where(
                        ConversationMediaReferenceRecord.deployment_id == deployment_id,
                        ConversationMediaReferenceRecord.character_card_id == character_card_id,
                        ConversationMediaReferenceRecord.guild_id == guild_id,
                        ConversationMediaReferenceRecord.channel_id == channel_id,
                        ConversationMediaReferenceRecord.thread_id == thread_id,
                        ConversationMediaReferenceRecord.message_id == message_id,
                        ConversationMediaReferenceRecord.expires_at > current,
                    )
                    .order_by(ConversationMediaReferenceRecord.created_at.asc())
                    .limit(max(1, min(limit, 10)))
                )
            )

    def recent(
        self,
        *,
        deployment_id: str,
        character_card_id: str,
        guild_id: str,
        channel_id: str,
        thread_id: str,
        now: datetime | None = None,
        limit: int = 5,
    ) -> list[ConversationMediaReferenceRecord]:
        current = now or datetime.now(UTC)
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(ConversationMediaReferenceRecord)
                    .where(
                        ConversationMediaReferenceRecord.deployment_id == deployment_id,
                        ConversationMediaReferenceRecord.character_card_id == character_card_id,
                        ConversationMediaReferenceRecord.guild_id == guild_id,
                        ConversationMediaReferenceRecord.channel_id == channel_id,
                        ConversationMediaReferenceRecord.thread_id == thread_id,
                        ConversationMediaReferenceRecord.expires_at > current,
                    )
                    .order_by(ConversationMediaReferenceRecord.created_at.desc())
                    .limit(max(1, min(limit, 20)))
                )
            )

    def purge_expired(self, *, now: datetime | None = None, limit: int = 500) -> int:
        current = now or datetime.now(UTC)
        bounded = max(1, min(limit, 5000))
        with self.database.session() as session:
            records = list(
                session.scalars(
                    select(ConversationMediaReferenceRecord)
                    .where(ConversationMediaReferenceRecord.expires_at <= current)
                    .order_by(ConversationMediaReferenceRecord.expires_at.asc())
                    .limit(bounded)
                )
            )
            if not records:
                return 0
            ids = [item.id for item in records]
            session.execute(
                delete(ConversationMediaReferenceRecord).where(
                    ConversationMediaReferenceRecord.id.in_(ids)
                )
            )
            session.commit()
        for item in records:
            self.semantic_vectors.delete_resource(
                owner_id=item.owner_id,
                namespace=_MEDIA_VECTOR_NAMESPACE,
                resource_id=item.id,
            )
        return len(records)

    def claim_owner(self, source_owner_id: str, target_owner_id: str) -> int:
        with self.database.session() as session:
            result = session.execute(
                update(ConversationMediaReferenceRecord)
                .where(ConversationMediaReferenceRecord.owner_id == source_owner_id)
                .values(owner_id=target_owner_id)
            )
            session.commit()
            count = int(getattr(result, "rowcount", 0) or 0)
        # Semantic vectors are a cache; rebuild them lazily for the claimed owner.
        self.semantic_vectors.delete_namespace(
            owner_id=source_owner_id,
            namespace=_MEDIA_VECTOR_NAMESPACE,
        )
        return count

    def delete_owner(self, owner_id: str) -> int:
        with self.database.session() as session:
            result = session.execute(
                delete(ConversationMediaReferenceRecord).where(
                    ConversationMediaReferenceRecord.owner_id == owner_id
                )
            )
            session.commit()
            count = int(getattr(result, "rowcount", 0) or 0)
        self.semantic_vectors.delete_namespace(
            owner_id=owner_id,
            namespace=_MEDIA_VECTOR_NAMESPACE,
        )
        return count
