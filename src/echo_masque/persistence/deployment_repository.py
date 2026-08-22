"""Persistence operations for platform connections and character deployments."""

import json
import math
from datetime import datetime
from uuid import uuid4

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError

from echo_masque.discord_event_safety import (
    DISCORD_OPERATIONAL_EVENT_MESSAGE,
    safe_discord_event_details,
)
from echo_masque.persistence.database import Database
from echo_masque.persistence.deployment_models import (
    CharacterDeploymentRecord,
    DiscordConnectorEventRecord,
    DiscordDeploymentScopeRecord,
    DiscordServerCatalogRecord,
    DiscordServerProfileRecord,
    PlatformConnectionRecord,
)
from echo_masque.persistence.models import CharacterCardRecord, utcnow
from echo_masque.security import redact


class DeploymentConflict(RuntimeError):
    """Raised when a deployment or reusable server profile conflicts."""


_MAX_DISCORD_EVENTS_PER_CONNECTION = 5_000
def _normalized_ids(values: list[str] | None) -> list[str]:
    return list(dict.fromkeys(item.strip() for item in (values or []) if item.strip()))


def _encode_ids(values: list[str] | None) -> str:
    return json.dumps(_normalized_ids(values))


def decode_ids(value: str) -> list[str]:
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(decoded, list):
        return []
    return _normalized_ids([item for item in decoded if isinstance(item, str)])


