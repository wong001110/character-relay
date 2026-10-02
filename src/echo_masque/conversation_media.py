"""Rehydrate only source-linked media a Character actually perceived."""

from __future__ import annotations

import re
from dataclasses import dataclass

from echo_masque.api.connector_schemas import DiscordInboundMessage
from echo_masque.live_media import LiveMediaContext
from echo_masque.persistence.conversation_media_models import ConversationMediaReferenceRecord
from echo_masque.persistence.conversation_media_repository import (
    ConversationMediaReferenceRepository,
)
from echo_masque.persistence.deployment_repository import DeploymentRepository
from echo_masque.persistence.room_repository import RoomRepository
from echo_masque.room_routing import RoomScope
from echo_masque.sparse_retrieval import semantic_tokens

_READABLE_TEXT_QUERY = re.compile(
    r"(?:文字|文本|字幕|写着|寫著|写了|寫了|什么字|什麼字|显示|顯示|"
    r"价格|價格|价钱|價錢|容量|数字|數字|编号|編號|uid|"
    r"\b(?:text|read|written|says?|ocr|number|price|capacity|teks|tertulis|nombor|harga|berapa)\b)",
    re.IGNORECASE,
)

_RECALL_TOKEN_BUDGET = 900


@dataclass(frozen=True)
class ConversationMediaMemory:
    message_id: str
    context: LiveMediaContext
    source_uri: str = ""
    recall_query: str = ""


class ConversationMediaReferenceService:
    """Keep perceived evidence, not automatic semantic recall or an Entity/Thread graph."""

    def __init__(self, repository: ConversationMediaReferenceRepository) -> None:
        self.repository = repository
        self.rooms = RoomRepository(repository.database)
        self.deployments = DeploymentRepository(repository.database)

    def _scope(
        self,
        deployment_id: str,
        card_id: str,
        payload: DiscordInboundMessage,
    ) -> RoomScope | None:
        deployment = self.deployments.deployment_matches_discord_destination(
            deployment_id,
            connection_id=payload.connection_id,
            guild_id=payload.guild_id,
            channel_id=payload.channel_id,
            thread_id=payload.thread_id,
            category_id=payload.category_id,
        )
        if deployment is None or deployment.character_card_id != card_id:
            return None
        scope = RoomScope(
            owner_id=deployment.owner_id,
            connection_id=payload.connection_id,
            guild_id=payload.guild_id,
            channel_id=payload.channel_id,
            thread_id=payload.thread_id,
        )
        return scope if self.rooms.can_read(scope, max_age_seconds=300) else None

    def remember_perceived(
        self,
        *,
        owner_id: str,
        deployment_id: str,
        character_card_id: str,
        payload: DiscordInboundMessage,
        contexts: tuple[LiveMediaContext, ...],
    ) -> None:
        scope = self._scope(deployment_id, character_card_id, payload)
        if scope is None or scope.owner_id != owner_id:
            return
        source = self.rooms.get(scope, payload.message_id)
        if source is None or source.message.deleted or not source.message.content_available:
            return
        source_uris = self._source_uris(payload, contexts)
        for index, context in enumerate(contexts[:5]):
            self.repository.remember(
                owner_id=owner_id,
                deployment_id=deployment_id,
                character_card_id=character_card_id,
                guild_id=payload.guild_id,
                channel_id=payload.channel_id,
                thread_id=payload.thread_id,
                message_id=payload.message_id,
                context=context,
                source_uri=source_uris[index] if index < len(source_uris) else "",
                source_fingerprint=source.message.draft_fingerprint(),
            )

    @staticmethod
    def _needs_readable_text(query: str) -> bool:
        return bool(_READABLE_TEXT_QUERY.search(query))

    def resolve_for_turn(
        self,
        *,
        deployment_id: str,
        character_card_id: str,
        payload: DiscordInboundMessage,
    ) -> tuple[ConversationMediaMemory, ...]:
        scope = self._scope(deployment_id, character_card_id, payload)
        if scope is None or not payload.reply_to_message_id:
            return ()
        source = self.rooms.get(scope, payload.reply_to_message_id)
        if source is None or source.message.deleted or not source.message.content_available:
            return ()
        records = self.repository.for_message(
            deployment_id=deployment_id,
            character_card_id=character_card_id,
            guild_id=payload.guild_id,
            channel_id=payload.channel_id,
            thread_id=payload.thread_id,
            message_id=payload.reply_to_message_id,
        )
        if self._scope(deployment_id, character_card_id, payload) is None:
            return ()
        current = self.rooms.get(scope, payload.reply_to_message_id)
        if current is None or current.message.deleted:
            return ()
        return tuple(
            self._memory(record, query=payload.text)
            for record in records
            if record.context_json
            and record.owner_id == scope.owner_id
            and record.source_fingerprint == current.message.draft_fingerprint()
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
