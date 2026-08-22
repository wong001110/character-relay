"""Bounded, process-local Discord runtime-ingress debug capture.

Option B deliberately keeps raw payloads out of SQLite, WAL files, backups, exports,
and ordinary connector events.  The protocols in this module are the extension seam
for a future separately encrypted Option C archive.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from threading import RLock
from typing import Literal, Protocol
from uuid import uuid4

from echo_masque.persistence.models import utcnow

DiscordDebugCaptureOutcome = Literal[
    "pending",
    "succeeded",
    "conflict",
    "provider_error",
]
DiscordDebugCaptureSessionStatus = Literal["active", "expired", "stopped"]

ALLOWED_TTL_MINUTES = (15, 60, 1440)
MAX_RECORDS_PER_SESSION = 100
MAX_BYTES_PER_SESSION = 10 * 1024 * 1024
MAX_RECORDS_GLOBAL = 500
MAX_BYTES_GLOBAL = 50 * 1024 * 1024
MAX_SESSIONS_GLOBAL = 500


class DiscordDebugCaptureConflict(RuntimeError):
    """Raised when a server already has an active capture session."""


class CapturePayloadCodec(Protocol):
    """Serialize validated ingress payloads independently of storage."""

    def encode(self, payload: Mapping[str, object]) -> bytes: ...

    def decode(self, payload: bytes) -> dict[str, object]: ...


class JsonCapturePayloadCodec:
    """Deterministic UTF-8 JSON codec used by the in-memory Option B store."""

    def encode(self, payload: Mapping[str, object]) -> bytes:
        return json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

    def decode(self, payload: bytes) -> dict[str, object]:
        decoded = json.loads(payload.decode("utf-8"))
        if not isinstance(decoded, dict):
            raise ValueError("Discord debug capture payload must decode to an object.")
        return decoded


@dataclass(frozen=True, slots=True)
class DiscordDebugCaptureSession:
    id: str
    owner_id: str
    server_profile_id: str
    connection_id: str
    guild_id: str
    guild_name: str
    started_at: datetime
    expires_at: datetime
    stopped_at: datetime | None = None
    record_count: int = 0
    evicted_record_count: int = 0
    captured_bytes: int = 0

    def status_at(self, now: datetime) -> DiscordDebugCaptureSessionStatus:
        if self.stopped_at is not None:
            return "stopped"
        if self.expires_at <= now:
            return "expired"
        return "active"


@dataclass(frozen=True, slots=True)
class DiscordDebugCaptureRecord:
    id: str
    session_id: str
    connection_id: str
    guild_id: str
    captured_at: datetime
    source_message_id: str
    channel_id: str
    thread_id: str
    deployment_id: str
    character_count: int
    payload_bytes: int
    outcome: DiscordDebugCaptureOutcome
    encoded_payload: bytes
    dedupe_key: tuple[str, ...]


class DiscordDebugCaptureStore(Protocol):
    """Storage boundary shared by process-memory Option B and future Option C."""

    codec: CapturePayloadCodec

    def start_session(
        self,
        *,
        owner_id: str,
        server_profile_id: str,
        connection_id: str,
        guild_id: str,
        guild_name: str,
        ttl_minutes: int,
    ) -> DiscordDebugCaptureSession: ...

    def current_session(
        self,
        *,
        owner_id: str,
        server_profile_id: str,
    ) -> DiscordDebugCaptureSession | None: ...

    def get_session(
        self,
        session_id: str,
        *,
        owner_id: str,
    ) -> DiscordDebugCaptureSession | None: ...

    def stop_session(
        self,
        session_id: str,
        *,
        owner_id: str,
    ) -> DiscordDebugCaptureSession | None: ...

    def discard_session(self, session_id: str, *, owner_id: str) -> bool: ...

    def capture(
        self,
        *,
        connection_id: str,
        guild_id: str,
        source_message_id: str,
        channel_id: str,
        thread_id: str,
        deployment_id: str,
        runtime_operation_id: str,
        runtime_step_id: str,
        character_count: int,
        payload: Mapping[str, object],
    ) -> DiscordDebugCaptureRecord | None: ...

    def mark_outcome(
        self,
        record_id: str,
        outcome: DiscordDebugCaptureOutcome,
    ) -> None: ...

    def list_records(
        self,
        session_id: str,
        *,
        owner_id: str,
        page: int,
        page_size: int,
    ) -> tuple[list[DiscordDebugCaptureRecord], int]: ...

    def get_record(
        self,
        record_id: str,
        *,
        owner_id: str,
    ) -> DiscordDebugCaptureRecord | None: ...

    def clear_records(self, session_id: str, *, owner_id: str) -> int | None: ...


class InMemoryDiscordDebugCaptureStore:
    """Thread-safe bounded capture store; all payloads disappear on process restart."""

    def __init__(
        self,
        *,
        codec: CapturePayloadCodec | None = None,
        now: Callable[[], datetime] = utcnow,
        maximum_records: int = MAX_RECORDS_PER_SESSION,
        maximum_bytes: int = MAX_BYTES_PER_SESSION,
        global_maximum_records: int = MAX_RECORDS_GLOBAL,
        global_maximum_bytes: int = MAX_BYTES_GLOBAL,
        maximum_sessions: int = MAX_SESSIONS_GLOBAL,
    ) -> None:
        if (
            maximum_records < 1
            or maximum_bytes < 1
            or global_maximum_records < 1
            or global_maximum_bytes < 1
            or maximum_sessions < 1
        ):
            raise ValueError("Discord debug capture capacity must be positive.")
        self.codec = codec or JsonCapturePayloadCodec()
        self._now = now
        self._maximum_records = maximum_records
        self._maximum_bytes = maximum_bytes
        self._global_maximum_records = global_maximum_records
        self._global_maximum_bytes = global_maximum_bytes
        self._maximum_sessions = maximum_sessions
        self._sessions: dict[str, DiscordDebugCaptureSession] = {}
        self._records: dict[str, DiscordDebugCaptureRecord] = {}
        self._global_record_ids: list[str] = []
        self._record_ids: dict[str, list[str]] = {}
        self._dedupe_ids: dict[tuple[str, ...], str] = {}
        self._active_scopes: dict[tuple[str, str], str] = {}
        self._lock = RLock()

    def start_session(
        self,
        *,
        owner_id: str,
        server_profile_id: str,
        connection_id: str,
        guild_id: str,
        guild_name: str,
        ttl_minutes: int,
    ) -> DiscordDebugCaptureSession:
        if ttl_minutes not in ALLOWED_TTL_MINUTES:
            raise ValueError("Discord debug capture TTL must be 15, 60, or 1440 minutes.")
        with self._lock:
            now = self._now()
            self._prune_expired_locked(now)
            scope = (connection_id, guild_id)
            active_id = self._active_scopes.get(scope)
            if active_id is not None:
                active = self._sessions.get(active_id)
                if active is not None and active.status_at(now) == "active":
                    raise DiscordDebugCaptureConflict(
                        "This Discord Server already has an active debug capture session."
                    )
            previous_session_ids: list[str] = []
            for previous in self._sessions.values():
                if (
                    previous.connection_id == connection_id
                    and previous.guild_id == guild_id
                ):
                    self._clear_session_records_locked(previous.id)
                    previous_session_ids.append(previous.id)
            for previous_session_id in previous_session_ids:
                self._record_ids.pop(previous_session_id, None)
                self._sessions.pop(previous_session_id, None)
            self._make_session_slot_locked(now)
            session = DiscordDebugCaptureSession(
                id=str(uuid4()),
                owner_id=owner_id,
                server_profile_id=server_profile_id,
                connection_id=connection_id,
                guild_id=guild_id,
                guild_name=guild_name,
                started_at=now,
                expires_at=now + timedelta(minutes=ttl_minutes),
            )
            self._sessions[session.id] = session
            self._record_ids[session.id] = []
            self._active_scopes[scope] = session.id
            return session

    def current_session(
        self,
        *,
        owner_id: str,
        server_profile_id: str,
    ) -> DiscordDebugCaptureSession | None:
        with self._lock:
            now = self._now()
            self._prune_expired_locked(now)
            for session in reversed(self._sessions.values()):
                if (
                    session.owner_id == owner_id
                    and session.server_profile_id == server_profile_id
                ):
                    return session
            return None

    def get_session(
        self,
        session_id: str,
        *,
        owner_id: str,
    ) -> DiscordDebugCaptureSession | None:
        with self._lock:
            now = self._now()
            self._prune_expired_locked(now)
            session = self._sessions.get(session_id)
            if session is None or session.owner_id != owner_id:
                return None
            return session

    def stop_session(
        self,
        session_id: str,
        *,
        owner_id: str,
    ) -> DiscordDebugCaptureSession | None:
        with self._lock:
            now = self._now()
            self._prune_expired_locked(now)
            session = self._sessions.get(session_id)
            if session is None or session.owner_id != owner_id:
                return None
            if session.stopped_at is None and session.expires_at > now:
                session = replace(session, stopped_at=now)
                self._sessions[session_id] = session
            self._release_scope_locked(session)
            return session

    def discard_session(self, session_id: str, *, owner_id: str) -> bool:
        """Remove a session when its required control-plane audit could not be recorded."""

        with self._lock:
            session = self._sessions.get(session_id)
            if session is None or session.owner_id != owner_id:
                return False
            self._release_scope_locked(session)
            self._clear_session_records_locked(session_id)
            self._record_ids.pop(session_id, None)
            self._sessions.pop(session_id, None)
            return True

    def capture(
        self,
        *,
        connection_id: str,
        guild_id: str,
        source_message_id: str,
        channel_id: str,
        thread_id: str,
        deployment_id: str,
        runtime_operation_id: str,
        runtime_step_id: str,
        character_count: int,
        payload: Mapping[str, object],
    ) -> DiscordDebugCaptureRecord | None:
        with self._lock:
            now = self._now()
            self._prune_expired_locked(now)
            session_id = self._active_scopes.get((connection_id, guild_id))
            if session_id is None:
                return None
            session = self._sessions.get(session_id)
            if session is None or session.status_at(now) != "active":
                return None
            dedupe_key = (
                session_id,
                connection_id,
                guild_id,
                source_message_id,
                deployment_id,
                runtime_operation_id,
                runtime_step_id,
            )
            existing_id = self._dedupe_ids.get(dedupe_key)
            if existing_id is not None:
                return self._records.get(existing_id)
            encoded = self.codec.encode(payload)
            record = DiscordDebugCaptureRecord(
                id=str(uuid4()),
                session_id=session_id,
                connection_id=connection_id,
                guild_id=guild_id,
                captured_at=now,
                source_message_id=source_message_id,
                channel_id=channel_id,
                thread_id=thread_id,
                deployment_id=deployment_id,
                character_count=max(0, character_count),
                payload_bytes=len(encoded),
                outcome="pending",
                encoded_payload=encoded,
                dedupe_key=dedupe_key,
            )
            self._records[record.id] = record
            self._global_record_ids.append(record.id)
            self._record_ids[session_id].append(record.id)
            self._dedupe_ids[dedupe_key] = record.id
            self._refresh_session_usage_locked(session_id)
            self._enforce_capacity_locked(session_id)
            self._enforce_global_capacity_locked()
            return self._records.get(record.id)

    def mark_outcome(
        self,
        record_id: str,
        outcome: DiscordDebugCaptureOutcome,
    ) -> None:
        with self._lock:
            self._prune_expired_locked(self._now())
            record = self._records.get(record_id)
            if record is not None:
                self._records[record_id] = replace(record, outcome=outcome)

    def list_records(
        self,
        session_id: str,
        *,
        owner_id: str,
        page: int,
        page_size: int,
    ) -> tuple[list[DiscordDebugCaptureRecord], int]:
        with self._lock:
            self._prune_expired_locked(self._now())
            session = self._sessions.get(session_id)
            if session is None or session.owner_id != owner_id:
                raise KeyError("session")
            ids = list(reversed(self._record_ids.get(session_id, [])))
            total = len(ids)
            pages = max(1, (total + page_size - 1) // page_size)
            safe_page = min(max(1, page), pages)
            start = (safe_page - 1) * page_size
            selected = ids[start : start + page_size]
            return [self._records[item] for item in selected if item in self._records], total

    def get_record(
        self,
        record_id: str,
        *,
        owner_id: str,
    ) -> DiscordDebugCaptureRecord | None:
        with self._lock:
            self._prune_expired_locked(self._now())
            record = self._records.get(record_id)
            if record is None:
                return None
            session = self._sessions.get(record.session_id)
            if session is None or session.owner_id != owner_id:
                return None
            return record

    def clear_records(self, session_id: str, *, owner_id: str) -> int | None:
        with self._lock:
            self._prune_expired_locked(self._now())
            session = self._sessions.get(session_id)
            if session is None or session.owner_id != owner_id:
                return None
            record_ids = list(self._record_ids.get(session_id, []))
            self._clear_session_records_locked(session_id)
            return len(record_ids)

    def decode_record(self, record: DiscordDebugCaptureRecord) -> dict[str, object]:
        return self.codec.decode(record.encoded_payload)

    def _prune_expired_locked(self, now: datetime) -> None:
        for session_id, session in list(self._sessions.items()):
            if session.expires_at <= now:
                self._release_scope_locked(session)
                for record_id in list(self._record_ids.get(session_id, [])):
                    self._remove_record_locked(record_id)
                self._record_ids[session_id] = []
                self._refresh_session_usage_locked(session_id)

    def _enforce_capacity_locked(self, session_id: str) -> None:
        session = self._sessions[session_id]
        record_ids = self._record_ids[session_id]
        evicted = 0
        while record_ids and (
            len(record_ids) > self._maximum_records
            or session.captured_bytes > self._maximum_bytes
        ):
            self._remove_record_locked(record_ids[0])
            evicted += 1
            session = self._refresh_session_usage_locked(session_id)
            record_ids = self._record_ids[session_id]
        if evicted:
            self._sessions[session_id] = replace(
                self._sessions[session_id],
                evicted_record_count=(
                    self._sessions[session_id].evicted_record_count + evicted
                ),
            )

    def _enforce_global_capacity_locked(self) -> None:
        while self._global_record_ids and (
            len(self._global_record_ids) > self._global_maximum_records
            or sum(item.payload_bytes for item in self._records.values())
            > self._global_maximum_bytes
        ):
            record = self._remove_record_locked(self._global_record_ids[0])
            if record is None:
                continue
            self._refresh_session_usage_locked(record.session_id)
            session = self._sessions[record.session_id]
            self._sessions[record.session_id] = replace(
                session,
                evicted_record_count=session.evicted_record_count + 1,
            )

    def _remove_record_locked(
        self,
        record_id: str,
    ) -> DiscordDebugCaptureRecord | None:
        record = self._records.pop(record_id, None)
        if record is None:
            if record_id in self._global_record_ids:
                self._global_record_ids.remove(record_id)
            return None
        ids = self._record_ids.get(record.session_id)
        if ids is not None and record_id in ids:
            ids.remove(record_id)
        if record_id in self._global_record_ids:
            self._global_record_ids.remove(record_id)
        self._dedupe_ids.pop(record.dedupe_key, None)
        return record

    def _clear_session_records_locked(self, session_id: str) -> None:
        for record_id in list(self._record_ids.get(session_id, [])):
            self._remove_record_locked(record_id)
        self._record_ids[session_id] = []
        self._refresh_session_usage_locked(session_id)

    def _release_scope_locked(self, session: DiscordDebugCaptureSession) -> None:
        scope = (session.connection_id, session.guild_id)
        if self._active_scopes.get(scope) == session.id:
            self._active_scopes.pop(scope, None)

    def _make_session_slot_locked(self, now: datetime) -> None:
        for session_id, session in list(self._sessions.items()):
            if len(self._sessions) < self._maximum_sessions:
                return
            if session.status_at(now) != "expired":
                continue
            self._record_ids.pop(session_id, None)
            self._sessions.pop(session_id, None)
        if len(self._sessions) >= self._maximum_sessions:
            raise DiscordDebugCaptureConflict(
                "The process-wide Discord debug capture session limit is reached."
            )

    def _refresh_session_usage_locked(self, session_id: str) -> DiscordDebugCaptureSession:
        session = self._sessions[session_id]
        records = [
            self._records[record_id]
            for record_id in self._record_ids.get(session_id, [])
            if record_id in self._records
        ]
        updated = replace(
            session,
            record_count=len(records),
            captured_bytes=sum(item.payload_bytes for item in records),
        )
        self._sessions[session_id] = updated
        return updated


__all__ = [
    "ALLOWED_TTL_MINUTES",
    "MAX_BYTES_GLOBAL",
    "MAX_BYTES_PER_SESSION",
    "MAX_RECORDS_GLOBAL",
    "MAX_RECORDS_PER_SESSION",
    "MAX_SESSIONS_GLOBAL",
    "CapturePayloadCodec",
    "DiscordDebugCaptureConflict",
    "DiscordDebugCaptureOutcome",
    "DiscordDebugCaptureRecord",
    "DiscordDebugCaptureSession",
    "DiscordDebugCaptureSessionStatus",
    "DiscordDebugCaptureStore",
    "InMemoryDiscordDebugCaptureStore",
    "JsonCapturePayloadCodec",
]
