"""Observed Topic Memory wrapper with single-decision reuse and trace enrichment."""

from __future__ import annotations

import hashlib
from collections import OrderedDict
from datetime import datetime

from echo_masque.conversation_topic import (
    ConversationTopicMemoryService,
    ConversationTopicSnapshot,
    TopicContinuityDecision,
)
from echo_masque.persistence.conversation_topic_models import ConversationTopicRecord

_CACHE_LIMIT = 128


class ObservedConversationTopicMemoryService(ConversationTopicMemoryService):
    """Reuse one semantic continuity decision across Tool Continuation and Topic mutation.

    ToolContinuation must inspect pending actions before Topic mutation, while observe_turn owns the
    Topic write. Both historically classified the same message independently. This wrapper keeps a
    small process-local hash-keyed cache so the second request receives the exact same decision.
    Raw message text is never retained in the cache key.
    """

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self._continuity_cache: OrderedDict[
            tuple[str, int, str], TopicContinuityDecision
        ] = OrderedDict()

    @staticmethod
    def _cache_key(
        *,
        text: str,
        active: ConversationTopicRecord,
    ) -> tuple[str, int, str]:
        digest = hashlib.sha256(" ".join(text.split()).encode("utf-8")).hexdigest()
        return active.id, active.capsule_version, digest

    def classify_continuity(
        self,
        *,
        text: str,
        active: ConversationTopicRecord,
        now: datetime | None = None,
    ) -> TopicContinuityDecision:
        key = self._cache_key(text=text, active=active)
        cached = self._continuity_cache.get(key)
        if cached is not None:
            self._continuity_cache.move_to_end(key)
            return cached
        decision = super().classify_continuity(text=text, active=active, now=now)
        self._continuity_cache[key] = decision
        self._continuity_cache.move_to_end(key)
        while len(self._continuity_cache) > _CACHE_LIMIT:
            self._continuity_cache.popitem(last=False)
        return decision

    def observe_turn(
        self,
        *,
        owner_id: str,
        payload: object,
        platform: str = "discord",
        now: datetime | None = None,
    ) -> ConversationTopicSnapshot | None:
        # Keep this wrapper payload-agnostic at runtime while using the same attributes required by
        # the base service. The concrete connector schema is intentionally not imported here.
        connection_id = str(getattr(payload, "connection_id"))
        guild_id = str(getattr(payload, "guild_id"))
        channel_id = str(getattr(payload, "channel_id"))
        thread_id = str(getattr(payload, "thread_id"))
        message_id = str(getattr(payload, "message_id"))
        text = str(getattr(payload, "text"))
        active = self.repository.active_for_scope(
            owner_id=owner_id,
            platform=platform,
            connection_id=connection_id,
            guild_id=guild_id,
            channel_id=channel_id,
            thread_id=thread_id,
        )
        key = self._cache_key(text=text, active=active) if active is not None else None
        result = super().observe_turn(
            owner_id=owner_id,
            payload=payload,  # type: ignore[arg-type]
            platform=platform,
            now=now,
        )
        decision = self._continuity_cache.get(key) if key is not None else None
        if decision is not None:
            self.repository.decisions.enrich_message_decision(
                owner_id=owner_id,
                message_id=message_id,
                reason=decision.reason,
                dense_score=decision.topic_similarity,
                sparse_score=decision.sparse_similarity,
                continuation_score=decision.acts.continuation,
                switch_score=decision.acts.switch_topic,
            )
        return result


__all__ = ["ObservedConversationTopicMemoryService"]
