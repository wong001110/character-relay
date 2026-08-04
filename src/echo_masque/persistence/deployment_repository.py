"""Persistence operations for platform connections and character deployments."""

import json
from uuid import uuid4

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError

from echo_masque.persistence.database import Database
from echo_masque.persistence.deployment_models import (
    CharacterDeploymentRecord,
    PlatformConnectionRecord,
)
from echo_masque.persistence.models import CharacterCardRecord, utcnow
from echo_masque.security import redact


class DeploymentConflict(RuntimeError):
    """Raised when a deployment target is already occupied by the same character."""


class DeploymentRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create_connection(
        self,
        *,
        owner_id: str,
        platform: str,
        display_name: str,
        connection_mode: str,
        external_account_id: str,
        status: str,
        metadata: dict[str, object],
    ) -> PlatformConnectionRecord:
        record = PlatformConnectionRecord(
            id=str(uuid4()),
            owner_id=owner_id,
            platform=platform,
            display_name=display_name,
            connection_mode=connection_mode,
            external_account_id=external_account_id,
            status=status,
            metadata_json=json.dumps(redact(metadata)),
        )
        with self.database.session() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
        return record

    def list_connections(self, owner_id: str) -> list[PlatformConnectionRecord]:
        with self.database.session() as session:
            query = (
                select(PlatformConnectionRecord)
                .where(PlatformConnectionRecord.owner_id == owner_id)
                .order_by(
                    PlatformConnectionRecord.platform,
                    PlatformConnectionRecord.created_at.desc(),
                )
            )
            return list(session.scalars(query))

    def get_connection(
        self, connection_id: str, owner_id: str
    ) -> PlatformConnectionRecord | None:
        with self.database.session() as session:
            record = session.get(PlatformConnectionRecord, connection_id)
            if record is None or record.owner_id != owner_id:
                return None
            return record

    def update_connection(
        self,
        connection_id: str,
        owner_id: str,
        *,
        display_name: str | None = None,
        connection_mode: str | None = None,
        external_account_id: str | None = None,
        status: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> PlatformConnectionRecord | None:
        with self.database.session() as session:
            record = session.get(PlatformConnectionRecord, connection_id)
            if record is None or record.owner_id != owner_id:
                return None
            if display_name is not None:
                record.display_name = display_name
            if connection_mode is not None:
                record.connection_mode = connection_mode
            if external_account_id is not None:
                record.external_account_id = external_account_id
            if status is not None:
                record.status = status
            if metadata is not None:
                record.metadata_json = json.dumps(redact(metadata))
            session.commit()
            session.refresh(record)
            return record

    def heartbeat_connection(
        self,
        *,
        connection_id: str,
        platform: str,
        external_account_id: str,
        display_name: str,
        status: str,
        last_error: str,
    ) -> bool:
        with self.database.session() as session:
            record = session.get(PlatformConnectionRecord, connection_id)
            if record is None or record.platform != platform:
                return False
            try:
                raw_metadata = json.loads(record.metadata_json)
            except json.JSONDecodeError:
                raw_metadata = {}
            metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
            metadata["last_error"] = last_error
            metadata["heartbeat_source"] = f"{platform}_connector"
            metadata["connector_display_name"] = display_name
            record.external_account_id = external_account_id
            record.status = status
            record.last_seen_at = utcnow()
            record.metadata_json = json.dumps(redact(metadata))
            session.commit()
            return True

    def delete_connection(self, connection_id: str, owner_id: str) -> bool:
        with self.database.session() as session:
            record = session.get(PlatformConnectionRecord, connection_id)
            if record is None or record.owner_id != owner_id:
                return False
            session.execute(
                delete(CharacterDeploymentRecord).where(
                    CharacterDeploymentRecord.owner_id == owner_id,
                    CharacterDeploymentRecord.connection_id == connection_id,
                )
            )
            session.delete(record)
            session.commit()
            return True

    def create_deployment(
        self,
        *,
        owner_id: str,
        character_card_id: str,
        connection_id: str,
        workspace_id: str,
        workspace_name: str,
        channel_id: str,
        channel_name: str,
        thread_id: str,
        thread_name: str,
        participation_mode: str,
        memory_scope: str,
        version_label: str,
        sticker_count: int,
        status: str,
    ) -> CharacterDeploymentRecord:
        with self.database.session() as session:
            character = session.get(CharacterCardRecord, character_card_id)
            if character is None or character.owner_id != owner_id:
                raise KeyError("character")
            connection = session.get(PlatformConnectionRecord, connection_id)
            if connection is None or connection.owner_id != owner_id:
                raise KeyError("connection")
            record = CharacterDeploymentRecord(
                id=str(uuid4()),
                owner_id=owner_id,
                character_card_id=character_card_id,
                connection_id=connection_id,
                platform=connection.platform,
                workspace_id=workspace_id,
                workspace_name=workspace_name,
                channel_id=channel_id,
                channel_name=channel_name,
                thread_id=thread_id,
                thread_name=thread_name,
                participation_mode=participation_mode,
                memory_scope=memory_scope,
                version_label=version_label,
                sticker_count=sticker_count,
                status=status,
            )
            session.add(record)
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise DeploymentConflict(
                    "This character is already deployed to the selected channel or thread."
                ) from exc
            session.refresh(record)
            return record

    def list_deployments(
        self,
        owner_id: str,
        *,
        character_card_id: str | None = None,
    ) -> list[CharacterDeploymentRecord]:
        with self.database.session() as session:
            query = select(CharacterDeploymentRecord).where(
                CharacterDeploymentRecord.owner_id == owner_id
            )
            if character_card_id is not None:
                query = query.where(
                    CharacterDeploymentRecord.character_card_id == character_card_id
                )
            query = query.order_by(
                CharacterDeploymentRecord.platform,
                CharacterDeploymentRecord.workspace_name,
                CharacterDeploymentRecord.channel_name,
                CharacterDeploymentRecord.thread_name,
            )
            return list(session.scalars(query))

    def list_connector_deployments(
        self,
        *,
        platform: str,
        connection_id: str,
    ) -> list[CharacterDeploymentRecord]:
        with self.database.session() as session:
            query = (
                select(CharacterDeploymentRecord)
                .where(
                    CharacterDeploymentRecord.platform == platform,
                    CharacterDeploymentRecord.connection_id == connection_id,
                    CharacterDeploymentRecord.status == "active",
                )
                .order_by(
                    CharacterDeploymentRecord.workspace_name,
                    CharacterDeploymentRecord.channel_name,
                    CharacterDeploymentRecord.thread_name,
                )
            )
            return list(session.scalars(query))

    def find_connector_deployment(
        self,
        *,
        platform: str,
        connection_id: str,
        channel_id: str,
        thread_id: str,
    ) -> CharacterDeploymentRecord | None:
        with self.database.session() as session:
            query = select(CharacterDeploymentRecord).where(
                CharacterDeploymentRecord.platform == platform,
                CharacterDeploymentRecord.connection_id == connection_id,
                CharacterDeploymentRecord.status == "active",
                CharacterDeploymentRecord.channel_id == channel_id,
                CharacterDeploymentRecord.thread_id == thread_id,
            )
            return session.scalar(query)

    def get_deployment(
        self, deployment_id: str, owner_id: str
    ) -> CharacterDeploymentRecord | None:
        with self.database.session() as session:
            record = session.get(CharacterDeploymentRecord, deployment_id)
            if record is None or record.owner_id != owner_id:
                return None
            return record

    def update_deployment(
        self,
        deployment_id: str,
        owner_id: str,
        *,
        workspace_id: str | None = None,
        workspace_name: str | None = None,
        channel_id: str | None = None,
        channel_name: str | None = None,
        thread_id: str | None = None,
        thread_name: str | None = None,
        participation_mode: str | None = None,
        memory_scope: str | None = None,
        version_label: str | None = None,
        sticker_count: int | None = None,
        status: str | None = None,
        last_error: str | None = None,
    ) -> CharacterDeploymentRecord | None:
        with self.database.session() as session:
            record = session.get(CharacterDeploymentRecord, deployment_id)
            if record is None or record.owner_id != owner_id:
                return None
            values: dict[str, object] = {
                "workspace_id": workspace_id,
                "workspace_name": workspace_name,
                "channel_id": channel_id,
                "channel_name": channel_name,
                "thread_id": thread_id,
                "thread_name": thread_name,
                "participation_mode": participation_mode,
                "memory_scope": memory_scope,
                "version_label": version_label,
                "sticker_count": sticker_count,
                "status": status,
                "last_error": last_error,
            }
            for field, value in values.items():
                if value is not None:
                    setattr(record, field, value)
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise DeploymentConflict(
                    "This character is already deployed to the selected channel or thread."
                ) from exc
            session.refresh(record)
            return record

    def record_deployment_activity(self, deployment_id: str) -> None:
        with self.database.session() as session:
            record = session.get(CharacterDeploymentRecord, deployment_id)
            if record is None:
                return
            record.status = "active"
            record.last_message_at = utcnow()
            record.last_error = ""
            session.commit()

    def record_deployment_error(self, deployment_id: str, message: str) -> None:
        with self.database.session() as session:
            record = session.get(CharacterDeploymentRecord, deployment_id)
            if record is None:
                return
            record.status = "error"
            record.last_error = message[:2000]
            session.commit()

    def delete_deployment(self, deployment_id: str, owner_id: str) -> bool:
        with self.database.session() as session:
            record = session.get(CharacterDeploymentRecord, deployment_id)
            if record is None or record.owner_id != owner_id:
                return False
            session.delete(record)
            session.commit()
            return True

    def delete_owner(self, owner_id: str) -> dict[str, int]:
        """Delete all connector configuration owned by an account."""
        with self.database.session() as session:
            deployment_result = session.execute(
                delete(CharacterDeploymentRecord).where(
                    CharacterDeploymentRecord.owner_id == owner_id
                )
            )
            connection_result = session.execute(
                delete(PlatformConnectionRecord).where(
                    PlatformConnectionRecord.owner_id == owner_id
                )
            )
            session.commit()
        return {
            "deployments": int(getattr(deployment_result, "rowcount", 0) or 0),
            "connections": int(getattr(connection_result, "rowcount", 0) or 0),
        }

    def claim_owner(self, source_owner_id: str, target_owner_id: str) -> dict[str, int]:
        """Move legacy local connector configuration into an authenticated workspace."""
        with self.database.session() as session:
            connection_result = session.execute(
                update(PlatformConnectionRecord)
                .where(PlatformConnectionRecord.owner_id == source_owner_id)
                .values(owner_id=target_owner_id)
            )
            deployment_result = session.execute(
                update(CharacterDeploymentRecord)
                .where(CharacterDeploymentRecord.owner_id == source_owner_id)
                .values(owner_id=target_owner_id)
            )
            session.commit()
        return {
            "connections": int(getattr(connection_result, "rowcount", 0) or 0),
            "deployments": int(getattr(deployment_result, "rowcount", 0) or 0),
        }
