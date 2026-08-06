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
from echo_masque.persistence.expression_models import DiscordExpressionSemanticRecord


class DiscordInventoryService:
    """Keep managed Discord connections and catalogs owned by the Bootstrap Super Admin."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def centralize(self, super_admin_id: str) -> dict[str, int]:
        """Move managed Discord inventory without breaking user-owned workspace profiles.

        Platform connections, synchronized catalogs, connector events, and the canonical
        expression catalog become Super Admin-owned. Existing user Server Profiles and
        Character Deployments remain user-owned claims so deployed characters continue
        to work. A Super Admin profile is created for each synchronized Server.
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
                    "expressions": 0,
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

            expression_result = session.execute(
                update(DiscordExpressionSemanticRecord)
                .where(
                    DiscordExpressionSemanticRecord.connection_id.in_(connection_ids),
                    DiscordExpressionSemanticRecord.owner_id.not_in(
                        select(DiscordServerProfileRecord.owner_id).where(
                            DiscordServerProfileRecord.connection_id
                            == DiscordExpressionSemanticRecord.connection_id,
                            DiscordServerProfileRecord.guild_id
                            == DiscordExpressionSemanticRecord.guild_id,
                        )
                    ),
                )
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
                "expressions": int(getattr(expression_result, "rowcount", 0) or 0),
                "super_admin_profiles": created_profiles,
            }
