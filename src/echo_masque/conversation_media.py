"""Rehydrate media a Character actually perceived in earlier conversation turns."""

from __future__ import annotations

import re
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from echo_masque.api.connector_schemas import DiscordInboundMessage
from echo_masque.config import get_settings
from echo_masque.conversation_media_graph import ConversationMediaGraphService
from echo_masque.expression_retrieval import semantic_tokens
from echo_masque.live_media import LiveMediaContext
from echo_masque.persistence.conversation_media_models import ConversationMediaReferenceRecord
from echo_masque.persistence.conversation_media_repository import (
    ConversationMediaReferenceRepository,
)
from echo_masque.persistence.conversation_structure_repository import (
    ConversationStructureRepository,
)
from echo_masque.persistence.entity_evidence_repository import EntityEvidenceRepository
from echo_masque.persistence.semantic_vector_repository import SemanticVectorRepository
from echo_masque.semantic_participation import (
    FastEmbedSemanticEncoder,
    SemanticEmbeddingUnavailable,
    SemanticEncoder,
    _cosine,
)

_DEICTIC_MEDIA = re.compile(
    r"(?:刚才|剛才|上面|前面|那个|那個|那张|那張|那幅|那段|那个视频|那個影片|那篇|刚刚|剛剛|"
    r"previous|earlier|above|that\s+(?:image|picture|photo|video|clip|article|link)|"
    r"the\s+(?:image|picture|photo|video|clip|article|link)\s+(?:above|before))",
    re.IGNORECASE,
)
_READABLE_TEXT_QUERY = re.compile(
    r"(?:文字|文本|字幕|写着|寫著|写了|寫了|什么字|什麼字|显示|顯示|"
    r"价格|價格|价钱|價錢|容量|数字|數字|编号|編號|uid|"
    r"\b(?:text|read|written|says?|ocr|number|price|capacity|teks|tertulis|nombor|harga|berapa)\b)",
    re.IGNORECASE,
)
_DISCORD_INLINE = re.compile(r"<@!?\d+>|<a?:[A-Za-z0-9_]+:\d+>|https?://\S+", re.IGNORECASE)
_MEANINGFUL_CHAR = re.compile(r"[A-Za-z0-9\u3400-\u9fff]")
_MEDIA_VECTOR_NAMESPACE = "conversation-media"
_AUTO_SEMANTIC_MINIMUM = 0.46
_EXPLICIT_SEMANTIC_MINIMUM = 0.38
_HYBRID_MINIMUM = 0.45
_TOP_MARGIN = 0.05
_RECALL_TOKEN_BUDGET = 900
_AUTO_RECALL_MAX_AGE = timedelta(hours=24)
_AUTO_RECALL_MIN_MEANINGFUL_CHARS = 3


@dataclass(frozen=True)
class ConversationMediaMemory:
    message_id: str
    context: LiveMediaContext
    source_uri: str = ""
    recall_query: str = ""


