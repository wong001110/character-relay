"""Short-lived process-local semantic signals shared by one Discord turn."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from threading import Lock
from time import monotonic
from typing import ClassVar


@dataclass(frozen=True, slots=True)
class SemanticTurnSignals:
    deployment_id: str
    message_id: str
    topic_id: str = ""
    topic_label: str = ""
    topic_summary: str = ""
    topic_message_count: int = 0
    continuation_tool_ids: tuple[str, ...] = ()
    detected_side_effect_intents: tuple[str, ...] = ()
    blocked_side_effect_intents: tuple[str, ...] = ()
    continuity_reason: str = ""
    retry_score: float = 0.0


class SemanticTurnSignalStore:
    """Bounded TTL store; raw Discord message text and Tool arguments are never retained."""

    _entries: ClassVar[
        OrderedDict[tuple[str, str], tuple[float, SemanticTurnSignals]]
    ] = OrderedDict()
    _lock: ClassVar[Lock] = Lock()
    _ttl_seconds: ClassVar[float] = 180.0
    _max_entries: ClassVar[int] = 512

    @classmethod
    def put(cls, signals: SemanticTurnSignals) -> None:
        key = (signals.deployment_id, signals.message_id)
        now = monotonic()
        with cls._lock:
            cls._purge_locked(now)
            cls._entries[key] = (now + cls._ttl_seconds, signals)
            cls._entries.move_to_end(key)
            while len(cls._entries) > cls._max_entries:
                cls._entries.popitem(last=False)

    @classmethod
    def get(cls, deployment_id: str, message_id: str) -> SemanticTurnSignals | None:
        key = (deployment_id, message_id)
        now = monotonic()
        with cls._lock:
            cached = cls._entries.get(key)
            if cached is None:
                return None
            expires_at, signals = cached
            if expires_at <= now:
                cls._entries.pop(key, None)
                return None
            cls._entries.move_to_end(key)
            return signals

    @classmethod
    def topic_capsule(cls, topic_id: str) -> tuple[str, str, int] | None:
        """Return the newest bounded prompt-safe capsule for a topic id."""

        if not topic_id:
            return None
        now = monotonic()
        with cls._lock:
            cls._purge_locked(now)
            for _, signals in reversed(cls._entries.values()):
                if signals.topic_id == topic_id:
                    return (
                        signals.topic_label[:240],
                        signals.topic_summary[:800],
                        max(0, signals.topic_message_count),
                    )
        return None

    @classmethod
    def _purge_locked(cls, now: float) -> None:
        expired = [key for key, (expires_at, _) in cls._entries.items() if expires_at <= now]
        for key in expired:
            cls._entries.pop(key, None)

    @classmethod
    def reset_for_test(cls) -> None:
        with cls._lock:
            cls._entries.clear()


__all__ = ["SemanticTurnSignalStore", "SemanticTurnSignals"]
