"""Persistence operations for Discord identities, webhooks, and reply routing."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import delete, select, update

from echo_masque.persistence.database import Database
from echo_masque.persistence.deployment_models import (
    CharacterDeploymentRecord,
    PlatformConnectionRecord,
)
from echo_masque.persistence.discord_identity_models import (
    DeploymentMessageIdentityRecord,
    DiscordMessageRouteRecord,
    DiscordWebhookBindingRecord,
)

_MESSAGE_ROUTE_RETENTION_DAYS = 180


class DiscordIdentityRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def list_identities(self, owner_id: str) -> list[DeploymentMessageIdentityRecord]:
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(DeploymentMessageIdentityRecord)
                    .where(DeploymentMessageIdentityRecord.owner_id == owner_id)
                    .order_by(DeploymentMessageIdentityRecord.created_at)
                )
            )

    def get_identity(
        self,
        deployment_id: str,
        owner_id: str,
    ) -> DeploymentMessageIdentityRecord | None:
        with self.database.session() as session:
            record = session.get(DeploymentMessageIdentityRecord, deployment_id)
            if record is None or record.owner_id != owner_id:
                return None
            return record

    def upsert_identity(
        self,
        *,
        deployment_id: str,
        owner_id: str,
        mode: str,
        display_name: str,
        avatar_url: str,
    ) -> DeploymentMessageIdentityRecord:
        with self.database.session() as session:
            deployment = session.get(CharacterDeploymentRecord, deployment_id)
            if deployment is None or deployment.owner_id != owner_id:
                raise KeyError(deployment_id)
            record = session.get(DeploymentMessageIdentityRecord, deployment_id)
            if record is None:
                record = DeploymentMessageIdentityRecord(
                    deployment_id=deployment_id,
                    owner_id=owner_id,
                    mode=mode,
                    display_name=display_name,
                    avatar_url=avatar_url,
                    webhook_status="pending" if mode == "webhook" else "not_required",
                )
                session.add(record)
            else:
                record.mode = mode
                record.display_name = display_name
                record.avatar_url = avatar_url
                if mode == "bot":
                    record.webhook_status = "not_required"
                    record.last_error = ""
                elif record.webhook_status == "not_required":
                    record.webhook_status = "pending"
            session.commit()
            session.refresh(record)
            return record

    def delete_identity(self, deployment_id: str, owner_id: str) -> bool:
        with self.database.session() as session:
            record = session.get(DeploymentMessageIdentityRecord, deployment_id)
            if record is None or record.owner_id != owner_id:
                return False
            session.execute(
                delete(DiscordMessageRouteRecord).where(
                    DiscordMessageRouteRecord.owner_id == owner_id,
                    DiscordMessageRouteRecord.deployment_id == deployment_id,
                )
            )
            session.delete(record)
            session.commit()
            return True

    def set_identity_status(
        self,
        *,
        deployment_id: str,
        status: str,
        last_error: str = "",
    ) -> None:
        with self.database.session() as session:
            record = session.get(DeploymentMessageIdentityRecord, deployment_id)
            if record is None:
                return
            record.webhook_status = status
            record.last_error = last_error
            session.commit()

    def deployment_for_connector(
        self,
        *,
        deployment_id: str,
        connection_id: str,
        channel_id: str,
    ) -> CharacterDeploymentRecord | None:
        with self.database.session() as session:
            return session.scalar(
                select(CharacterDeploymentRecord).where(
                    CharacterDeploymentRecord.id == deployment_id,
                    CharacterDeploymentRecord.connection_id == connection_id,
                    CharacterDeploymentRecord.channel_id == channel_id,
                    CharacterDeploymentRecord.platform == "discord",
                )
            )

    def get_binding(
        self,
        *,
        owner_id: str,
        connection_id: str,
        channel_id: str,
    ) -> DiscordWebhookBindingRecord | None:
        with self.database.session() as session:
            return session.scalar(
                select(DiscordWebhookBindingRecord).where(
                    DiscordWebhookBindingRecord.owner_id == owner_id,
                    DiscordWebhookBindingRecord.connection_id == connection_id,
                    DiscordWebhookBindingRecord.channel_id == channel_id,
                )
            )

    def upsert_binding(
        self,
        *,
        owner_id: str,
        connection_id: str,
        workspace_id: str,
        channel_id: str,
        webhook_id: str,
    ) -> DiscordWebhookBindingRecord:
        now = datetime.now(UTC)
        with self.database.session() as session:
            connection = session.get(PlatformConnectionRecord, connection_id)
            if (
                connection is None
                or connection.owner_id != owner_id
                or connection.platform != "discord"
            ):
                raise KeyError(connection_id)
            record = session.scalar(
                select(DiscordWebhookBindingRecord).where(
                    DiscordWebhookBindingRecord.owner_id == owner_id,
                    DiscordWebhookBindingRecord.connection_id == connection_id,
                    DiscordWebhookBindingRecord.channel_id == channel_id,
                )
            )
            if record is None:
                record = DiscordWebhookBindingRecord(
                    id=str(uuid4()),
                    owner_id=owner_id,
                    connection_id=connection_id,
                    workspace_id=workspace_id,
                    channel_id=channel_id,
                    webhook_id=webhook_id,
                    status="active",
                    last_verified_at=now,
                )
                session.add(record)
            else:
                record.workspace_id = workspace_id
                record.webhook_id = webhook_id
                record.status = "active"
                record.last_error = ""
                record.last_verified_at = now
            session.commit()
            session.refresh(record)
            return record

    def mark_binding_error(
        self,
        *,
        owner_id: str,
        connection_id: str,
        channel_id: str,
        error: str,
    ) -> None:
        with self.database.session() as session:
            record = session.scalar(
                select(DiscordWebhookBindingRecord).where(
                    DiscordWebhookBindingRecord.owner_id == owner_id,
                    DiscordWebhookBindingRecord.connection_id == connection_id,
                    DiscordWebhookBindingRecord.channel_id == channel_id,
                )
            )
            if record is None:
                return
            record.status = "error"
            record.last_error = error
            session.commit()

    def register_message_routes(
        self,
        *,
        connection_id: str,
        deployment_id: str,
        workspace_id: str,
        channel_id: str,
        thread_id: str,
        webhook_id: str,
        message_ids: list[str],
    ) -> list[DiscordMessageRouteRecord]:
        now = datetime.now(UTC)
        with self.database.session() as session:
            deployment = session.scalar(
                select(CharacterDeploymentRecord).where(
                    CharacterDeploymentRecord.id == deployment_id,
                    CharacterDeploymentRecord.connection_id == connection_id,
                    CharacterDeploymentRecord.platform == "discord",
                    CharacterDeploymentRecord.status == "active",
                    CharacterDeploymentRecord.channel_id == channel_id,
                    CharacterDeploymentRecord.thread_id == thread_id,
                )
            )
            if deployment is None:
                raise KeyError(deployment_id)
            records: list[DiscordMessageRouteRecord] = []
            for message_id in dict.fromkeys(message_ids):
                record = session.get(DiscordMessageRouteRecord, message_id)
                if record is None:
                    record = DiscordMessageRouteRecord(
                        message_id=message_id,
                        owner_id=deployment.owner_id,
                        connection_id=connection_id,
                        deployment_id=deployment.id,
                        character_card_id=deployment.character_card_id,
                        workspace_id=workspace_id,
                        channel_id=channel_id,
                        thread_id=thread_id,
                        webhook_id=webhook_id,
                        created_at=now,
                    )
                    session.add(record)
                else:
                    record.owner_id = deployment.owner_id
                    record.connection_id = connection_id
                    record.deployment_id = deployment.id
                    record.character_card_id = deployment.character_card_id
                    record.workspace_id = workspace_id
                    record.channel_id = channel_id
                    record.thread_id = thread_id
                    record.webhook_id = webhook_id
                    record.created_at = now
                records.append(record)
            cutoff = now - timedelta(days=_MESSAGE_ROUTE_RETENTION_DAYS)
            session.execute(
                delete(DiscordMessageRouteRecord).where(
                    DiscordMessageRouteRecord.created_at < cutoff
                )
            )
            session.commit()
            for record in records:
                session.refresh(record)
            return records

    def resolve_message_route(
        self,
        *,
        connection_id: str,
        message_id: str,
    ) -> DiscordMessageRouteRecord | None:
        with self.database.session() as session:
            record = session.get(DiscordMessageRouteRecord, message_id)
            if record is None or record.connection_id != connection_id:
                return None
            deployment = session.scalar(
                select(CharacterDeploymentRecord).where(
                    CharacterDeploymentRecord.id == record.deployment_id,
                    CharacterDeploymentRecord.connection_id == connection_id,
                    CharacterDeploymentRecord.platform == "discord",
                    CharacterDeploymentRecord.status == "active",
                    CharacterDeploymentRecord.channel_id == record.channel_id,
                    CharacterDeploymentRecord.thread_id == record.thread_id,
                )
            )
            return record if deployment is not None else None

    def delete_owner(self, owner_id: str) -> dict[str, int]:
        with self.database.session() as session:
            route_result = session.execute(
                delete(DiscordMessageRouteRecord).where(
                    DiscordMessageRouteRecord.owner_id == owner_id
                )
            )
            identity_result = session.execute(
                delete(DeploymentMessageIdentityRecord).where(
                    DeploymentMessageIdentityRecord.owner_id == owner_id
                )
            )
            binding_result = session.execute(
                delete(DiscordWebhookBindingRecord).where(
                    DiscordWebhookBindingRecord.owner_id == owner_id
                )
            )
            session.commit()
        return {
            "discord_message_routes": int(getattr(route_result, "rowcount", 0) or 0),
            "deployment_identities": int(
                getattr(identity_result, "rowcount", 0) or 0
            ),
            "discord_webhooks": int(getattr(binding_result, "rowcount", 0) or 0),
        }

    def claim_owner(self, source_owner_id: str, target_owner_id: str) -> dict[str, int]:
        with self.database.session() as session:
            route_result = session.execute(
                update(DiscordMessageRouteRecord)
                .where(DiscordMessageRouteRecord.owner_id == source_owner_id)
                .values(owner_id=target_owner_id)
            )
            identity_result = session.execute(
                update(DeploymentMessageIdentityRecord)
                .where(DeploymentMessageIdentityRecord.owner_id == source_owner_id)
                .values(owner_id=target_owner_id)
            )
            binding_result = session.execute(
                update(DiscordWebhookBindingRecord)
                .where(DiscordWebhookBindingRecord.owner_id == source_owner_id)
                .values(owner_id=target_owner_id)
            )
            session.commit()
        return {
            "discord_message_routes": int(getattr(route_result, "rowcount", 0) or 0),
            "deployment_identities": int(
                getattr(identity_result, "rowcount", 0) or 0
            ),
            "discord_webhooks": int(getattr(binding_result, "rowcount", 0) or 0),
        }
