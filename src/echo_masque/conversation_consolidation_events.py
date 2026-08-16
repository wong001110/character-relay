"""Process-local signals for asynchronous conversation consolidation.

Signals never perform persistence inside SQLAlchemy mapper callbacks. They only enqueue a
bounded topic identifier for the application-owned consolidation service. Periodic maintenance
remains the cross-replica / missed-event safety net.
"""

from __future__ import annotations

from collections.abc import Callable
from threading import Lock

TopicConsolidationSink = Callable[[str, str, str], None]


class ConversationConsolidationEventBus:
    _sink: TopicConsolidationSink | None = None
    _lock = Lock()

    @classmethod
    def configure(cls, sink: TopicConsolidationSink | None) -> None:
        with cls._lock:
            cls._sink = sink

    @classmethod
    def publish(cls, owner_id: str, topic_id: str, reason: str) -> None:
        if not owner_id or not topic_id:
            return
        with cls._lock:
            sink = cls._sink
        if sink is None:
            return
        sink(owner_id, topic_id, reason[:80])


__all__ = ["ConversationConsolidationEventBus", "TopicConsolidationSink"]
