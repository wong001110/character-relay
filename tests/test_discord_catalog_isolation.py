import pytest
from pydantic import ValidationError
from sqlalchemy import select

from echo_masque.api.connector_schemas import DiscordCatalogServer, DiscordServerCatalogSync
from echo_masque.persistence.database import Database
from echo_masque.persistence.deployment_repository import DeploymentRepository, decode_channels
from echo_masque.persistence.expression_models import DiscordExpressionSemanticRecord
from echo_masque.persistence.expression_repository import ExpressionRepository


def _connection(repository: DeploymentRepository) -> str:
    return repository.create_connection(
        owner_id="owner-1",
        platform="discord",
        display_name="Discord",
        connection_mode="managed",
        external_account_id="bot-1",
        status="connected",
        metadata={},
    ).id


def _server(guild_id: str, channel_id: str) -> tuple[str, str, list[dict[str, object]]]:
    return (
        guild_id,
        f"Guild {guild_id}",
        [
            {
                "id": channel_id,
                "name": channel_id,
                "category_id": "",
                "category_name": "",
                "type": "text",
            }
        ],
    )


def test_catalog_failure_preserves_failed_guild_and_deletes_only_left_guild() -> None:
    database = Database("sqlite://")
    database.initialize()
    deployments = DeploymentRepository(database)
    connection_id = _connection(deployments)
    deployments.sync_discord_server_catalog(
        connection_id=connection_id,
        visible_guild_ids=["guild-a", "guild-b", "guild-c"],
        failed_guild_ids=[],
        servers=[
            _server("guild-a", "a-before"),
            _server("guild-b", "b-before"),
            _server("guild-c", "c-before"),
        ],
    )

    deployments.sync_discord_server_catalog(
        connection_id=connection_id,
        visible_guild_ids=["guild-a", "guild-b", "guild-c"],
        failed_guild_ids=["guild-b"],
        servers=[_server("guild-a", "a-after"), _server("guild-c", "c-after")],
    )
    after_failure = {
        item.guild_id: decode_channels(item.channels_json)
        for item in deployments.list_discord_server_catalog("owner-1", connection_id=connection_id)
    }
    assert after_failure["guild-a"][0]["id"] == "a-after"
    assert after_failure["guild-b"][0]["id"] == "b-before"
    assert after_failure["guild-c"][0]["id"] == "c-after"

    deployments.sync_discord_server_catalog(
        connection_id=connection_id,
        visible_guild_ids=["guild-a", "guild-c"],
        failed_guild_ids=[],
        servers=[_server("guild-a", "a-after"), _server("guild-c", "c-after")],
    )
    assert [
        item.guild_id
        for item in deployments.list_discord_server_catalog("owner-1", connection_id=connection_id)
    ] == ["guild-a", "guild-c"]


def test_partial_media_sync_preserves_failed_inventory_and_applies_successful_empty_snapshot(
) -> None:
    database = Database("sqlite://")
    database.initialize()
    deployments = DeploymentRepository(database)
    connection_id = _connection(deployments)
    expressions = ExpressionRepository(database)
    expressions.sync_server_resources(
        connection_id=connection_id,
        guild_id="guild-media",
        emojis=[
            {
                "emoji_id": "emoji-1",
                "name": "wave",
                "animated": False,
                "available": True,
                "asset_url": "https://cdn.example/wave.png",
            }
        ],
        stickers=[
            {
                "sticker_id": "sticker-1",
                "name": "wave",
                "format_type": "png",
                "asset_url": "https://cdn.example/wave.png",
            }
        ],
    )

    expressions.sync_server_resources(
        connection_id=connection_id,
        guild_id="guild-media",
        emojis=None,
        stickers=[],
    )

    with database.session() as session:
        records = {
            item.resource_type: item
            for item in session.scalars(
                select(DiscordExpressionSemanticRecord).where(
                    DiscordExpressionSemanticRecord.connection_id == connection_id
                )
            )
        }
    assert records["emoji"].available is True
    assert records["sticker"].available is False


def test_catalog_schema_rejects_overlapping_or_invisible_failure_partitions() -> None:
    with pytest.raises(ValidationError, match="subset"):
        DiscordServerCatalogSync(
            connection_id="connection-1",
            visible_guild_ids=["guild-a"],
            failed_guild_ids=["guild-b"],
            servers=[],
        )
    with pytest.raises(ValidationError, match="both successful and failed"):
        DiscordServerCatalogSync(
            connection_id="connection-1",
            visible_guild_ids=["guild-a"],
            failed_guild_ids=["guild-a"],
            servers=[
                DiscordCatalogServer(
                    guild_id="guild-a",
                    guild_name="Guild A",
                    channels=[],
                )
            ],
        )
