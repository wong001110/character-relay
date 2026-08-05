"""Persistence operations for privacy-safe connector diagnostic events."""

import json
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import uuid4

from sqlalchemy import delete, or_, select, update

from echo_masque.persistence.database import Database
from echo_masque.persistence.deployment_log_models import DeploymentLogRecord
from echo_masque.persistence.deployment_models import (
    CharacterDeploymentRecord,
    PlatformConnectionRecord,
)
from echo_masque.persistence.models import utcnow
from echo_masque.security import redact

LogLevel = Literal["debug", "info", "warning", "error"]
_MAX_RECORDS_PER_OWNER = 2500


class DeploymentLogRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def record(
        self,
        *,
        connection_id: str,
        platform: str,
        level: LogLevel,
        event_type: str,
        message: str,
        deployment_id: str = "",
        workspace_id: str = "",
        channel_id: str = "",
        thread_id: str = "",
        source_message_id: str = "",
        details: dict[str, object] | None = None,
        dedupe_seconds: int = 0,
    ) -> DeploymentLogRecord | None:
        """Store one event without persisting chat message content."""

        with self.database.session() as session:
            connection = session.get(PlatformConnectionRecord, connection_id)
            if connection is None or connection.platform != platform:
                return None
            if deployment_id:
                deployment = session.get(CharacterDeploymentRecord, deployment_id)
                if (
                    deployment is None
                    or deployment.owner_id != connection.owner_id
                    or deployment.connection_id != connection_id
                ):
                    return None

            now = utcnow()
            if dedupe_seconds > 0 and not source_message_id:
                cutoff = datetime.now(UTC) - timedelta(seconds=dedupe_seconds)
                existing = session.scalar(
                    select(DeploymentLogRecord)
                    .where(
                        DeploymentLogRecord.owner_id == connection.owner_id,
                        DeploymentLogRecord.connection_id == connection_id,
                        DeploymentLogRecord.deployment_id == deployment_id,
                        DeploymentLogRecord.event_type == event_type[:80],
                        DeploymentLogRecord.message == message[:2000],
                        DeploymentLogRecord.created_at >= cutoff,
                    )
                    .order_by(DeploymentLogRecord.created_at.desc())
                    .limit(1)
                )
                if existing is not None:
                    existing.level = level
                    existing.workspace_id = workspace_id[:200]
                    existing.channel_id = channel_id[:200]
                    existing.thread_id = thread_id[:200]
                    existing.details_json = json.dumps(redact(details or {}), ensure_ascii=False)
                    existing.created_at = now
                    session.commit()
                    session.refresh(existing)
                    return existing

            record = DeploymentLogRecord(
                id=str(uuid4()),
                owner_id=connection.owner_id,
                connection_id=connection_id,
                deployment_id=deployment_id,
                platform=platform,
                level=level,
                event_type=event_type[:80],
                message=message[:2000],
                workspace_id=workspace_id[:200],
                channel_id=channel_id[:200],
                thread_id=thread_id[:200],
                source_message_id=source_message_id[:200],
                details_json=json.dumps(redact(details or {}), ensure_ascii=False),
                created_at=now,
            )
            session.add(record)
            session.flush()

            overflow_ids = list(
                session.scalars(
                    select(DeploymentLogRecord.id)
                    .where(DeploymentLogRecord.owner_id == connection.owner_id)
                    .order_by(
                        DeploymentLogRecord.created_at.desc(),
                        DeploymentLogRecord.id.desc(),
                    )
                    .offset(_MAX_RECORDS_PER_OWNER)
                )
            )
            if overflow_ids:
                session.execute(
                    delete(DeploymentLogRecord).where(DeploymentLogRecord.id.in_(overflow_ids))
                )
            session.commit()
            session.refresh(record)
            return record

    def list_events(
        self,
        owner_id: str,
        *,
        connection_id: str | None = None,
        deployment_id: str | None = None,
        level: str | None = None,
        limit: int = 100,
    ) -> list[DeploymentLogRecord]:
        with self.database.session() as session:
            query = select(DeploymentLogRecord).where(
                DeploymentLogRecord.owner_id == owner_id
            )
            if connection_id:
                query = query.where(DeploymentLogRecord.connection_id == connection_id)
            if deployment_id:
                query = query.where(
                    or_(
                        DeploymentLogRecord.deployment_id == deployment_id,
                        DeploymentLogRecord.deployment_id == "",
                    )
                )
            if level:
                query = query.where(DeploymentLogRecord.level == level)
            query = query.order_by(
                DeploymentLogRecord.created_at.desc(),
                DeploymentLogRecord.id.desc(),
            ).limit(min(max(limit, 1), 500))
            return list(session.scalars(query))

    def delete_connection_scope(self, connection_id: str) -> int:
        with self.database.session() as session:
            result = session.execute(
                delete(DeploymentLogRecord).where(
                    DeploymentLogRecord.connection_id == connection_id
                )
            )
            session.commit()
            return int(getattr(result, "rowcount", 0) or 0)

    def delete_owner(self, owner_id: str) -> dict[str, int]:
        with self.database.session() as session:
            result = session.execute(
                delete(DeploymentLogRecord).where(DeploymentLogRecord.owner_id == owner_id)
            )
            session.commit()
            return {"deployment_logs": int(getattr(result, "rowcount", 0) or 0)}

    def claim_owner(self, source_owner_id: str, target_owner_id: str) -> dict[str, int]:
        with self.database.session() as session:
            result = session.execute(
                update(DeploymentLogRecord)
                .where(DeploymentLogRecord.owner_id == source_owner_id)
                .values(owner_id=target_owner_id)
            )
            session.commit()
            return {"deployment_logs": int(getattr(result, "rowcount", 0) or 0)}
