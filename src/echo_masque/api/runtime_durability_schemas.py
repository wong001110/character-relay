"""HTTP schemas for Phase 5 durable Runtime operations and trace inspection."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from echo_masque.api.social_turn_schemas import (
    DiscordSocialPendingTurn,
    DiscordSocialTurnCursor,
)
from echo_masque.persistence.runtime_durability_models import (
    RuntimeOperationRecord,
    RuntimeTraceEventRecord,
    RuntimeTraceRunRecord,
)

RuntimeOperationStatus = Literal[
    "active",
    "awaiting_delivery",
    "completed",
    "uncertain",
    "failed",
]
RuntimeDeliveryClaimStatus = Literal["granted", "already_delivered", "uncertain"]
RuntimeTraceRunStatus = Literal["running", "completed", "failed"]


def _json_object(value: str) -> dict[str, object]:
    try:
        decoded = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}
    return cast(dict[str, object], decoded) if isinstance(decoded, dict) else {}


def _json_list(value: str) -> list[object]:
    try:
        decoded = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []
    return decoded if isinstance(decoded, list) else []


class DiscordSocialOperationSource(BaseModel):
    deployment_id: str = Field(min_length=1, max_length=64)
    text: str = Field(default="", max_length=10000)
    sent_message_ids: list[str] = Field(default_factory=list, max_length=20)


class DiscordSocialOperationClaimRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connection_id: str = Field(min_length=1, max_length=64)
    operation_id: str = Field(min_length=32, max_length=64)
    guild_id: str = Field(min_length=1, max_length=200)
    channel_id: str = Field(min_length=1, max_length=200)
    thread_id: str = Field(default="", max_length=200)
    source_message_id: str = Field(min_length=1, max_length=200)
    initial_deployment_ids: list[str] = Field(min_length=1, max_length=10)
    available_deployment_ids: list[str] = Field(min_length=1, max_length=30)
    continuation_budget: int = Field(default=4, ge=0, le=20)
    max_depth: int = Field(default=2, ge=0, le=8)


class DiscordSocialOperationView(BaseModel):
    operation_id: str
    status: RuntimeOperationStatus
    cursor: DiscordSocialTurnCursor
    next_turn: DiscordSocialPendingTurn | None = None
    sources: list[DiscordSocialOperationSource] = Field(default_factory=list)
    resume_count: int = 0
    last_error: str = ""

    @classmethod
    def from_record(cls, record: RuntimeOperationRecord) -> DiscordSocialOperationView:
        cursor = DiscordSocialTurnCursor.model_validate(_json_object(record.cursor_json))
        sources = [
            DiscordSocialOperationSource.model_validate(item)
            for item in _json_list(record.sources_json)
            if isinstance(item, dict)
        ]
        return cls(
            operation_id=record.operation_id,
            status=cast(RuntimeOperationStatus, record.status),
            cursor=cursor,
            next_turn=cursor.pending_turns[0] if cursor.pending_turns else None,
            sources=sources,
            resume_count=record.resume_count,
            last_error=record.last_error,
        )


class DiscordPendingSocialOperation(BaseModel):
    operation_id: str
    status: RuntimeOperationStatus
    guild_id: str
    channel_id: str
    thread_id: str
    source_message_id: str
    updated_at: datetime

    @classmethod
    def from_record(cls, record: RuntimeOperationRecord) -> DiscordPendingSocialOperation:
        return cls(
            operation_id=record.operation_id,
            status=cast(RuntimeOperationStatus, record.status),
            guild_id=record.guild_id,
            channel_id=record.channel_id,
            thread_id=record.thread_id,
            source_message_id=record.source_message_id,
            updated_at=record.updated_at,
        )


class DiscordDeliveryClaimRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connection_id: str = Field(min_length=1, max_length=64)
    operation_id: str = Field(min_length=32, max_length=64)
    step_id: str = Field(min_length=32, max_length=64)
    claim_nonce: str = Field(min_length=16, max_length=64)


class DiscordDeliveryClaimView(BaseModel):
    claim_status: RuntimeDeliveryClaimStatus
    operation_status: RuntimeOperationStatus
    operation_id: str
    step_id: str


class DiscordDeliveryAckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connection_id: str = Field(min_length=1, max_length=64)
    operation_id: str = Field(min_length=32, max_length=64)
    step_id: str = Field(min_length=32, max_length=64)
    claim_nonce: str = Field(min_length=16, max_length=64)
    deployment_id: str = Field(min_length=1, max_length=64)
    cursor: DiscordSocialTurnCursor
    sent_message_ids: list[str] = Field(default_factory=list, max_length=20)
    outgoing_text: str = Field(default="", max_length=10000)
    applied: bool = False


class DiscordDeliveryFailureRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connection_id: str = Field(min_length=1, max_length=64)
    operation_id: str = Field(min_length=32, max_length=64)
    step_id: str = Field(min_length=32, max_length=64)
    claim_nonce: str = Field(min_length=16, max_length=64)
    error: str = Field(default="delivery_failed_or_uncertain", max_length=1000)


class DiscordCharacterDeliveryAckRequest(BaseModel):
    """Connector acknowledgement for an ordinary Character turn.

    Cursor and deployment are intentionally omitted: Runtime reloads both from the claimed step.
    """

    model_config = ConfigDict(extra="forbid")

    connection_id: str = Field(min_length=1, max_length=64)
    operation_id: str = Field(min_length=32, max_length=64)
    step_id: str = Field(min_length=32, max_length=64)
    claim_nonce: str = Field(min_length=16, max_length=64)
    sent_message_ids: list[str] = Field(default_factory=list, max_length=20)


class RuntimeTraceEventView(BaseModel):
    id: int
    node_name: str
    node_kind: str
    status: str
    changed_keys: list[str]
    metadata: list[tuple[str, str]]
    error: str
    created_at: datetime

    @classmethod
    def from_record(cls, record: RuntimeTraceEventRecord) -> RuntimeTraceEventView:
        changed = [str(item) for item in _json_list(record.changed_keys_json)]
        metadata: list[tuple[str, str]] = []
        for item in _json_list(record.metadata_json):
            if isinstance(item, list) and len(item) == 2:
                metadata.append((str(item[0]), str(item[1])))
        return cls(
            id=record.id,
            node_name=record.node_name,
            node_kind=record.node_kind,
            status=record.status,
            changed_keys=changed,
            metadata=metadata,
            error=record.error,
            created_at=record.created_at,
        )


class RuntimeTraceSummary(BaseModel):
    graph_run_id: str
    trace_id: str
    operation_id: str
    graph_name: str
    status: RuntimeTraceRunStatus
    owner_id: str
    deployment_id: str
    character_card_id: str
    last_node: str
    event_count: int
    error: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_record(cls, record: RuntimeTraceRunRecord) -> RuntimeTraceSummary:
        return cls(
            graph_run_id=record.graph_run_id,
            trace_id=record.trace_id,
            operation_id=record.operation_id,
            graph_name=record.graph_name,
            status=cast(RuntimeTraceRunStatus, record.status),
            owner_id=record.owner_id,
            deployment_id=record.deployment_id,
            character_card_id=record.character_card_id,
            last_node=record.last_node,
            event_count=record.event_count,
            error=record.error,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )


class RuntimeTraceView(RuntimeTraceSummary):
    events: list[RuntimeTraceEventView]


class RuntimeTracePage(BaseModel):
    items: list[RuntimeTraceSummary]
    next_cursor: str | None
    has_more: bool


class RuntimeTraceAccessView(BaseModel):
    allowed: bool = True


class RuntimeTraceClearResult(BaseModel):
    deleted_count: int
