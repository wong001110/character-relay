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
    conversation_thread_id: str = ""
    continuation_tool_ids: tuple[str, ...] = ()
    detected_side_effect_intents: tuple[str, ...] = ()
    blocked_side_effect_intents: tuple[str, ...] = ()
    continuity_reason: str = ""
    retry_score: float = 0.0


class SemanticTurnSignalStore:
    """Bounded TTL store; no raw message text is retained."""

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
    def _purge_locked(cls, now: float) -> None:
        expired = [key for key, (expires_at, _) in cls._entries.items() if expires_at <= now]
        for key in expired:
            cls._entries.pop(key, None)

    @classmethod
    def reset_for_test(cls) -> None:
        with cls._lock:
            cls._entries.clear()


__all__ = ["SemanticTurnSignalStore", "SemanticTurnSignals"]
