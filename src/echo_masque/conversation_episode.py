"""Episode projection service: organize raw conversation events without replacing them."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from echo_masque.persistence.conversation_episode_repository import ConversationEpisodeRepository

if TYPE_CHECKING:
    from echo_masque.api.connector_schemas import DiscordInboundMessage


@dataclass(slots=True)
class ConversationEpisodeProjectionService:
    repository: ConversationEpisodeRepository

    @staticmethod
    def _episode_key(payload: DiscordInboundMessage) -> str:
        burst_id = payload.conversation_burst_id.strip()
        if burst_id:
            return f"burst:{burst_id}"[:120]
        identity = "\x1f".join(
            (
                payload.connection_id,
                payload.guild_id,
                payload.channel_id,
                payload.thread_id,
                payload.message_id,
            )
        )
        return "message:" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:48]

    @staticmethod
    def _source_ids(payload: DiscordInboundMessage) -> list[str]:
        return list(
            dict.fromkeys(
                [
                    *payload.burst_source_message_ids,
                    payload.message_id,
                ]
            )
        )

    @staticmethod
    def _media_refs(payload: DiscordInboundMessage) -> list[str]:
        values = [f"message:{item}" for item in payload.burst_media_message_ids]
        values.extend(
            f"attachment:{item.attachment_id}"
            for item in payload.attachments
            if item.attachment_id
        )
        values.extend(f"url:{item.url}" for item in payload.embeds if item.url)
        return list(dict.fromkeys(values))[:20]

    def observe(
        self,
        *,
        owner_id: str,
        payload: DiscordInboundMessage,
        topic_id: str = "",
        topic_evidence: bool = True,
        now: datetime | None = None,
    ) -> None:
        current = now or datetime.now(UTC)
        summary = " ".join(payload.text.split())[:800]
        key_points = [summary] if summary else []
        self.repository.upsert_projection(
            owner_id=owner_id,
            platform="discord",
            connection_id=payload.connection_id,
            guild_id=payload.guild_id,
            channel_id=payload.channel_id,
            thread_id=payload.thread_id,
            episode_key=self._episode_key(payload),
            topic_id=topic_id if topic_evidence else "",
            burst_ids=[payload.conversation_burst_id] if payload.conversation_burst_id else [],
            source_message_ids=self._source_ids(payload),
            participant_refs=[payload.author_id] if payload.author_id else [],
            media_refs=self._media_refs(payload),
            summary=summary,
            key_points=key_points,
            status="closed",
            now=current,
        )


__all__ = ["ConversationEpisodeProjectionService"]
