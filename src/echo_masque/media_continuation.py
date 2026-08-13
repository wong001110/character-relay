"""Semantic continuation for shared media a Character previously chose not to inspect."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import ClassVar

from sqlalchemy import delete, select

from echo_masque.api.connector_schemas import DiscordInboundMessage
from echo_masque.config import Settings, get_settings
from echo_masque.content_resolver import resolve_static_url
from echo_masque.persistence.conversation_media_models import ConversationMediaReferenceRecord
from echo_masque.persistence.conversation_media_repository import (
    ConversationMediaReferenceRepository,
)
from echo_masque.semantic_participation import (
    FastEmbedSemanticEncoder,
    SemanticEmbeddingUnavailable,
    SemanticEncoder,
    _cosine,
)

_URL_PATTERN = re.compile(r"https?://[^\s<>\]\[(){}\"']+", re.IGNORECASE)
_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif")
_SKIPPED_PREFIX = "skipped-topic:"
_SKIPPED_TTL = timedelta(hours=6)
_MEDIA_RECONSIDER_MINIMUM = 0.47
_MEDIA_RECONSIDER_PROFILE = (
    "The member wants the Character to open, inspect, watch, or read media or a link that was "
    "shared earlier in this same conversation topic but was not inspected before. Examples "
    "include asking the Character to look at it now, reconsider it, inspect the previous video, "
    "or go back and open the earlier shared content."
)


@dataclass(frozen=True, slots=True)
class SkippedMediaReference:
    id: str
    owner_id: str
    message_id: str
    source_uri: str
    kind: str
    label: str
    topic_id: str


class SkippedMediaContinuationService:
    """Retain source references without turning unseen content into perceived memory."""

    _profile_vectors: ClassVar[dict[tuple[str, int], list[float]]] = {}
    _profile_lock: ClassVar[Lock] = Lock()

    def __init__(
        self,
        repository: ConversationMediaReferenceRepository,
        *,
        settings: Settings | None = None,
        encoder: SemanticEncoder | None = None,
        semantic_enabled: bool | None = None,
    ) -> None:
        self.repository = repository
        self.settings = settings or get_settings()
        self._encoder = encoder
        self._semantic_enabled = (
            semantic_enabled
            if semantic_enabled is not None
            else self.settings.semantic_embedding_runtime_enabled
        )

    def _get_encoder(self) -> SemanticEncoder:
        if self._encoder is None:
            self._encoder = FastEmbedSemanticEncoder(
                model_name=self.settings.semantic_embedding_model,
                model_file=self.settings.semantic_embedding_model_file,
                cache_dir=self.settings.semantic_embedding_cache_dir,
                dimension=self.settings.semantic_embedding_dimension,
            )
        return self._encoder

    @staticmethod
    def _topic_prefix(topic_id: str) -> str:
        return f"{_SKIPPED_PREFIX}{topic_id}:"

    @classmethod
    def _source_key(cls, topic_id: str, source_uri: str) -> str:
        digest = hashlib.sha256(source_uri.encode()).hexdigest()
        return f"{cls._topic_prefix(topic_id)}{digest}"[:500]

    @staticmethod
    def _visible_image_attachment(content_type: str, filename: str) -> bool:
        return content_type.casefold().startswith("image/") or filename.casefold().endswith(
            _IMAGE_EXTENSIONS
        )

    @classmethod
    def _sources(cls, payload: DiscordInboundMessage) -> list[tuple[str, str, str]]:
        values: list[tuple[str, str, str]] = []
        for attachment in payload.attachments[:6]:
            if cls._visible_image_attachment(
                attachment.content_type,
                attachment.filename,
            ):
                continue
            kind = (
                "video"
                if attachment.content_type.casefold().startswith("video/")
                else "media"
            )
            if attachment.url.strip():
                label = attachment.filename.strip() or "Discord attachment"
                values.append((attachment.url.strip(), kind, label))
        for embed in payload.embeds[:6]:
            uri = embed.url.strip()
            if uri:
                label = embed.title.strip() or embed.provider_name.strip() or "Shared link"
                values.append((uri, "link", label))
        trailing = ".,!?;:\uff0c\u3002\uff01\uff1f\uff1b\uff1a"
        for match in _URL_PATTERN.findall(payload.text):
            raw = match.rstrip(trailing)
            kind = "link"
            label = "Shared link"
            try:
                source = resolve_static_url(raw)
                kind = source.kind or "link"
                label = source.platform or source.kind or label
            except ValueError:
                pass
            values.append((raw, kind, label))
        deduped: list[tuple[str, str, str]] = []
        seen: set[str] = set()
        for uri, kind, label in values:
            if not uri or uri in seen:
                continue
            seen.add(uri)
            deduped.append((uri[:6000], kind[:30], label[:300]))
        return deduped[:5]

    def remember_skipped(
        self,
        *,
        owner_id: str,
        deployment_id: str,
        character_card_id: str,
        payload: DiscordInboundMessage,
        topic_id: str,
        now: datetime | None = None,
    ) -> tuple[SkippedMediaReference, ...]:
        """Persist only retrievable source metadata; no content observations are written."""

        topic = topic_id.strip()
        if not topic:
            return ()
        sources = self._sources(payload)
        if not sources:
            return ()
        current = now or datetime.now(UTC)
        results: list[SkippedMediaReference] = []
        with self.repository.database.session() as session:
            for source_uri, kind, label in sources:
                source_key = self._source_key(topic, source_uri)
                record = session.scalar(
                    select(ConversationMediaReferenceRecord).where(
                        ConversationMediaReferenceRecord.deployment_id == deployment_id,
                        ConversationMediaReferenceRecord.character_card_id == character_card_id,
                        ConversationMediaReferenceRecord.message_id == payload.message_id,
                        ConversationMediaReferenceRecord.source_key == source_key,
                    )
                )
                if record is None:
                    stable_id = (
                        f"{deployment_id}:{character_card_id}:{payload.message_id}:{source_key}"
                    )
                    record = ConversationMediaReferenceRecord(
                        id=hashlib.sha256(stable_id.encode()).hexdigest(),
                        owner_id=owner_id,
                        deployment_id=deployment_id,
                        character_card_id=character_card_id,
                        guild_id=payload.guild_id,
                        channel_id=payload.channel_id,
                        thread_id=payload.thread_id,
                        message_id=payload.message_id,
                        source_key=source_key,
                        kind=kind,
                        label=label,
                        context_json="",
                        source_uri=source_uri,
                        created_at=current,
                        expires_at=current + min(self.repository.ttl, _SKIPPED_TTL),
                    )
                    session.add(record)
                else:
                    record.kind = kind
                    record.label = label
                    record.context_json = ""
                    record.source_uri = source_uri
                    record.expires_at = current + min(self.repository.ttl, _SKIPPED_TTL)
                session.flush()
                results.append(self._reference(record, topic))
            session.commit()
        return tuple(results)

    @classmethod
    def _reference(
        cls,
        record: ConversationMediaReferenceRecord,
        topic_id: str,
    ) -> SkippedMediaReference:
        return SkippedMediaReference(
            id=record.id,
            owner_id=record.owner_id,
            message_id=record.message_id,
            source_uri=record.source_uri,
            kind=record.kind,
            label=record.label,
            topic_id=topic_id,
        )

    @classmethod
    def _profile_vector(cls, encoder: SemanticEncoder) -> list[float]:
        key = (encoder.model_name, encoder.dimension)
        cached = cls._profile_vectors.get(key)
        if cached is not None:
            return cached
        with cls._profile_lock:
            cached = cls._profile_vectors.get(key)
            if cached is not None:
                return cached
            vector = encoder.embed_passage(_MEDIA_RECONSIDER_PROFILE)
            cls._profile_vectors[key] = vector
            return vector

    def resolve_for_turn(
        self,
        *,
        deployment_id: str,
        character_card_id: str,
        payload: DiscordInboundMessage,
        topic_id: str,
        now: datetime | None = None,
    ) -> SkippedMediaReference | None:
        """Return a skipped source only for same-topic semantic inspection continuation."""

        topic = topic_id.strip()
        if not topic or payload.author_is_bot:
            return None
        current = now or datetime.now(UTC)
        prefix = self._topic_prefix(topic)
        with self.repository.database.session() as session:
            records = list(
                session.scalars(
                    select(ConversationMediaReferenceRecord)
                    .where(
                        ConversationMediaReferenceRecord.deployment_id == deployment_id,
                        ConversationMediaReferenceRecord.character_card_id == character_card_id,
                        ConversationMediaReferenceRecord.guild_id == payload.guild_id,
                        ConversationMediaReferenceRecord.channel_id == payload.channel_id,
                        ConversationMediaReferenceRecord.thread_id == payload.thread_id,
                        ConversationMediaReferenceRecord.context_json == "",
                        ConversationMediaReferenceRecord.source_uri != "",
                        ConversationMediaReferenceRecord.source_key.like(f"{prefix}%"),
                        ConversationMediaReferenceRecord.expires_at > current,
                    )
                    .order_by(ConversationMediaReferenceRecord.created_at.desc())
                    .limit(5)
                )
            )
        if not records:
            return None
        if payload.reply_to_message_id:
            exact = next(
                (
                    item
                    for item in records
                    if item.message_id == payload.reply_to_message_id
                ),
                None,
            )
            if exact is not None:
                return self._reference(exact, topic)
        query = " ".join(payload.text.split())[:4000]
        if not query or not self._semantic_enabled:
            return None
        try:
            encoder = self._get_encoder()
            score = _cosine(
                encoder.embed_query(query),
                self._profile_vector(encoder),
            )
        except (SemanticEmbeddingUnavailable, ValueError, RuntimeError):
            return None
        if score < _MEDIA_RECONSIDER_MINIMUM:
            return None
        return self._reference(records[0], topic)

    @staticmethod
    def payload_for_reference(
        current_payload: DiscordInboundMessage,
        reference: SkippedMediaReference,
    ) -> DiscordInboundMessage:
        """Rebuild a fetchable payload without pretending old content is in the new message."""

        return current_payload.model_copy(
            update={
                "message_id": reference.message_id,
                "text": reference.source_uri,
                "attachments": [],
                "embeds": [],
                "emojis": [],
                "stickers": [],
                "reply_to_message_id": "",
            }
        )

    def forget(self, reference: SkippedMediaReference) -> None:
        with self.repository.database.session() as session:
            session.execute(
                delete(ConversationMediaReferenceRecord).where(
                    ConversationMediaReferenceRecord.id == reference.id,
                    ConversationMediaReferenceRecord.owner_id == reference.owner_id,
                )
            )
            session.commit()


__all__ = ["SkippedMediaContinuationService", "SkippedMediaReference"]
