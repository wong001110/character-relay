"""Deterministic lifecycle policy for persisted conversation Topics."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from echo_masque.persistence.conversation_topic_models import ConversationTopicRecord

ACTIVE_TO_COOLING = timedelta(hours=6)
COOLING_TO_CLOSED = timedelta(days=3)
CLOSED_TO_ARCHIVED = timedelta(days=30)
_TERMINAL_PENDING_STATES = {"completed", "cancelled", "expired", "failed"}


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _has_live_pending_action(record: ConversationTopicRecord, now: datetime) -> bool:
    try:
        values = json.loads(record.pending_actions_json or "[]")
    except (json.JSONDecodeError, TypeError):
        return False
    if not isinstance(values, list):
        return False
    for item in values:
        if not isinstance(item, dict):
            continue
        state = str(item.get("state", ""))
        if state in _TERMINAL_PENDING_STATES:
            continue
        raw_expiry = item.get("expires_at")
        if not isinstance(raw_expiry, str) or not raw_expiry:
            return True
        try:
            expiry = datetime.fromisoformat(raw_expiry.replace("Z", "+00:00"))
        except ValueError:
            return True
        if _aware(expiry) > now:
            return True
    return False


@dataclass(frozen=True, slots=True)
class TopicLifecycleDecision:
    from_status: str
    to_status: str
    reason: str



def evaluate_topic_lifecycle(
    record: ConversationTopicRecord,
    *,
    now: datetime | None = None,
) -> TopicLifecycleDecision | None:
    current = _aware(now) if now is not None else datetime.now(UTC)
    if record.status == "active":
        if _has_live_pending_action(record, current):
            return None
        if current - _aware(record.last_active_at) >= ACTIVE_TO_COOLING:
            return TopicLifecycleDecision("active", "cooling", "active_idle_timeout")
        return None
    if record.status == "cooling":
        if current - _aware(record.updated_at) >= COOLING_TO_CLOSED:
            return TopicLifecycleDecision("cooling", "closed", "cooling_retention_elapsed")
        return None
    if record.status == "closed":
        anchor = record.closed_at or record.updated_at
        if current - _aware(anchor) >= CLOSED_TO_ARCHIVED:
            return TopicLifecycleDecision("closed", "archived", "closed_retention_elapsed")
    return None


__all__ = [
    "ACTIVE_TO_COOLING",
    "CLOSED_TO_ARCHIVED",
    "COOLING_TO_CLOSED",
    "TopicLifecycleDecision",
    "evaluate_topic_lifecycle",
]
