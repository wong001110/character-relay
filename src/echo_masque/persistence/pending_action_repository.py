"""Durable pending tool requests, independent of conversation/memory projections."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast
from uuid import NAMESPACE_URL, uuid4, uuid5

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError

from echo_masque.persistence.database import Database
from echo_masque.persistence.pending_action_models import PendingActionRecord


@dataclass(frozen=True, slots=True)
class PendingActionView:
    id: str
    channel_id: str
    discord_thread_id: str
    source_message_id: str
    requested_by_user_id: str
    target_character_card_id: str
    deployment_id: str
    tool_id: str
    intent_summary: str
    state: str
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PendingActionRepository:
    """Only exact requester/room/character tasks; uncertain effects never auto-resume."""

    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def _aware(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

    @classmethod
    def pending_action_view(cls, record: PendingActionRecord) -> PendingActionView:
        return PendingActionView(
            id=record.id,
            channel_id=record.channel_id,
            discord_thread_id=record.discord_thread_id,
            source_message_id=record.source_message_id,
            requested_by_user_id=record.requested_by_user_id,
            target_character_card_id=record.target_character_card_id,
            deployment_id=record.deployment_id,
            tool_id=record.tool_id,
            intent_summary=record.intent_summary,
            state=record.state,
            expires_at=cls._aware(record.expires_at),
            created_at=cls._aware(record.created_at) or record.created_at,
            updated_at=cls._aware(record.updated_at) or record.updated_at,
        )

    def create_pending_action(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        channel_id: str,
        discord_thread_id: str,
        source_message_id: str,
        requested_by_user_id: str,
        target_character_card_id: str,
        deployment_id: str,
        tool_id: str,
        intent_summary: str,
        state: str = "pending",
        expires_at: datetime | None = None,
        now: datetime | None = None,
        idempotency_key: str = "",
    ) -> PendingActionView:
        current = now or datetime.now(UTC)
        record = PendingActionRecord(
            id=str(uuid5(NAMESPACE_URL, idempotency_key)) if idempotency_key else str(uuid4()),
            owner_id=owner_id,
            connection_id=connection_id,
            guild_id=guild_id,
            channel_id=channel_id,
            discord_thread_id=discord_thread_id,
            source_message_id=source_message_id[:200],
            requested_by_user_id=requested_by_user_id[:200],
            target_character_card_id=target_character_card_id[:64],
            deployment_id=deployment_id[:64],
            tool_id=tool_id[:160],
            intent_summary=" ".join(intent_summary.split())[:2000],
            state=state[:32],
            expires_at=expires_at,
            created_at=current,
            updated_at=current,
        )
        with self.database.session() as session:
            session.add(record)
            try:
                session.commit()
                session.refresh(record)
            except IntegrityError:
                session.rollback()
                if not idempotency_key:
                    raise
                existing = session.get(PendingActionRecord, record.id)
                if existing is None or existing.owner_id != owner_id:
                    raise
                record = existing
        return self.pending_action_view(record)

    def claim_pending_action_for_execution(
        self,
        *,
        owner_id: str,
        action_id: str,
        now: datetime | None = None,
    ) -> PendingActionView | None:
        """Atomically move one pre-execution action into the non-resumable state."""

        current = now or datetime.now(UTC)
        with self.database.session() as session:
            result = session.execute(
                update(PendingActionRecord)
                .where(
                    PendingActionRecord.id == action_id,
                    PendingActionRecord.owner_id == owner_id,
                    PendingActionRecord.state.in_(("pending", "blocked_unavailable")),
                    or_(
                        PendingActionRecord.expires_at.is_(None),
                        PendingActionRecord.expires_at > current,
                    ),
                )
                .values(state="in_progress", updated_at=current)
            )
            if cast(int, getattr(result, "rowcount", 0)) != 1:
                session.rollback()
                return None
            session.commit()
            record = session.get(PendingActionRecord, action_id)
            return self.pending_action_view(record) if record is not None else None

    def active_pending_actions(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        requested_by_user_id: str = "",
        target_character_card_id: str = "",
        deployment_id: str = "",
        channel_id: str = "",
        discord_thread_id: str = "",
        now: datetime | None = None,
        limit: int = 20,
    ) -> tuple[PendingActionView, ...]:
        current = now or datetime.now(UTC)
        with self.database.session() as session:
            statement = select(PendingActionRecord).where(
                PendingActionRecord.owner_id == owner_id,
                PendingActionRecord.connection_id == connection_id,
                PendingActionRecord.guild_id == guild_id,
                PendingActionRecord.state.in_(("pending", "in_progress", "blocked_unavailable")),
            )
            statement = statement.where(
                PendingActionRecord.requested_by_user_id == requested_by_user_id,
                PendingActionRecord.target_character_card_id == target_character_card_id,
                PendingActionRecord.deployment_id == deployment_id,
                PendingActionRecord.channel_id == channel_id,
                PendingActionRecord.discord_thread_id == discord_thread_id,
            )
            records = list(
                session.scalars(
                    statement.order_by(PendingActionRecord.updated_at.desc()).limit(
                        max(1, min(limit, 100))
                    )
                )
            )
            changed = False
            active: list[PendingActionRecord] = []
            for record in records:
                expires = self._aware(record.expires_at)
                if expires is not None and expires <= current:
                    record.state = "expired"
                    record.updated_at = current
                    changed = True
                else:
                    active.append(record)
            if changed:
                session.commit()
        return tuple(self.pending_action_view(record) for record in active)

    def pending_action(self, *, owner_id: str, action_id: str) -> PendingActionView | None:
        with self.database.session() as session:
            record = session.get(PendingActionRecord, action_id)
        if record is None or record.owner_id != owner_id:
            return None
        return self.pending_action_view(record)

    def update_pending_action_state(
        self,
        *,
        owner_id: str,
        action_id: str,
        state: str,
        now: datetime | None = None,
    ) -> PendingActionView | None:
        current = now or datetime.now(UTC)
        allowed = {
            "pending",
            "in_progress",
            "blocked_unavailable",
            "completed",
            "cancelled",
            "expired",
        }
        if state not in allowed:
            raise ValueError("invalid_pending_action_state")
        normalized = state
        with self.database.session() as session:
            record = session.get(PendingActionRecord, action_id)
            if record is None or record.owner_id != owner_id:
                return None
            if record.state in {"completed", "cancelled", "expired"} and state != record.state:
                return None
            record.state = normalized
            record.updated_at = current
            session.commit()
            session.refresh(record)
            return self.pending_action_view(record)
