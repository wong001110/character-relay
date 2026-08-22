"""Super Admin API schemas for temporary Discord debug capture."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from echo_masque.discord_debug_capture import (
    ALLOWED_TTL_MINUTES,
    MAX_BYTES_GLOBAL,
    MAX_BYTES_PER_SESSION,
    MAX_RECORDS_GLOBAL,
    MAX_RECORDS_PER_SESSION,
    MAX_SESSIONS_GLOBAL,
    DiscordDebugCaptureOutcome,
    DiscordDebugCaptureRecord,
    DiscordDebugCaptureSession,
    DiscordDebugCaptureSessionStatus,
)


class DiscordDebugCaptureAccessView(BaseModel):
    available: Literal[True] = True
    storage: Literal["process_memory"] = "process_memory"
    allowed_ttl_minutes: tuple[int, ...] = ALLOWED_TTL_MINUTES
    maximum_records_per_session: int = MAX_RECORDS_PER_SESSION
    maximum_bytes_per_session: int = MAX_BYTES_PER_SESSION
    global_maximum_records: int = MAX_RECORDS_GLOBAL
    global_maximum_bytes: int = MAX_BYTES_GLOBAL
    maximum_session_summaries: int = MAX_SESSIONS_GLOBAL
    restart_clears_captures: Literal[True] = True


class DiscordDebugCaptureSessionCreate(BaseModel):
    server_profile_id: str = Field(min_length=1, max_length=64)
    ttl_minutes: Literal[15, 60, 1440]


class DiscordDebugCaptureSessionView(BaseModel):
    id: str
    server_profile_id: str
    connection_id: str
    guild_id: str
    guild_name: str
    status: DiscordDebugCaptureSessionStatus
    started_at: datetime
    expires_at: datetime
    stopped_at: datetime | None
    record_count: int
    evicted_record_count: int
    captured_bytes: int

    @classmethod
    def from_capture(
        cls,
        session: DiscordDebugCaptureSession,
        *,
        now: datetime,
    ) -> "DiscordDebugCaptureSessionView":
        return cls(
            id=session.id,
            server_profile_id=session.server_profile_id,
            connection_id=session.connection_id,
            guild_id=session.guild_id,
            guild_name=session.guild_name,
            status=session.status_at(now),
            started_at=session.started_at,
            expires_at=session.expires_at,
            stopped_at=session.stopped_at,
            record_count=session.record_count,
            evicted_record_count=session.evicted_record_count,
            captured_bytes=session.captured_bytes,
        )


class DiscordDebugCaptureRecordSummary(BaseModel):
    id: str
    session_id: str
    captured_at: datetime
    source_message_id: str
    channel_id: str
    thread_id: str
    deployment_id: str
    character_count: int
    payload_bytes: int
    outcome: DiscordDebugCaptureOutcome

    @classmethod
    def from_capture(
        cls,
        record: DiscordDebugCaptureRecord,
    ) -> "DiscordDebugCaptureRecordSummary":
        return cls(
            id=record.id,
            session_id=record.session_id,
            captured_at=record.captured_at,
            source_message_id=record.source_message_id,
            channel_id=record.channel_id,
            thread_id=record.thread_id,
            deployment_id=record.deployment_id,
            character_count=record.character_count,
            payload_bytes=record.payload_bytes,
            outcome=record.outcome,
        )


class DiscordDebugCaptureRecordPage(BaseModel):
    items: list[DiscordDebugCaptureRecordSummary]
    page: int
    page_size: int
    total: int
    pages: int


class DiscordDebugCaptureRecordDetail(DiscordDebugCaptureRecordSummary):
    payload: dict[str, object]


class DiscordDebugCaptureClearResult(BaseModel):
    deleted_count: int


__all__ = [
    "DiscordDebugCaptureAccessView",
    "DiscordDebugCaptureClearResult",
    "DiscordDebugCaptureRecordDetail",
    "DiscordDebugCaptureRecordPage",
    "DiscordDebugCaptureRecordSummary",
    "DiscordDebugCaptureSessionCreate",
    "DiscordDebugCaptureSessionView",
]