class ConversationMediaReferenceService:
    """Persist perceived media and resolve exact, semantic, and recent references."""

    def __init__(
        self,
        repository: ConversationMediaReferenceRepository,
        *,
        semantic_encoder: SemanticEncoder | None = None,
        semantic_enabled: bool | None = None,
    ) -> None:
        self.repository = repository
        settings = get_settings()
        self._settings = settings
        self._semantic_encoder = semantic_encoder
        self._semantic_enabled = (
            semantic_enabled
            if semantic_enabled is not None
            else settings.semantic_embedding_runtime_enabled
            and settings.media_semantic_recall_enabled
        )
        self._semantic_vectors = SemanticVectorRepository(repository.database)
        self._media_graph = ConversationMediaGraphService(
            EntityEvidenceRepository(repository.database),
            ConversationStructureRepository(repository.database),
        )

    def _encoder(self) -> SemanticEncoder:
        if self._semantic_encoder is None:
            if not self._semantic_enabled:
                raise SemanticEmbeddingUnavailable("Semantic Media Recall is disabled.")
            self._semantic_encoder = FastEmbedSemanticEncoder(
                model_name=self._settings.semantic_embedding_model,
                model_file=self._settings.semantic_embedding_model_file,
                cache_dir=self._settings.semantic_embedding_cache_dir,
                dimension=self._settings.semantic_embedding_dimension,
            )
        return self._semantic_encoder

    @staticmethod
    def _semantic_text(context: LiveMediaContext) -> str:
        sections = [
            f"Media type: {context.kind}",
            f"Label: {context.label}" if context.label else "",
            f"Summary: {context.summary}",
            f"Readable text: {context.visible_text}" if context.visible_text else "",
            "Details: " + "; ".join(context.notable_details) if context.notable_details else "",
        ]
        return "\n".join(item for item in sections if item)[:20_000]

    def _ensure_vector(
        self,
        *,
        owner_id: str,
        record: ConversationMediaReferenceRecord,
        context: LiveMediaContext,
    ) -> list[float]:
        encoder = self._encoder()
        semantic_text = self._semantic_text(context)
        source_hash = self._semantic_vectors.source_hash(
            semantic_text, encoder.model_name, encoder.dimension
        )
        cached = self._semantic_vectors.get(
            owner_id=owner_id,
            namespace=_MEDIA_VECTOR_NAMESPACE,
            resource_id=record.id,
            model_name=encoder.model_name,
            dimension=encoder.dimension,
            source_hash=source_hash,
        )
        if cached is not None:
            return cached
        vector = encoder.embed_passage(semantic_text)
        self._semantic_vectors.upsert(
            owner_id=owner_id,
            namespace=_MEDIA_VECTOR_NAMESPACE,
            resource_id=record.id,
            semantic_text=semantic_text,
            model_name=encoder.model_name,
            dimension=encoder.dimension,
            vector=vector,
        )
        return vector

    def remember_perceived(
        self,
        *,
        owner_id: str,
        deployment_id: str,
        character_card_id: str,
        payload: DiscordInboundMessage,
        contexts: tuple[LiveMediaContext, ...],
    ) -> None:
        source_uris = self._source_uris(payload, contexts)
        for index, context in enumerate(contexts[:5]):
            record = self.repository.remember(
                owner_id=owner_id,
                deployment_id=deployment_id,
                character_card_id=character_card_id,
                guild_id=payload.guild_id,
                channel_id=payload.channel_id,
                thread_id=payload.thread_id,
                message_id=payload.message_id,
                context=context,
                source_uri=source_uris[index] if index < len(source_uris) else "",
            )
            with suppress(Exception):
                self._media_graph.project_perceived(
                    record=record,
                    context=context,
                    connection_id=payload.connection_id,
                )
            if self._semantic_enabled:
                with suppress(SemanticEmbeddingUnavailable, ValueError, RuntimeError):
                    self._ensure_vector(owner_id=owner_id, record=record, context=context)

    @staticmethod
    def _contextual_query(payload: DiscordInboundMessage) -> str:
        current = payload.text.strip()
        previous = [
            item.text.strip()
            for item in payload.recent_messages
            if item.message_id != payload.message_id
            and not item.is_bot
            and item.author_id == payload.author_id
            and item.text.strip()
        ][-2:]
        return "\n".join([*previous, current])[-4000:].strip()

    @staticmethod
    def _automatic_recall_allowed(text: str) -> bool:
        cleaned = _DISCORD_INLINE.sub(" ", text)
        meaningful = _MEANINGFUL_CHAR.findall(cleaned)
        if len(meaningful) < _AUTO_RECALL_MIN_MEANINGFUL_CHARS:
            return False
        return len(set(value.casefold() for value in meaningful)) != 1

    @staticmethod
    def _aware_utc(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    @staticmethod
    def _needs_readable_text(query: str) -> bool:
        return bool(_READABLE_TEXT_QUERY.search(query))

    def _semantic_recent(
        self,
        *,
        deployment_id: str,
        character_card_id: str,
        payload: DiscordInboundMessage,
    ) -> list[ConversationMediaReferenceRecord]:
        if not self._semantic_enabled:
            return []
        explicit = bool(_DEICTIC_MEDIA.search(payload.text))
        if not explicit and not self._automatic_recall_allowed(payload.text):
            return []
        query = self._contextual_query(payload)
        if not query:
            return []
        recent = self.repository.recent(
            deployment_id=deployment_id,
            character_card_id=character_card_id,
            guild_id=payload.guild_id,
            channel_id=payload.channel_id,
            thread_id=payload.thread_id,
            limit=10,
        )
        if not explicit:
            cutoff = datetime.now(UTC) - _AUTO_RECALL_MAX_AGE
            recent = [item for item in recent if self._aware_utc(item.created_at) >= cutoff]
        if not recent:
            return []
        with suppress(Exception):
            linked_keys = self._media_graph.active_thread_media_keys(
                owner_id=recent[0].owner_id,
                connection_id=payload.connection_id,
                guild_id=payload.guild_id,
                channel_id=payload.channel_id,
                thread_id=payload.thread_id,
            )
            if linked_keys:
                narrowed = [
                    item
                    for item in recent
                    if self._media_graph.media_key(item.source_key) in linked_keys
                ]
                if narrowed:
                    recent = narrowed
        try:
            encoder = self._encoder()
            query_vector = encoder.embed_query(query)
        except (SemanticEmbeddingUnavailable, ValueError, RuntimeError):
            return []
        semantic_minimum = _EXPLICIT_SEMANTIC_MINIMUM if explicit else _AUTO_SEMANTIC_MINIMUM
        ranked: list[tuple[float, float, ConversationMediaReferenceRecord]] = []
        denominator = max(1, len(recent) - 1)
        for index, record in enumerate(recent):
            if not record.context_json:
                continue
            try:
                context = LiveMediaContext.model_validate_json(record.context_json)
                vector = self._ensure_vector(
                    owner_id=record.owner_id, record=record, context=context
                )
            except (ValueError, SemanticEmbeddingUnavailable, RuntimeError):
                continue
            semantic = _cosine(query_vector, vector)
            if semantic < semantic_minimum:
                continue
            recency = 1.0 - (index / denominator)
            hybrid = semantic * 0.92 + recency * 0.05 + (0.03 if explicit else 0.0)
            if hybrid >= _HYBRID_MINIMUM:
                ranked.append((hybrid, semantic, record))
        ranked.sort(key=lambda item: (-item[0], -item[1], item[2].created_at))
        if not ranked:
            return []
        if not explicit and len(ranked) > 1 and ranked[0][1] - ranked[1][1] < _TOP_MARGIN:
            return []
        return [ranked[0][2]]

    def resolve_for_turn(
        self,
        *,
        deployment_id: str,
        character_card_id: str,
        payload: DiscordInboundMessage,
    ) -> tuple[ConversationMediaMemory, ...]:
        records: list[ConversationMediaReferenceRecord] = []
        if payload.reply_to_message_id:
            records = self.repository.for_message(
                deployment_id=deployment_id,
                character_card_id=character_card_id,
                guild_id=payload.guild_id,
                channel_id=payload.channel_id,
                thread_id=payload.thread_id,
                message_id=payload.reply_to_message_id,
            )
        if not records:
            records = self._semantic_recent(
                deployment_id=deployment_id,
                character_card_id=character_card_id,
                payload=payload,
            )
        if not records and _DEICTIC_MEDIA.search(payload.text):
            records = self.repository.recent(
                deployment_id=deployment_id,
                character_card_id=character_card_id,
                guild_id=payload.guild_id,
                channel_id=payload.channel_id,
                thread_id=payload.thread_id,
                limit=1,
            )
        return tuple(
            self._memory(item, query=payload.text) for item in records if item.context_json
        )

    @staticmethod
    def _excerpt(value: str, query: str, maximum: int) -> str:
        text = " ".join(value.split()).strip()
        if len(text) <= maximum:
            return text
        if maximum < 300:
            return text[:maximum]
        query_tokens = set(semantic_tokens(query))
        window = min(700, maximum)
        step = max(200, window - 140)
        candidates: list[tuple[int, int, str]] = []
        for start in range(0, len(text), step):
            chunk = text[start : start + window].strip()
            if not chunk:
                continue
            overlap = len(query_tokens.intersection(semantic_tokens(chunk))) if query_tokens else 0
            candidates.append((overlap, -start, chunk))
            if start + window >= len(text):
                break
        if not candidates:
            return text[:maximum]
        _, neg_start, best = max(candidates, key=lambda item: (item[0], item[1]))
        start = -neg_start
        prefix = "…" if start > 0 else ""
        suffix = "…" if start + len(best) < len(text) else ""
        return f"{prefix}{best}{suffix}"[:maximum]

    @classmethod
    def guidance(cls, memories: tuple[ConversationMediaMemory, ...]) -> tuple[str, ...]:
        if not memories:
            return ()
        maximum_chars = _RECALL_TOKEN_BUDGET * 4
        lines = [
            "Remembered media perception from this conversation:",
            "Runtime truth: this content was actually perceived earlier. "
            "Use it only as remembered evidence for the current follow-up; "
            "do not invent new media facts.",
        ]
        used = sum(len(item) + 1 for item in lines)
        per_memory = max(600, (maximum_chars - used) // max(1, len(memories)))
        for memory in memories:
            context = memory.context
            block = [f"[remembered from Discord message {memory.message_id}]"]
            summary = " ".join(context.summary.split()).strip()
            if summary:
                block.append(f"Summary: {summary[: min(1200, per_memory - 80)]}")
            remaining = per_memory - sum(len(item) + 1 for item in block)
            if (
                context.visible_text
                and cls._needs_readable_text(memory.recall_query)
                and remaining > 300
            ):
                excerpt = cls._excerpt(
                    context.visible_text,
                    memory.recall_query,
                    min(1800, remaining),
                )
                if excerpt:
                    block.append(f"Relevant readable excerpt: {excerpt}")
            for item in block:
                if used + len(item) + 1 > maximum_chars:
                    break
                lines.append(item)
                used += len(item) + 1
            if used >= maximum_chars:
                break
        return tuple(lines)

    @staticmethod
    def _memory(
        record: ConversationMediaReferenceRecord, *, query: str = ""
    ) -> ConversationMediaMemory:
        return ConversationMediaMemory(
            message_id=record.message_id,
            context=LiveMediaContext.model_validate_json(record.context_json),
            source_uri=record.source_uri,
            recall_query=query,
        )

    @staticmethod
    def _source_uris(
        payload: DiscordInboundMessage,
        contexts: tuple[LiveMediaContext, ...],
    ) -> list[str]:
        image_urls = [
            attachment.url
            for attachment in payload.attachments
            if attachment.content_type.casefold().startswith("image/")
            or attachment.filename.casefold().endswith(
                (".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif")
            )
        ]
        image_index = 0
        values: list[str] = []
        for context in contexts:
            uri = ""
            if context.kind == "image" and image_index < len(image_urls):
                uri = image_urls[image_index]
                image_index += 1
            elif context.source_key.startswith("url:"):
                uri = context.source_key[4:]
            values.append(uri)
        return values


__all__ = ["ConversationMediaMemory", "ConversationMediaReferenceService"]
