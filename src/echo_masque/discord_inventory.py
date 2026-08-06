"""Centralized ownership for the managed Discord Bot inventory."""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select, update

from echo_masque.persistence.database import Database
from echo_masque.persistence.deployment_models import (
    DiscordConnectorEventRecord,
    DiscordServerCatalogRecord,
    DiscordServerProfileRecord,
    PlatformConnectionRecord,
)


class DiscordInventoryService:
    """Keep managed Discord connections and catalogs owned by the Bootstrap Super Admin."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def centralize(self, super_admin_id: str) -> dict[str, int]:
        """Move managed Discord inventory without breaking user-owned workspaces.

        Platform connections, synchronized catalogs, and connector events become Super
        Admin-owned. Existing user Server Profiles, Character Deployments, and manual
        Expression definitions remain user-owned claims. A Super Admin profile is created
        for every synchronized Server so the complete inventory is visible there.
        """

        with self.database.session() as session:
            connection_ids = list(
                session.scalars(
                    select(PlatformConnectionRecord.id).where(
                        PlatformConnectionRecord.platform == "discord"
                    )
                )
            )
            if not connection_ids:
                return {
                    "connections": 0,
                    "catalogs": 0,
                    "events": 0,
                    "super_admin_profiles": 0,
                }

            connection_result = session.execute(
                update(PlatformConnectionRecord)
                .where(PlatformConnectionRecord.id.in_(connection_ids))
                .values(owner_id=super_admin_id)
            )
            catalog_result = session.execute(
                update(DiscordServerCatalogRecord)
                .where(DiscordServerCatalogRecord.connection_id.in_(connection_ids))
                .values(owner_id=super_admin_id)
            )
            event_result = session.execute(
                update(DiscordConnectorEventRecord)
                .where(DiscordConnectorEventRecord.connection_id.in_(connection_ids))
                .values(owner_id=super_admin_id)
            )

            created_profiles = 0
            catalogs = list(
                session.scalars(
                    select(DiscordServerCatalogRecord).where(
                        DiscordServerCatalogRecord.connection_id.in_(connection_ids)
                    )
                )
            )
            for catalog in catalogs:
                existing = session.scalar(
                    select(DiscordServerProfileRecord.id).where(
                        DiscordServerProfileRecord.owner_id == super_admin_id,
                        DiscordServerProfileRecord.connection_id == catalog.connection_id,
                        DiscordServerProfileRecord.guild_id == catalog.guild_id,
                    )
                )
                if existing is not None:
                    continue
                session.add(
                    DiscordServerProfileRecord(
                        id=str(uuid4()),
                        owner_id=super_admin_id,
                        connection_id=catalog.connection_id,
                        name=catalog.guild_name,
                        guild_id=catalog.guild_id,
                        guild_name=catalog.guild_name,
                        channel_scope_mode="all_except",
                        excluded_channel_ids_json="[]",
                        excluded_category_ids_json="[]",
                        thread_policy="inherit_parent",
                    )
                )
                created_profiles += 1

            session.commit()
            return {
                "connections": int(getattr(connection_result, "rowcount", 0) or 0),
                "catalogs": int(getattr(catalog_result, "rowcount", 0) or 0),
                "events": int(getattr(event_result, "rowcount", 0) or 0),
                "super_admin_profiles": created_profiles,
            }
