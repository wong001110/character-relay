"""Persistence helpers for account access to managed Discord servers."""

from __future__ import annotations

import secrets
from uuid import uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from echo_masque.persistence.database import Database
from echo_masque.persistence.deployment_models import (
    DiscordServerCatalogRecord,
    DiscordServerProfileRecord,
)
from echo_masque.persistence.models import UserRecord
from echo_masque.persistence.server_access_models import (
    DiscordServerAccessRecord,
    DiscordServerJoinConfigRecord,
)

_JOIN_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"


def _join_code() -> str:
    return "CR-" + "".join(secrets.choice(_JOIN_ALPHABET) for _ in range(8))


class ServerAccessRepository:
    """Keep join-code and account-to-server access state behind one boundary."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def ensure_join_config(
        self,
        *,
        connection_id: str,
        guild_id: str,
    ) -> DiscordServerJoinConfigRecord:
        with self.database.session() as session:
            existing = session.scalar(
                select(DiscordServerJoinConfigRecord).where(
                    DiscordServerJoinConfigRecord.connection_id == connection_id,
                    DiscordServerJoinConfigRecord.guild_id == guild_id,
                )
            )
            if existing is not None:
                return existing

        for _ in range(12):
            record = DiscordServerJoinConfigRecord(
                id=str(uuid4()),
                connection_id=connection_id,
                guild_id=guild_id,
                join_code=_join_code(),
                join_enabled=True,
            )
            with self.database.session() as session:
                session.add(record)
                try:
                    session.commit()
                except IntegrityError:
                    session.rollback()
                    existing = session.scalar(
                        select(DiscordServerJoinConfigRecord).where(
                            DiscordServerJoinConfigRecord.connection_id == connection_id,
                            DiscordServerJoinConfigRecord.guild_id == guild_id,
                        )
                    )
                    if existing is not None:
                        return existing
                    continue
                session.refresh(record)
                return record
        raise RuntimeError("Could not allocate a unique Discord server join code.")

    def get_join_config_by_code(self, code: str) -> DiscordServerJoinConfigRecord | None:
        normalized = code.strip().upper()
        if not normalized:
            return None
        with self.database.session() as session:
            return session.scalar(
                select(DiscordServerJoinConfigRecord).where(
                    func.upper(DiscordServerJoinConfigRecord.join_code) == normalized
                )
            )

    def set_join_enabled(
        self,
        *,
        connection_id: str,
        guild_id: str,
        enabled: bool,
    ) -> DiscordServerJoinConfigRecord | None:
        with self.database.session() as session:
            record = session.scalar(
                select(DiscordServerJoinConfigRecord).where(
                    DiscordServerJoinConfigRecord.connection_id == connection_id,
                    DiscordServerJoinConfigRecord.guild_id == guild_id,
                )
            )
            if record is None:
                return None
            record.join_enabled = enabled
            session.commit()
            session.refresh(record)
            return record

    def regenerate_join_code(
        self,
        *,
        connection_id: str,
        guild_id: str,
    ) -> DiscordServerJoinConfigRecord | None:
        for _ in range(12):
            with self.database.session() as session:
                record = session.scalar(
                    select(DiscordServerJoinConfigRecord).where(
                        DiscordServerJoinConfigRecord.connection_id == connection_id,
                        DiscordServerJoinConfigRecord.guild_id == guild_id,
                    )
                )
                if record is None:
                    return None
                record.join_code = _join_code()
                try:
                    session.commit()
                except IntegrityError:
                    session.rollback()
                    continue
                session.refresh(record)
                return record
        raise RuntimeError("Could not allocate a unique Discord server join code.")

    def get_catalog_server(
        self,
        *,
        catalog_owner_id: str,
        connection_id: str,
        guild_id: str,
    ) -> DiscordServerCatalogRecord | None:
        with self.database.session() as session:
            return session.scalar(
                select(DiscordServerCatalogRecord)
                .where(
                    DiscordServerCatalogRecord.owner_id == catalog_owner_id,
                    DiscordServerCatalogRecord.connection_id == connection_id,
                    DiscordServerCatalogRecord.guild_id == guild_id,
                )
                .limit(1)
            )

    def grant_access(
        self,
        *,
        user_id: str,
        connection_id: str,
        guild_id: str,
        source: str,
    ) -> DiscordServerAccessRecord:
        with self.database.session() as session:
            existing = session.scalar(
                select(DiscordServerAccessRecord).where(
                    DiscordServerAccessRecord.user_id == user_id,
                    DiscordServerAccessRecord.connection_id == connection_id,
                    DiscordServerAccessRecord.guild_id == guild_id,
                )
            )
            if existing is not None:
                return existing
            record = DiscordServerAccessRecord(
                id=str(uuid4()),
                user_id=user_id,
                connection_id=connection_id,
                guild_id=guild_id,
                access_source=source,
            )
            session.add(record)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                existing = session.scalar(
                    select(DiscordServerAccessRecord).where(
                        DiscordServerAccessRecord.user_id == user_id,
                        DiscordServerAccessRecord.connection_id == connection_id,
                        DiscordServerAccessRecord.guild_id == guild_id,
                    )
                )
                if existing is None:
                    raise
                return existing
            session.refresh(record)
            return record

    def revoke_access(
        self,
        *,
        user_id: str,
        connection_id: str,
        guild_id: str,
    ) -> bool:
        with self.database.session() as session:
            record_id = session.scalar(
                select(DiscordServerAccessRecord.id).where(
                    DiscordServerAccessRecord.user_id == user_id,
                    DiscordServerAccessRecord.connection_id == connection_id,
                    DiscordServerAccessRecord.guild_id == guild_id,
                )
            )
            if record_id is None:
                return False
            session.execute(
                delete(DiscordServerAccessRecord).where(
                    DiscordServerAccessRecord.id == record_id
                )
            )
            session.commit()
            return True

    def list_user_access(self, user_id: str) -> list[DiscordServerAccessRecord]:
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(DiscordServerAccessRecord)
                    .where(DiscordServerAccessRecord.user_id == user_id)
                    .order_by(DiscordServerAccessRecord.created_at)
                )
            )

    def list_server_members(
        self,
        *,
        connection_id: str,
        guild_id: str,
        exclude_user_id: str | None = None,
    ) -> list[tuple[DiscordServerAccessRecord, UserRecord]]:
        with self.database.session() as session:
            query = (
                select(DiscordServerAccessRecord, UserRecord)
                .join(UserRecord, UserRecord.id == DiscordServerAccessRecord.user_id)
                .where(
                    DiscordServerAccessRecord.connection_id == connection_id,
                    DiscordServerAccessRecord.guild_id == guild_id,
                )
                .order_by(UserRecord.display_name, UserRecord.email)
            )
            if exclude_user_id is not None:
                query = query.where(DiscordServerAccessRecord.user_id != exclude_user_id)
            return [(access, user) for access, user in session.execute(query).all()]

    def ensure_profile_for_access(
        self,
        *,
        user_id: str,
        catalog: DiscordServerCatalogRecord,
    ) -> tuple[DiscordServerProfileRecord, bool]:
        """Create the legacy owner-scoped profile required by the current Deployment UI.

        Access is shared independently. The profile is retained as a compatibility bridge until
        Deployment ownership is migrated to a server workspace model.
        """

        with self.database.session() as session:
            existing = session.scalar(
                select(DiscordServerProfileRecord).where(
                    DiscordServerProfileRecord.owner_id == user_id,
                    DiscordServerProfileRecord.connection_id == catalog.connection_id,
                    DiscordServerProfileRecord.guild_id == catalog.guild_id,
                )
            )
            if existing is not None:
                return existing, False
            record = DiscordServerProfileRecord(
                id=str(uuid4()),
                owner_id=user_id,
                connection_id=catalog.connection_id,
                name=catalog.guild_name,
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
            except IntegrityError:
                session.rollback()
                existing = session.scalar(
                    select(DiscordServerProfileRecord).where(
                        DiscordServerProfileRecord.owner_id == user_id,
                        DiscordServerProfileRecord.connection_id == catalog.connection_id,
                        DiscordServerProfileRecord.guild_id == catalog.guild_id,
                    )
                )
                if existing is None:
                    raise
                return existing, False
            session.refresh(record)
            return record, True

    def find_profile_for_access(
        self,
        *,
        user_id: str,
        connection_id: str,
        guild_id: str,
    ) -> DiscordServerProfileRecord | None:
        with self.database.session() as session:
            return session.scalar(
                select(DiscordServerProfileRecord).where(
                    DiscordServerProfileRecord.owner_id == user_id,
                    DiscordServerProfileRecord.connection_id == connection_id,
                    DiscordServerProfileRecord.guild_id == guild_id,
                )
            )

    def backfill_access_from_profiles(
        self,
        *,
        catalog_owner_id: str,
        user_id: str | None = None,
    ) -> int:
        """Preserve access for Server Profile claims created before join codes."""

        with self.database.session() as session:
            query = (
                select(DiscordServerProfileRecord)
                .join(
                    DiscordServerCatalogRecord,
                    (
                        DiscordServerCatalogRecord.connection_id
                        == DiscordServerProfileRecord.connection_id
                    )
                    & (
                        DiscordServerCatalogRecord.guild_id
                        == DiscordServerProfileRecord.guild_id
                    ),
                )
                .where(
                    DiscordServerCatalogRecord.owner_id == catalog_owner_id,
                    DiscordServerProfileRecord.owner_id != catalog_owner_id,
                )
            )
            if user_id is not None:
                query = query.where(DiscordServerProfileRecord.owner_id == user_id)
            profiles = list(session.scalars(query))

        created = 0
        for profile in profiles:
            before = self.list_user_access(profile.owner_id)
            known = any(
                item.connection_id == profile.connection_id and item.guild_id == profile.guild_id
                for item in before
            )
            if known:
                continue
            self.grant_access(
                user_id=profile.owner_id,
                connection_id=profile.connection_id,
                guild_id=profile.guild_id,
                source="legacy_claim",
            )
            created += 1
        return created