def decode_channels(value: str) -> list[dict[str, object]]:
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(decoded, list):
        return []
    return [item for item in decoded if isinstance(item, dict)]


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

    def get_connection(self, connection_id: str, owner_id: str) -> PlatformConnectionRecord | None:
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
        replica_region: str = "",
        replica_id: str = "",
        gateway_ready: bool = False,
        state_synchronized: bool = False,
        visible_server_count: int = 0,
        event_log_pending_count: int = 0,
        event_log_last_error: str = "",
        event_log_last_success_at: str = "",
        event_log_last_recorded_at: str = "",
        event_log_last_recorded_type: str = "",
        event_log_sent_count: int = 0,
        last_gateway_message_at: str = "",
        last_gateway_message_id: str = "",
        last_gateway_mentioned_bot: bool = False,
        turn_collector_enabled: bool = False,
        turn_collector_quiet_window_ms: int = 0,
        turn_collector_max_wait_ms: int = 0,
        turn_collector_max_messages: int = 0,
        turn_collector_max_characters: int = 0,
        turn_collector_pending_burst_scope_count: int = 0,
        turn_collector_pending_preflight_scope_count: int = 0,
        turn_collector_candidate_messages: int = 0,
        turn_collector_bypass_messages: int = 0,
        turn_collector_bursts: int = 0,
        turn_collector_collected_messages: int = 0,
        turn_collector_collapsed_messages: int = 0,
        turn_collector_interaction_bypasses: int = 0,
        turn_collector_bypass_reasons: dict[str, int] | None = None,
        turn_collector_last_burst_at: str = "",
        turn_collector_last_burst_id: str = "",
        turn_collector_last_flush_reason: str = "",
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
            metadata["replica_region"] = replica_region
            metadata["replica_id"] = replica_id
            metadata["gateway_ready"] = gateway_ready
            metadata["state_synchronized"] = state_synchronized
            metadata["visible_server_count"] = visible_server_count
            metadata["event_log_pending_count"] = event_log_pending_count
            metadata["event_log_last_error"] = event_log_last_error
            metadata["event_log_last_success_at"] = event_log_last_success_at
            metadata["event_log_last_recorded_at"] = event_log_last_recorded_at
            metadata["event_log_last_recorded_type"] = event_log_last_recorded_type
            metadata["event_log_sent_count"] = event_log_sent_count
            metadata["last_gateway_message_at"] = last_gateway_message_at
            metadata["last_gateway_message_id"] = last_gateway_message_id
            metadata["last_gateway_mentioned_bot"] = last_gateway_mentioned_bot
            metadata["turn_collector_enabled"] = turn_collector_enabled
            metadata["turn_collector_quiet_window_ms"] = turn_collector_quiet_window_ms
            metadata["turn_collector_max_wait_ms"] = turn_collector_max_wait_ms
            metadata["turn_collector_max_messages"] = turn_collector_max_messages
            metadata["turn_collector_max_characters"] = turn_collector_max_characters
            metadata["turn_collector_pending_burst_scope_count"] = (
                turn_collector_pending_burst_scope_count
            )
            metadata["turn_collector_pending_preflight_scope_count"] = (
                turn_collector_pending_preflight_scope_count
            )
            metadata["turn_collector_candidate_messages"] = turn_collector_candidate_messages
            metadata["turn_collector_bypass_messages"] = turn_collector_bypass_messages
            metadata["turn_collector_bursts"] = turn_collector_bursts
            metadata["turn_collector_collected_messages"] = turn_collector_collected_messages
            metadata["turn_collector_collapsed_messages"] = turn_collector_collapsed_messages
            metadata["turn_collector_interaction_bypasses"] = turn_collector_interaction_bypasses
            metadata["turn_collector_bypass_reasons"] = turn_collector_bypass_reasons or {}
            metadata["turn_collector_last_burst_at"] = turn_collector_last_burst_at
            metadata["turn_collector_last_burst_id"] = turn_collector_last_burst_id
            metadata["turn_collector_last_flush_reason"] = turn_collector_last_flush_reason
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
            deployment_ids = list(
                session.scalars(
                    select(CharacterDeploymentRecord.id).where(
                        CharacterDeploymentRecord.owner_id == owner_id,
                        CharacterDeploymentRecord.connection_id == connection_id,
                    )
                )
            )
            if deployment_ids:
                session.execute(
                    delete(DiscordDeploymentScopeRecord).where(
                        DiscordDeploymentScopeRecord.deployment_id.in_(deployment_ids)
                    )
                )
            session.execute(
                delete(CharacterDeploymentRecord).where(
                    CharacterDeploymentRecord.owner_id == owner_id,
                    CharacterDeploymentRecord.connection_id == connection_id,
                )
            )
            session.execute(
                delete(DiscordServerProfileRecord).where(
                    DiscordServerProfileRecord.owner_id == owner_id,
                    DiscordServerProfileRecord.connection_id == connection_id,
                )
            )
            session.execute(
                delete(DiscordServerCatalogRecord).where(
                    DiscordServerCatalogRecord.owner_id == owner_id,
                    DiscordServerCatalogRecord.connection_id == connection_id,
                )
            )
            session.execute(
                delete(DiscordConnectorEventRecord).where(
                    DiscordConnectorEventRecord.owner_id == owner_id,
                    DiscordConnectorEventRecord.connection_id == connection_id,
                )
            )
            session.delete(record)
            session.commit()
            return True

    def record_discord_events(
        self,
        *,
        connection_id: str,
        events: list[dict[str, object]],
    ) -> int:
        with self.database.session() as session:
            connection = session.get(PlatformConnectionRecord, connection_id)
            if connection is None or connection.platform != "discord":
                raise KeyError("connection")

            requested_deployment_ids = {
                str(item.get("deployment_id", "")).strip()
                for item in events
                if str(item.get("deployment_id", "")).strip()
            }
            valid_deployment_ids = set(
                session.scalars(
                    select(CharacterDeploymentRecord.id).where(
                        CharacterDeploymentRecord.connection_id == connection_id,
                        CharacterDeploymentRecord.id.in_(requested_deployment_ids),
                    )
                )
            )
            invalid = requested_deployment_ids - valid_deployment_ids
            if invalid:
                raise ValueError("One or more Discord event deployment IDs are invalid.")

            inserted = 0
            for item in events:
                event_id = str(item["id"])
                if session.get(DiscordConnectorEventRecord, event_id) is not None:
                    continue
                occurred_at = item["occurred_at"]
                if not isinstance(occurred_at, datetime):
                    raise ValueError("Discord event occurred_at must be a datetime.")
                details = item.get("details", {})
                safe_details = details if isinstance(details, dict) else {}
                session.add(
                    DiscordConnectorEventRecord(
                        id=event_id,
                        owner_id=connection.owner_id,
                        connection_id=connection_id,
                        level=str(item["level"])[:16],
                        event_type=str(item["event_type"])[:80],
                        message=DISCORD_OPERATIONAL_EVENT_MESSAGE,
                        guild_id=str(item.get("guild_id", ""))[:200],
                        guild_name=str(item.get("guild_name", ""))[:160],
                        channel_id=str(item.get("channel_id", ""))[:200],
                        channel_name=str(item.get("channel_name", ""))[:160],
                        thread_id=str(item.get("thread_id", ""))[:200],
                        thread_name=str(item.get("thread_name", ""))[:160],
                        source_message_id=str(item.get("source_message_id", ""))[:200],
                        deployment_id=str(item.get("deployment_id", ""))[:64],
                        character_name=str(item.get("character_name", ""))[:160],
                        details_json=json.dumps(
                            safe_discord_event_details(safe_details), ensure_ascii=False
                        ),
                        occurred_at=occurred_at,
                    )
                )
                inserted += 1

            session.flush()
            overflow_ids = list(
                session.scalars(
                    select(DiscordConnectorEventRecord.id)
                    .where(DiscordConnectorEventRecord.connection_id == connection_id)
                    .order_by(
                        DiscordConnectorEventRecord.occurred_at.desc(),
                        DiscordConnectorEventRecord.id.desc(),
                    )
                    .offset(_MAX_DISCORD_EVENTS_PER_CONNECTION)
                )
            )
            if overflow_ids:
                session.execute(
                    delete(DiscordConnectorEventRecord).where(
                        DiscordConnectorEventRecord.id.in_(overflow_ids)
                    )
                )
            session.commit()
            return inserted

    def list_discord_events(
        self,
        owner_id: str,
        *,
        page: int = 1,
        page_size: int = 50,
        connection_id: str | None = None,
        guild_id: str | None = None,
        level: str | None = None,
        event_type: str | None = None,
    ) -> tuple[list[DiscordConnectorEventRecord], int, int, int]:
        with self.database.session() as session:
            conditions = [DiscordConnectorEventRecord.owner_id == owner_id]
            if connection_id is not None:
                conditions.append(DiscordConnectorEventRecord.connection_id == connection_id)
            if guild_id is not None:
                conditions.append(DiscordConnectorEventRecord.guild_id == guild_id)
            if level is not None:
                conditions.append(DiscordConnectorEventRecord.level == level)
            if event_type is not None:
                conditions.append(DiscordConnectorEventRecord.event_type == event_type)

            total = int(
                session.scalar(
                    select(func.count()).select_from(DiscordConnectorEventRecord).where(*conditions)
                )
                or 0
            )
            pages = max(1, math.ceil(total / page_size))
            safe_page = min(max(page, 1), pages)
            records = list(
                session.scalars(
                    select(DiscordConnectorEventRecord)
                    .where(*conditions)
                    .order_by(
                        DiscordConnectorEventRecord.occurred_at.desc(),
                        DiscordConnectorEventRecord.id.desc(),
                    )
                    .offset((safe_page - 1) * page_size)
                    .limit(page_size)
                )
            )
            return records, safe_page, total, pages

    def sync_discord_server_catalog(
        self,
        *,
        connection_id: str,
        servers: list[tuple[str, str, list[dict[str, object]]]],
        visible_guild_ids: list[str] | None = None,
        failed_guild_ids: list[str] | None = None,
    ) -> list[DiscordServerCatalogRecord]:
        """Upsert successful snapshots and delete only Guilds explicitly no longer visible."""

        with self.database.session() as session:
            connection = session.get(PlatformConnectionRecord, connection_id)
            if connection is None or connection.platform != "discord":
                raise KeyError("connection")
            existing = {
                item.guild_id: item
                for item in session.scalars(
                    select(DiscordServerCatalogRecord).where(
                        DiscordServerCatalogRecord.connection_id == connection_id
                    )
                )
            }
            now = utcnow()
            records: list[DiscordServerCatalogRecord] = []
            for guild_id, guild_name, channels in servers:
                record = existing.get(guild_id)
                if record is None:
                    record = DiscordServerCatalogRecord(
                        id=str(uuid4()),
                        owner_id=connection.owner_id,
                        connection_id=connection_id,
                        guild_id=guild_id,
                        guild_name=guild_name,
                    )
                    session.add(record)
                record.guild_name = guild_name
                record.channels_json = json.dumps(channels)
                record.synced_at = now
                records.append(record)
            if visible_guild_ids is not None:
                visible = set(_normalized_ids(visible_guild_ids))
                visible.update(_normalized_ids(failed_guild_ids))
                for guild_id, record in existing.items():
                    if guild_id not in visible:
                        session.delete(record)
            session.commit()
            for record in records:
                session.refresh(record)
            return records

    def list_discord_server_catalog(
        self,
        owner_id: str,
        *,
        connection_id: str | None = None,
    ) -> list[DiscordServerCatalogRecord]:
        with self.database.session() as session:
            query = select(DiscordServerCatalogRecord).where(
                DiscordServerCatalogRecord.owner_id == owner_id
            )
            if connection_id is not None:
                query = query.where(DiscordServerCatalogRecord.connection_id == connection_id)
            query = query.order_by(
                DiscordServerCatalogRecord.guild_name,
                DiscordServerCatalogRecord.guild_id,
            )
            return list(session.scalars(query))

    def list_shared_connections_for_profiles(
        self,
        owner_id: str,
    ) -> list[PlatformConnectionRecord]:
        """Return managed Discord connections referenced by this owner's claims."""

        with self.database.session() as session:
            return list(
                session.scalars(
                    select(PlatformConnectionRecord)
                    .join(
                        DiscordServerProfileRecord,
                        DiscordServerProfileRecord.connection_id == PlatformConnectionRecord.id,
                    )
                    .where(
                        DiscordServerProfileRecord.owner_id == owner_id,
                        PlatformConnectionRecord.owner_id != owner_id,
                        PlatformConnectionRecord.platform == "discord",
                    )
                    .distinct()
                    .order_by(PlatformConnectionRecord.created_at)
                )
            )

    def list_claimed_discord_server_catalog(
        self,
        owner_id: str,
    ) -> list[DiscordServerCatalogRecord]:
        """Return only catalog rows represented by this owner's Server Profiles."""

        with self.database.session() as session:
            return list(
                session.scalars(
                    select(DiscordServerCatalogRecord)
                    .join(
                        DiscordServerProfileRecord,
                        (
                            DiscordServerProfileRecord.connection_id
                            == DiscordServerCatalogRecord.connection_id
                        )
                        & (
                            DiscordServerProfileRecord.guild_id
                            == DiscordServerCatalogRecord.guild_id
                        ),
                    )
                    .where(DiscordServerProfileRecord.owner_id == owner_id)
                    .distinct()
                    .order_by(
                        DiscordServerCatalogRecord.guild_name,
                        DiscordServerCatalogRecord.guild_id,
                    )
                )
            )

    def claim_server_profile(
        self,
        *,
        owner_id: str,
        catalog_owner_id: str,
        guild_id: str,
        name: str,
    ) -> DiscordServerProfileRecord:
        """Claim one exact Super Admin-managed Discord Server for an account."""

        with self.database.session() as session:
            catalog = session.scalar(
                select(DiscordServerCatalogRecord)
                .where(
                    DiscordServerCatalogRecord.owner_id == catalog_owner_id,
                    DiscordServerCatalogRecord.guild_id == guild_id,
                )
                .order_by(DiscordServerCatalogRecord.synced_at.desc())
                .limit(1)
            )
            if catalog is None:
                raise KeyError("server catalog")
            connection = session.get(PlatformConnectionRecord, catalog.connection_id)
            if (
                connection is None
                or connection.platform != "discord"
                or connection.owner_id != catalog_owner_id
            ):
                raise KeyError("connection")

            existing = session.scalar(
                select(DiscordServerProfileRecord).where(
                    DiscordServerProfileRecord.owner_id == owner_id,
                    DiscordServerProfileRecord.connection_id == catalog.connection_id,
                    DiscordServerProfileRecord.guild_id == guild_id,
                )
            )
            if existing is not None:
                raise DeploymentConflict("This Discord Server is already in your account.")

            if owner_id != catalog_owner_id:
                claimed_elsewhere = session.scalar(
                    select(DiscordServerProfileRecord.id)
                    .where(
                        DiscordServerProfileRecord.connection_id == catalog.connection_id,
                        DiscordServerProfileRecord.guild_id == guild_id,
                        DiscordServerProfileRecord.owner_id.not_in((catalog_owner_id, owner_id)),
                    )
                    .limit(1)
                )
                if claimed_elsewhere is not None:
                    raise DeploymentConflict(
                        "This Discord Server has already been claimed by another account."
                    )

            record = DiscordServerProfileRecord(
                id=str(uuid4()),
                owner_id=owner_id,
                connection_id=catalog.connection_id,
                name=name.strip() or catalog.guild_name,
                guild_id=catalog.guild_id,
                guild_name=catalog.guild_name,
                channel_scope_mode="all_except",
                excluded_channel_ids_json="[]",
                excluded_category_ids_json="[]",
                thread_policy="inherit_parent",
            )
            session.add(record)
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise DeploymentConflict("This Discord Server is already in your account.") from exc
            session.refresh(record)
            return record

    def create_server_profile(
        self,
        *,
        owner_id: str,
        connection_id: str,
        name: str,
        guild_id: str,
        guild_name: str,
        excluded_channel_ids: list[str],
        excluded_category_ids: list[str],
        thread_policy: str,
    ) -> DiscordServerProfileRecord:
        with self.database.session() as session:
            connection = session.get(PlatformConnectionRecord, connection_id)
            if (
                connection is None
                or connection.owner_id != owner_id
                or connection.platform != "discord"
            ):
                raise KeyError("connection")
            record = DiscordServerProfileRecord(
                id=str(uuid4()),
                owner_id=owner_id,
                connection_id=connection_id,
                name=name,
                guild_id=guild_id,
                guild_name=guild_name,
                channel_scope_mode="all_except",
                excluded_channel_ids_json=_encode_ids(excluded_channel_ids),
                excluded_category_ids_json=_encode_ids(excluded_category_ids),
                thread_policy=thread_policy,
            )
            session.add(record)
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise DeploymentConflict(
                    "A Discord server profile already exists for this account and server."
                ) from exc
            session.refresh(record)
            return record

    def list_server_profiles(self, owner_id: str) -> list[DiscordServerProfileRecord]:
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(DiscordServerProfileRecord)
                    .where(DiscordServerProfileRecord.owner_id == owner_id)
                    .order_by(
                        DiscordServerProfileRecord.name,
                        DiscordServerProfileRecord.guild_name,
                    )
                )
            )

    def get_server_profile(
        self, profile_id: str, owner_id: str
    ) -> DiscordServerProfileRecord | None:
        with self.database.session() as session:
            record = session.get(DiscordServerProfileRecord, profile_id)
            if record is None or record.owner_id != owner_id:
                return None
            return record

    def update_server_profile(
        self,
        profile_id: str,
        owner_id: str,
        *,
        name: str | None = None,
        guild_name: str | None = None,
        excluded_channel_ids: list[str] | None = None,
        excluded_category_ids: list[str] | None = None,
        thread_policy: str | None = None,
    ) -> DiscordServerProfileRecord | None:
        with self.database.session() as session:
            record = session.get(DiscordServerProfileRecord, profile_id)
            if record is None or record.owner_id != owner_id:
                return None
            if name is not None:
                record.name = name
            if guild_name is not None:
                record.guild_name = guild_name
            if excluded_channel_ids is not None:
                record.excluded_channel_ids_json = _encode_ids(excluded_channel_ids)
            if excluded_category_ids is not None:
                record.excluded_category_ids_json = _encode_ids(excluded_category_ids)
            if thread_policy is not None:
                record.thread_policy = thread_policy
            session.commit()
            session.refresh(record)
            return record

    def delete_server_profile(self, profile_id: str, owner_id: str) -> bool:
        with self.database.session() as session:
            record = session.get(DiscordServerProfileRecord, profile_id)
            if record is None or record.owner_id != owner_id:
                return False
            used = session.scalar(
                select(DiscordDeploymentScopeRecord.deployment_id)
                .where(DiscordDeploymentScopeRecord.server_profile_id == profile_id)
                .limit(1)
            )
            if used is not None:
                raise DeploymentConflict(
                    "Remove or convert deployments using this server profile first."
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
        server_profile_id: str = "",
        excluded_channel_ids: list[str] | None = None,
        excluded_category_ids: list[str] | None = None,
    ) -> CharacterDeploymentRecord:
        with self.database.session() as session:
            character = session.get(CharacterCardRecord, character_card_id)
            if character is None or character.owner_id != owner_id:
                raise KeyError("character")
            connection = session.get(PlatformConnectionRecord, connection_id)
            if connection is None:
                raise KeyError("connection")

            profile: DiscordServerProfileRecord | None = None
            if server_profile_id:
                profile = session.get(DiscordServerProfileRecord, server_profile_id)
                if (
                    profile is None
                    or profile.owner_id != owner_id
                    or profile.connection_id != connection_id
                ):
                    raise KeyError("server profile")
                if connection.platform != "discord":
                    raise DeploymentConflict(
                        "Discord server profiles can only be used with Discord connections."
                    )
                workspace_id = profile.guild_id
                workspace_name = profile.guild_name
                channel_id = f"@server:{profile.id}"
                channel_name = "All available channels"
                thread_id = ""
                thread_name = ""
            elif connection.owner_id != owner_id:
                raise KeyError("connection")
            elif not channel_id or not channel_name:
                raise DeploymentConflict(
                    "A channel is required when no Discord server profile is selected."
                )

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
            if profile is not None:
                session.add(
                    DiscordDeploymentScopeRecord(
                        deployment_id=record.id,
                        owner_id=owner_id,
                        server_profile_id=profile.id,
                        channel_scope_mode="all_except",
                        excluded_channel_ids_json=_encode_ids(excluded_channel_ids),
                        excluded_category_ids_json=_encode_ids(excluded_category_ids),
                    )
                )
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise DeploymentConflict(
                    "This character is already deployed to the selected destination."
                ) from exc
            session.refresh(record)
            return record

    def list_deployments(
        self,
        owner_id: str,
        *,
        character_card_id: str | None = None,
        server_profile_id: str | None = None,
    ) -> list[CharacterDeploymentRecord]:
        with self.database.session() as session:
            query = select(CharacterDeploymentRecord)
            if server_profile_id is not None:
                query = query.join(
                    DiscordDeploymentScopeRecord,
                    DiscordDeploymentScopeRecord.deployment_id == CharacterDeploymentRecord.id,
                )
            query = query.where(CharacterDeploymentRecord.owner_id == owner_id)
            if character_card_id is not None:
                query = query.where(
                    CharacterDeploymentRecord.character_card_id == character_card_id
                )
            if server_profile_id is not None:
                query = query.where(
                    DiscordDeploymentScopeRecord.server_profile_id == server_profile_id
                )
            query = query.order_by(
                CharacterDeploymentRecord.platform,
                CharacterDeploymentRecord.workspace_name,
                CharacterDeploymentRecord.channel_name,
                CharacterDeploymentRecord.thread_name,
            )
            return list(session.scalars(query))

    def list_deployments_page(
        self,
        owner_id: str,
        *,
        page: int = 1,
        page_size: int = 20,
        character_card_id: str | None = None,
        platform: str | None = None,
        status: str | None = None,
        server_profile_id: str | None = None,
    ) -> tuple[
        list[CharacterDeploymentRecord],
        int,
        int,
        int,
        dict[str, int],
    ]:
        with self.database.session() as session:
            conditions = [CharacterDeploymentRecord.owner_id == owner_id]
            if server_profile_id is not None:
                conditions.append(
                    DiscordDeploymentScopeRecord.server_profile_id == server_profile_id
                )
            if character_card_id is not None:
                conditions.append(CharacterDeploymentRecord.character_card_id == character_card_id)
            if platform is not None:
                conditions.append(CharacterDeploymentRecord.platform == platform)
            if status is not None:
                conditions.append(CharacterDeploymentRecord.status == status)
            count_query = select(func.count()).select_from(CharacterDeploymentRecord)
            records_query = select(CharacterDeploymentRecord)
            if server_profile_id is not None:
                count_query = count_query.join(
                    DiscordDeploymentScopeRecord,
                    DiscordDeploymentScopeRecord.deployment_id == CharacterDeploymentRecord.id,
                )
                records_query = records_query.join(
                    DiscordDeploymentScopeRecord,
                    DiscordDeploymentScopeRecord.deployment_id == CharacterDeploymentRecord.id,
                )
            total = int(session.scalar(count_query.where(*conditions)) or 0)
            pages = max(1, math.ceil(total / page_size))
            safe_page = min(max(1, page), pages)
            records = list(
                session.scalars(
                    records_query.where(*conditions)
                    .order_by(
                        CharacterDeploymentRecord.updated_at.desc(),
                        CharacterDeploymentRecord.id.desc(),
                    )
                    .offset((safe_page - 1) * page_size)
                    .limit(page_size)
                )
            )

            def scoped_status_count(statuses: tuple[str, ...]) -> int:
                query = select(func.count()).select_from(CharacterDeploymentRecord)
                count_conditions = [
                    CharacterDeploymentRecord.owner_id == owner_id,
                    CharacterDeploymentRecord.status.in_(statuses),
                ]
                if server_profile_id is not None:
                    query = query.join(
                        DiscordDeploymentScopeRecord,
                        DiscordDeploymentScopeRecord.deployment_id == CharacterDeploymentRecord.id,
                    )
                    count_conditions.append(
                        DiscordDeploymentScopeRecord.server_profile_id == server_profile_id
                    )
                return int(session.scalar(query.where(*count_conditions)) or 0)

            counts = {
                "active": scoped_status_count(("active",)),
                "paused": scoped_status_count(("paused",)),
                "attention": scoped_status_count(("error", "offline")),
            }
            return records, safe_page, total, pages, counts

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

    def get_deployment(self, deployment_id: str, owner_id: str) -> CharacterDeploymentRecord | None:
        with self.database.session() as session:
            record = session.get(CharacterDeploymentRecord, deployment_id)
            if record is None or record.owner_id != owner_id:
                return None
            return record

    def get_deployment_scope(self, deployment_id: str) -> DiscordDeploymentScopeRecord | None:
        with self.database.session() as session:
            return session.get(DiscordDeploymentScopeRecord, deployment_id)

    def get_server_profile_for_deployment(
        self, deployment_id: str
    ) -> DiscordServerProfileRecord | None:
        with self.database.session() as session:
            scope = session.get(DiscordDeploymentScopeRecord, deployment_id)
            if scope is None:
                return None
            return session.get(DiscordServerProfileRecord, scope.server_profile_id)

    def get_active_discord_deployment_for_guild(
        self,
        deployment_id: str,
        *,
        connection_id: str,
        guild_id: str,
    ) -> CharacterDeploymentRecord | None:
        """Validate immutable deployment/guild ownership before durable ingress claim.

        Channel/category exclusions remain owned by ``deployment_matches_discord_destination`` so
        an excluded destination preserves the established fail-silent Runtime behavior.
        """

        with self.database.session() as session:
            deployment = session.get(CharacterDeploymentRecord, deployment_id)
            if (
                deployment is None
                or deployment.connection_id != connection_id
                or deployment.platform != "discord"
                or deployment.status != "active"
            ):
                return None
            scope = session.get(DiscordDeploymentScopeRecord, deployment_id)
            if scope is None:
                return deployment if deployment.workspace_id == guild_id else None
            profile = session.get(DiscordServerProfileRecord, scope.server_profile_id)
            if profile is None or profile.guild_id != guild_id:
                return None
            return deployment

    def deployment_matches_discord_destination(
        self,
        deployment_id: str,
        *,
        connection_id: str,
        guild_id: str,
        channel_id: str,
        thread_id: str,
        category_id: str = "",
    ) -> CharacterDeploymentRecord | None:
        with self.database.session() as session:
            deployment = session.get(CharacterDeploymentRecord, deployment_id)
            if (
                deployment is None
                or deployment.connection_id != connection_id
                or deployment.platform != "discord"
                or deployment.status != "active"
            ):
                return None
            scope = session.get(DiscordDeploymentScopeRecord, deployment_id)
            if scope is None:
                if (
                    deployment.workspace_id == guild_id
                    and deployment.channel_id == channel_id
                    and deployment.thread_id == thread_id
                ):
                    return deployment
                return None
            profile = session.get(DiscordServerProfileRecord, scope.server_profile_id)
            if profile is None or profile.guild_id != guild_id:
                return None
            if channel_id in decode_ids(profile.excluded_channel_ids_json):
                return None
            if category_id and category_id in decode_ids(profile.excluded_category_ids_json):
                return None
            if channel_id in decode_ids(scope.excluded_channel_ids_json):
                return None
            if category_id and category_id in decode_ids(scope.excluded_category_ids_json):
                return None
            return deployment

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
        server_profile_id: str | None = None,
        excluded_channel_ids: list[str] | None = None,
        excluded_category_ids: list[str] | None = None,
    ) -> CharacterDeploymentRecord | None:
        with self.database.session() as session:
            record = session.get(CharacterDeploymentRecord, deployment_id)
            if record is None or record.owner_id != owner_id:
                return None

            scope = session.get(DiscordDeploymentScopeRecord, deployment_id)
            if server_profile_id is not None:
                if server_profile_id:
                    profile = session.get(DiscordServerProfileRecord, server_profile_id)
                    if (
                        profile is None
                        or profile.owner_id != owner_id
                        or profile.connection_id != record.connection_id
                    ):
                        raise KeyError("server profile")
                    if record.platform != "discord":
                        raise DeploymentConflict(
                            "Discord server profiles can only be used with Discord deployments."
                        )
                    record.workspace_id = profile.guild_id
                    record.workspace_name = profile.guild_name
                    record.channel_id = f"@server:{profile.id}"
                    record.channel_name = "All available channels"
                    record.thread_id = ""
                    record.thread_name = ""
                    if scope is None:
                        scope = DiscordDeploymentScopeRecord(
                            deployment_id=record.id,
                            owner_id=owner_id,
                            server_profile_id=profile.id,
                            channel_scope_mode="all_except",
                            excluded_channel_ids_json="[]",
                            excluded_category_ids_json="[]",
                        )
                        session.add(scope)
                    else:
                        scope.server_profile_id = profile.id
                elif scope is not None:
                    session.delete(scope)
                    scope = None

            if scope is not None:
                if excluded_channel_ids is not None:
                    scope.excluded_channel_ids_json = _encode_ids(excluded_channel_ids)
                if excluded_category_ids is not None:
                    scope.excluded_category_ids_json = _encode_ids(excluded_category_ids)

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
            profile_selected = scope is not None
            for field, value in values.items():
                if value is None:
                    continue
                if profile_selected and field in {
                    "workspace_id",
                    "workspace_name",
                    "channel_id",
                    "channel_name",
                    "thread_id",
                    "thread_name",
                }:
                    continue
                setattr(record, field, value)
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise DeploymentConflict(
                    "This character is already deployed to the selected destination."
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
            scope = session.get(DiscordDeploymentScopeRecord, deployment_id)
            if scope is not None:
                session.delete(scope)
            session.delete(record)
            session.commit()
            return True

    def delete_owner(self, owner_id: str) -> dict[str, int]:
        """Delete all connector configuration owned by an account."""
        with self.database.session() as session:
            event_result = session.execute(
                delete(DiscordConnectorEventRecord).where(
                    DiscordConnectorEventRecord.owner_id == owner_id
                )
            )
            scope_result = session.execute(
                delete(DiscordDeploymentScopeRecord).where(
                    DiscordDeploymentScopeRecord.owner_id == owner_id
                )
            )
            deployment_result = session.execute(
                delete(CharacterDeploymentRecord).where(
                    CharacterDeploymentRecord.owner_id == owner_id
                )
            )
            profile_result = session.execute(
                delete(DiscordServerProfileRecord).where(
                    DiscordServerProfileRecord.owner_id == owner_id
                )
            )
            catalog_result = session.execute(
                delete(DiscordServerCatalogRecord).where(
                    DiscordServerCatalogRecord.owner_id == owner_id
                )
            )
            connection_result = session.execute(
                delete(PlatformConnectionRecord).where(
                    PlatformConnectionRecord.owner_id == owner_id
                )
            )
            session.commit()
        return {
            "discord_connector_events": int(getattr(event_result, "rowcount", 0) or 0),
            "deployment_scopes": int(getattr(scope_result, "rowcount", 0) or 0),
            "deployments": int(getattr(deployment_result, "rowcount", 0) or 0),
            "server_profiles": int(getattr(profile_result, "rowcount", 0) or 0),
            "server_catalogs": int(getattr(catalog_result, "rowcount", 0) or 0),
            "connections": int(getattr(connection_result, "rowcount", 0) or 0),
        }

    def claim_owner(self, source_owner_id: str, target_owner_id: str) -> dict[str, int]:
        """Move legacy local connector configuration into an authenticated workspace."""
        with self.database.session() as session:
            event_result = session.execute(
                update(DiscordConnectorEventRecord)
                .where(DiscordConnectorEventRecord.owner_id == source_owner_id)
                .values(owner_id=target_owner_id)
            )
            connection_result = session.execute(
                update(PlatformConnectionRecord)
                .where(PlatformConnectionRecord.owner_id == source_owner_id)
                .values(owner_id=target_owner_id)
            )
            catalog_result = session.execute(
                update(DiscordServerCatalogRecord)
                .where(DiscordServerCatalogRecord.owner_id == source_owner_id)
                .values(owner_id=target_owner_id)
            )
            profile_result = session.execute(
                update(DiscordServerProfileRecord)
                .where(DiscordServerProfileRecord.owner_id == source_owner_id)
                .values(owner_id=target_owner_id)
            )
            deployment_result = session.execute(
                update(CharacterDeploymentRecord)
                .where(CharacterDeploymentRecord.owner_id == source_owner_id)
                .values(owner_id=target_owner_id)
            )
            scope_result = session.execute(
                update(DiscordDeploymentScopeRecord)
                .where(DiscordDeploymentScopeRecord.owner_id == source_owner_id)
                .values(owner_id=target_owner_id)
            )
            session.commit()
        return {
            "discord_connector_events": int(getattr(event_result, "rowcount", 0) or 0),
            "connections": int(getattr(connection_result, "rowcount", 0) or 0),
            "server_catalogs": int(getattr(catalog_result, "rowcount", 0) or 0),
            "server_profiles": int(getattr(profile_result, "rowcount", 0) or 0),
            "deployments": int(getattr(deployment_result, "rowcount", 0) or 0),
            "deployment_scopes": int(getattr(scope_result, "rowcount", 0) or 0),
        }
