"""Super Admin read-only Conversation Burst Runtime observability."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from echo_masque.api.dependencies import AdminUserDependency
from echo_masque.persistence.database import Database
from echo_masque.persistence.deployment_models import (
    DiscordConnectorEventRecord,
    PlatformConnectionRecord,
)

router = APIRouter(
    prefix="/api/admin/runtime/conversation-burst",
    tags=["runtime"],
)


class ConversationBurstEffectiveConfigView(BaseModel):
    model_config = ConfigDict(frozen=True)

    enabled: bool = False
    quiet_window_ms: int = 0
    max_wait_ms: int = 0
    max_messages: int = 0
    max_characters: int = 0


class ConversationBurstConnectorView(BaseModel):
    model_config = ConfigDict(frozen=True)

    connection_id: str
    display_name: str
    status: str
    last_seen_at: datetime | None = None
    effective_config: ConversationBurstEffectiveConfigView
    pending_burst_scopes: int = 0
    pending_preflight_scopes: int = 0
    candidate_messages: int = 0
    bypass_messages: int = 0
    burst_count: int = 0
    collected_messages: int = 0
    collapsed_messages: int = 0
    interaction_bypasses: int = 0
    bypass_reasons: dict[str, int] = {}
    last_burst_at: datetime | None = None
    last_burst_id: str = ""
    last_flush_reason: str = ""


class ConversationBurstPersistedView(BaseModel):
    model_config = ConfigDict(frozen=True)

    occurred_at: datetime
    connection_id: str
    guild_id: str
    channel_id: str
    burst_id: str = ""
    flush_reason: str = ""
    message_count: int = 0
    author_count: int = 0
    collapsed_message_count: int = 0
    collection_latency_ms: int = 0


class ConversationBurstObservationView(BaseModel):
    model_config = ConfigDict(frozen=True)

    connectors: tuple[ConversationBurstConnectorView, ...] = ()
    bursts_24h: int = 0
    collected_messages_24h: int = 0
    collapsed_messages_24h: int = 0
    last_persisted_burst: ConversationBurstPersistedView | None = None
    observation_source: str = "connector_heartbeat_and_persisted_events"


def _database(request: Request) -> Database:
    return cast(Database, request.app.state.database)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _metadata(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _details(raw: str) -> dict[str, Any]:
    return _metadata(raw)


def _int(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return max(0, value)
    if isinstance(value, float):
        return max(0, int(value))
    return 0


def _bool(value: object) -> bool:
    return value if isinstance(value, bool) else False


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return _aware(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        return None


def _reason_counts(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, int] = {}
    for key, raw in value.items():
        name = str(key).strip()[:80]
        if name:
            result[name] = _int(raw)
    return result


def _connector_view(record: PlatformConnectionRecord) -> ConversationBurstConnectorView:
    meta = _metadata(record.metadata_json)
    return ConversationBurstConnectorView(
        connection_id=record.id,
        display_name=record.display_name,
        status=record.status,
        last_seen_at=_aware(record.last_seen_at),
        effective_config=ConversationBurstEffectiveConfigView(
            enabled=_bool(meta.get("turn_collector_enabled")),
            quiet_window_ms=_int(meta.get("turn_collector_quiet_window_ms")),
            max_wait_ms=_int(meta.get("turn_collector_max_wait_ms")),
            max_messages=_int(meta.get("turn_collector_max_messages")),
            max_characters=_int(meta.get("turn_collector_max_characters")),
        ),
        pending_burst_scopes=_int(meta.get("turn_collector_pending_burst_scope_count")),
        pending_preflight_scopes=_int(meta.get("turn_collector_pending_preflight_scope_count")),
        candidate_messages=_int(meta.get("turn_collector_candidate_messages")),
        bypass_messages=_int(meta.get("turn_collector_bypass_messages")),
        burst_count=_int(meta.get("turn_collector_bursts")),
        collected_messages=_int(meta.get("turn_collector_collected_messages")),
        collapsed_messages=_int(meta.get("turn_collector_collapsed_messages")),
        interaction_bypasses=_int(meta.get("turn_collector_interaction_bypasses")),
        bypass_reasons=_reason_counts(meta.get("turn_collector_bypass_reasons")),
        last_burst_at=_datetime(meta.get("turn_collector_last_burst_at")),
        last_burst_id=_text(meta.get("turn_collector_last_burst_id")),
        last_flush_reason=_text(meta.get("turn_collector_last_flush_reason")),
    )


def _persisted_view(record: DiscordConnectorEventRecord) -> ConversationBurstPersistedView:
    details = _details(record.details_json)
    return ConversationBurstPersistedView(
        occurred_at=_aware(record.occurred_at) or record.occurred_at,
        connection_id=record.connection_id,
        guild_id=record.guild_id,
        channel_id=record.channel_id,
        burst_id=_text(details.get("burst_id")),
        flush_reason=_text(details.get("flush_reason")),
        message_count=_int(details.get("message_count")),
        author_count=_int(details.get("author_count")),
        collapsed_message_count=_int(details.get("collapsed_message_count")),
        collection_latency_ms=_int(details.get("collection_latency_ms")),
    )


@router.get("/snapshot", response_model=ConversationBurstObservationView)
def conversation_burst_snapshot(
    request: Request,
    admin: AdminUserDependency,
) -> ConversationBurstObservationView:
    del admin
    database = _database(request)
    since = datetime.now(UTC) - timedelta(hours=24)
    with database.session() as session:
        connections = list(
            session.scalars(
                select(PlatformConnectionRecord)
                .where(PlatformConnectionRecord.platform == "discord")
                .order_by(PlatformConnectionRecord.last_seen_at.desc())
            )
        )
        events = list(
            session.scalars(
                select(DiscordConnectorEventRecord)
                .where(
                    DiscordConnectorEventRecord.event_type == "smart_participation_burst_flushed",
                    DiscordConnectorEventRecord.occurred_at >= since,
                )
                .order_by(DiscordConnectorEventRecord.occurred_at.desc())
            )
        )

    persisted = [_persisted_view(record) for record in events]
    return ConversationBurstObservationView(
        connectors=tuple(_connector_view(record) for record in connections),
        bursts_24h=len(persisted),
        collected_messages_24h=sum(item.message_count for item in persisted),
        collapsed_messages_24h=sum(item.collapsed_message_count for item in persisted),
        last_persisted_burst=persisted[0] if persisted else None,
    )


__all__ = ["router"]
