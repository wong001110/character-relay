"""One-time cleanup for Discord operational content stored before Option B."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from echo_masque.discord_event_safety import (
    DISCORD_OPERATIONAL_EVENT_MESSAGE,
    safe_discord_event_details,
)
from echo_masque.persistence.database import Database
from echo_masque.persistence.deployment_models import (
    CharacterDeploymentRecord,
    DiscordConnectorEventRecord,
    PlatformConnectionRecord,
)
from echo_masque.persistence.discord_identity_models import (
    DeploymentMessageIdentityRecord,
    DiscordWebhookBindingRecord,
)
from echo_masque.persistence.operational_migration_models import (
    OperationalDataMigrationRecord,
)

DISCORD_EVENT_PRIVACY_MIGRATION_ID = "discord-event-privacy-v1"


class DiscordEventPrivacyMigration:
    """Sanitize legacy event rows and clear untrusted historical error strings."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def run(self) -> None:
        """Claim, sanitize, and complete atomically across independent processes."""

        with self.database.engine.connect() as connection:
            if self.database.engine.dialect.name == "sqlite":
                connection.exec_driver_sql("BEGIN IMMEDIATE")
            else:
                connection.begin()
            session = Session(bind=connection, expire_on_commit=False)
            try:
                now = datetime.now(UTC)
                record = session.get(
                    OperationalDataMigrationRecord,
                    DISCORD_EVENT_PRIVACY_MIGRATION_ID,
                )
                if record is not None and record.status == "completed":
                    connection.commit()
                    return
                if record is None:
                    record = OperationalDataMigrationRecord(
                        id=DISCORD_EVENT_PRIVACY_MIGRATION_ID,
                        status="running",
                        attempt_count=1,
                        affected_row_count=0,
                        last_error="",
                        started_at=now,
                        updated_at=now,
                        completed_at=None,
                    )
                    session.add(record)
                else:
                    record.status = "running"
                    record.attempt_count += 1
                    record.affected_row_count = 0
                    record.last_error = ""
                    record.started_at = now
                    record.updated_at = now
                    record.completed_at = None

                affected = self._sanitize_records(session)
                record.status = "completed"
                record.affected_row_count = affected
                record.last_error = ""
                record.updated_at = datetime.now(UTC)
                record.completed_at = record.updated_at
                session.flush()
                connection.commit()
            except Exception as exc:
                connection.rollback()
                self._record_failure(exc)
                raise
            finally:
                session.close()

    def _sanitize_records(self, session: Session) -> int:
        affected = 0
        for record in session.scalars(select(DiscordConnectorEventRecord)):
            safe_json = json.dumps(
                safe_discord_event_details(record.details_json),
                ensure_ascii=False,
            )
            if (
                record.message != DISCORD_OPERATIONAL_EVENT_MESSAGE
                or record.details_json != safe_json
            ):
                record.message = DISCORD_OPERATIONAL_EVENT_MESSAGE
                record.details_json = safe_json
                affected += 1

        for connection in session.scalars(
            select(PlatformConnectionRecord).where(PlatformConnectionRecord.platform == "discord")
        ):
            try:
                raw_metadata = json.loads(connection.metadata_json)
            except json.JSONDecodeError:
                raw_metadata = {}
            metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
            changed = False
            for key in ("last_error", "event_log_last_error"):
                if metadata.get(key):
                    metadata[key] = ""
                    changed = True
            if changed:
                connection.metadata_json = json.dumps(metadata, ensure_ascii=False)
                affected += 1

        for deployment in session.scalars(
            select(CharacterDeploymentRecord).where(
                CharacterDeploymentRecord.platform == "discord",
                CharacterDeploymentRecord.last_error != "",
            )
        ):
            deployment.last_error = ""
            affected += 1

        for identity in session.scalars(
            select(DeploymentMessageIdentityRecord).where(
                DeploymentMessageIdentityRecord.last_error != ""
            )
        ):
            identity.last_error = ""
            affected += 1

        for binding in session.scalars(
            select(DiscordWebhookBindingRecord).where(
                DiscordWebhookBindingRecord.last_error != ""
            )
        ):
            binding.last_error = ""
            affected += 1
        return affected

    def _record_failure(self, error: Exception) -> None:
        with self.database.session() as session:
            now = datetime.now(UTC)
            record = session.get(
                OperationalDataMigrationRecord,
                DISCORD_EVENT_PRIVACY_MIGRATION_ID,
            )
            if record is None:
                record = OperationalDataMigrationRecord(
                    id=DISCORD_EVENT_PRIVACY_MIGRATION_ID,
                    status="failed",
                    attempt_count=1,
                    affected_row_count=0,
                    last_error=type(error).__name__[:120],
                    started_at=now,
                    updated_at=now,
                    completed_at=None,
                )
                session.add(record)
                session.commit()
                return
            if record.status == "completed":
                return
            record.status = "failed"
            record.attempt_count += 1
            record.affected_row_count = 0
            record.last_error = type(error).__name__[:120]
            record.started_at = now
            record.updated_at = now
            record.completed_at = None
            session.commit()


__all__ = ["DISCORD_EVENT_PRIVACY_MIGRATION_ID", "DiscordEventPrivacyMigration"]
