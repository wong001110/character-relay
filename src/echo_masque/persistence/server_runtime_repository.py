"""Persistence access for Discord Server runtime settings."""

from sqlalchemy import select, update

from echo_masque.persistence.database import Database
from echo_masque.persistence.deployment_models import DiscordServerProfileRecord
from echo_masque.persistence.server_runtime_models import (
    DiscordServerRuntimeRecord,
    ServerRuntimeMigrationRecord,
)
from echo_masque.server_time import DEFAULT_SERVER_TIMEZONE, validate_timezone

_LEGACY_UTC_MIGRATION = "default-timezone-malaysia-v1"


class ServerRuntimeRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def migrate_legacy_utc_defaults(self) -> int:
        """Convert UTC values written by the former default exactly once.

        A marker prevents a later intentional UTC choice from being changed on future starts.
        """

        with self.database.session() as session:
            if session.get(ServerRuntimeMigrationRecord, _LEGACY_UTC_MIGRATION) is not None:
                return 0
            result = session.execute(
                update(DiscordServerRuntimeRecord)
                .where(DiscordServerRuntimeRecord.timezone == "UTC")
                .values(timezone=DEFAULT_SERVER_TIMEZONE)
            )
            session.add(ServerRuntimeMigrationRecord(id=_LEGACY_UTC_MIGRATION))
            session.commit()
            return int(getattr(result, "rowcount", 0) or 0)

    def get_timezone(
        self,
        *,
        profile_id: str,
        owner_id: str,
        default_timezone: str = DEFAULT_SERVER_TIMEZONE,
    ) -> str | None:
        fallback = validate_timezone(default_timezone)
        with self.database.session() as session:
            profile = session.get(DiscordServerProfileRecord, profile_id)
            if profile is None or profile.owner_id != owner_id:
                return None
            runtime = session.get(DiscordServerRuntimeRecord, profile_id)
            if runtime is None:
                return fallback
            try:
                return validate_timezone(runtime.timezone)
            except ValueError:
                return fallback

    def set_timezone(
        self,
        *,
        profile_id: str,
        owner_id: str,
        timezone: str,
    ) -> DiscordServerRuntimeRecord | None:
        normalized = validate_timezone(timezone)
        with self.database.session() as session:
            profile = session.get(DiscordServerProfileRecord, profile_id)
            if profile is None or profile.owner_id != owner_id:
                return None
            runtime = session.get(DiscordServerRuntimeRecord, profile_id)
            if runtime is None:
                runtime = DiscordServerRuntimeRecord(
                    profile_id=profile_id,
                    owner_id=owner_id,
                    timezone=normalized,
                )
                session.add(runtime)
            else:
                runtime.timezone = normalized
            session.commit()
            session.refresh(runtime)
            return runtime

    def resolve_timezone(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        default_timezone: str = DEFAULT_SERVER_TIMEZONE,
    ) -> str:
        fallback = validate_timezone(default_timezone)
        if not guild_id:
            return fallback
        with self.database.session() as session:
            profile = session.scalar(
                select(DiscordServerProfileRecord).where(
                    DiscordServerProfileRecord.owner_id == owner_id,
                    DiscordServerProfileRecord.connection_id == connection_id,
                    DiscordServerProfileRecord.guild_id == guild_id,
                )
            )
            if profile is None:
                return fallback
            runtime = session.get(DiscordServerRuntimeRecord, profile.id)
            if runtime is None:
                return fallback
            try:
                return validate_timezone(runtime.timezone)
            except ValueError:
                return fallback


__all__ = ["ServerRuntimeRepository"]
