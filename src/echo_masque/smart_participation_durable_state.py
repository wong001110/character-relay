"""Durable Smart Participation admission/cooldown state for restart and multi-replica safety."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.sql.elements import ColumnElement

from echo_masque.persistence.database import Database
from echo_masque.persistence.smart_participation_state_models import (
    SmartParticipationDeploymentStateRecord,
    SmartParticipationScopeStateRecord,
)

_RETENTION = timedelta(days=2)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class DurableParticipationPreflight:
    channel_blocked: bool
    rate_limited: bool
    blocked_deployment_ids: frozenset[str]
    recent_deployment_id: str
    window_count: int


class SmartParticipationDurableStateService:
    """Second-line authoritative state behind the Connector's cheap local cache."""

    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def _scope_conditions(
        model: type[SmartParticipationScopeStateRecord]
        | type[SmartParticipationDeploymentStateRecord],
        *,
        connection_id: str,
        guild_id: str,
        channel_id: str,
        thread_id: str,
    ) -> tuple[ColumnElement[bool], ...]:
        return (
            model.connection_id == connection_id,
            model.guild_id == guild_id,
            model.channel_id == channel_id,
            model.thread_id == thread_id,
        )

    def preflight(
        self,
        *,
        connection_id: str,
        guild_id: str,
        channel_id: str,
        thread_id: str,
        candidate_cooldowns: dict[str, int],
        channel_cooldown_seconds: int,
        window_seconds: int,
        max_replies_per_window: int,
        now: datetime | None = None,
    ) -> DurableParticipationPreflight:
        current = _aware(now) if now is not None else datetime.now(UTC)
        with self.database.session() as session:
            scope = session.scalar(
                select(SmartParticipationScopeStateRecord).where(
                    *self._scope_conditions(
                        SmartParticipationScopeStateRecord,
                        connection_id=connection_id,
                        guild_id=guild_id,
                        channel_id=channel_id,
                        thread_id=thread_id,
                    )
                )
            )
            channel_blocked = False
            rate_limited = False
            recent = ""
            window_count = 0
            if scope is not None:
                recent = scope.recent_deployment_id
                if scope.last_admitted_at is not None:
                    channel_blocked = (
                        current - _aware(scope.last_admitted_at)
                    ).total_seconds() < max(0, channel_cooldown_seconds)
                if scope.window_started_at is not None:
                    elapsed = (current - _aware(scope.window_started_at)).total_seconds()
                    if elapsed < max(1, window_seconds):
                        window_count = scope.window_count
                        rate_limited = window_count >= max(1, max_replies_per_window)

            blocked: set[str] = set()
            for deployment_id, cooldown_seconds in candidate_cooldowns.items():
                record = session.scalar(
                    select(SmartParticipationDeploymentStateRecord).where(
                        *self._scope_conditions(
                            SmartParticipationDeploymentStateRecord,
                            connection_id=connection_id,
                            guild_id=guild_id,
                            channel_id=channel_id,
                            thread_id=thread_id,
                        ),
                        SmartParticipationDeploymentStateRecord.deployment_id == deployment_id,
                    )
                )
                if record is None or record.last_admitted_at is None:
                    continue
                elapsed = (current - _aware(record.last_admitted_at)).total_seconds()
                if elapsed < max(0, cooldown_seconds):
                    blocked.add(deployment_id)

        return DurableParticipationPreflight(
            channel_blocked=channel_blocked,
            rate_limited=rate_limited,
            blocked_deployment_ids=frozenset(blocked),
            recent_deployment_id=recent,
            window_count=window_count,
        )

    def recent_speaker(
        self,
        *,
        connection_id: str,
        guild_id: str,
        channel_id: str,
        thread_id: str,
        maximum_age_seconds: int,
        allowed_deployment_ids: frozenset[str],
        now: datetime | None = None,
    ) -> str:
        """Return a durable recent speaker only inside a bounded lightweight-follow-up window."""

        current = _aware(now) if now is not None else datetime.now(UTC)
        with self.database.session() as session:
            scope = session.scalar(
                select(SmartParticipationScopeStateRecord).where(
                    *self._scope_conditions(
                        SmartParticipationScopeStateRecord,
                        connection_id=connection_id,
                        guild_id=guild_id,
                        channel_id=channel_id,
                        thread_id=thread_id,
                    )
                )
            )
        if scope is None or scope.last_admitted_at is None:
            return ""
        if scope.recent_deployment_id not in allowed_deployment_ids:
            return ""
        age = (current - _aware(scope.last_admitted_at)).total_seconds()
        if age < 0 or age > max(1, maximum_age_seconds):
            return ""
        return scope.recent_deployment_id

    def record_admission(
        self,
        *,
        connection_id: str,
        guild_id: str,
        channel_id: str,
        thread_id: str,
        deployment_ids: tuple[str, ...],
        window_seconds: int,
        now: datetime | None = None,
    ) -> None:
        if not deployment_ids:
            return
        current = _aware(now) if now is not None else datetime.now(UTC)
        with self.database.session() as session:
            scope = session.scalar(
                select(SmartParticipationScopeStateRecord).where(
                    *self._scope_conditions(
                        SmartParticipationScopeStateRecord,
                        connection_id=connection_id,
                        guild_id=guild_id,
                        channel_id=channel_id,
                        thread_id=thread_id,
                    )
                )
            )
            if scope is None:
                scope = SmartParticipationScopeStateRecord(
                    id=str(uuid4()),
                    connection_id=connection_id,
                    guild_id=guild_id,
                    channel_id=channel_id,
                    thread_id=thread_id,
                    window_started_at=current,
                    window_count=0,
                )
                session.add(scope)
            if scope.window_started_at is None or (
                current - _aware(scope.window_started_at)
            ).total_seconds() >= max(1, window_seconds):
                scope.window_started_at = current
                scope.window_count = 0
            scope.window_count += len(deployment_ids)
            scope.last_admitted_at = current
            scope.recent_deployment_id = deployment_ids[0]
            scope.updated_at = current

            for deployment_id in deployment_ids:
                record = session.scalar(
                    select(SmartParticipationDeploymentStateRecord).where(
                        *self._scope_conditions(
                            SmartParticipationDeploymentStateRecord,
                            connection_id=connection_id,
                            guild_id=guild_id,
                            channel_id=channel_id,
                            thread_id=thread_id,
                        ),
                        SmartParticipationDeploymentStateRecord.deployment_id == deployment_id,
                    )
                )
                if record is None:
                    record = SmartParticipationDeploymentStateRecord(
                        id=str(uuid4()),
                        connection_id=connection_id,
                        guild_id=guild_id,
                        channel_id=channel_id,
                        thread_id=thread_id,
                        deployment_id=deployment_id,
                    )
                    session.add(record)
                record.last_admitted_at = current
                record.updated_at = current
            session.commit()

    def cleanup(self, *, now: datetime | None = None) -> dict[str, int]:
        current = _aware(now) if now is not None else datetime.now(UTC)
        cutoff = current - _RETENTION
        with self.database.session() as session:
            deployment_result = session.execute(
                delete(SmartParticipationDeploymentStateRecord).where(
                    SmartParticipationDeploymentStateRecord.updated_at < cutoff
                )
            )
            scope_result = session.execute(
                delete(SmartParticipationScopeStateRecord).where(
                    SmartParticipationScopeStateRecord.updated_at < cutoff
                )
            )
            session.commit()
            return {
                "deployments": int(cast(CursorResult[Any], deployment_result).rowcount or 0),
                "scopes": int(cast(CursorResult[Any], scope_result).rowcount or 0),
            }


__all__ = ["DurableParticipationPreflight", "SmartParticipationDurableStateService"]
