from echo_masque.persistence.auth_repository import AuthRepository
from echo_masque.persistence.database import Database
from echo_masque.persistence.deployment_repository import DeploymentRepository
from echo_masque.persistence.server_access_repository import ServerAccessRepository


def build_database(tmp_path) -> Database:
    database = Database(f"sqlite:///{tmp_path / 'server-access.db'}")
    database.initialize()
    return database


def seed_server(database: Database):
    auth = AuthRepository(database)
    admin = auth.create_user(
        email="admin@example.com",
        display_name="Admin",
        password_hash="hash",
        role="admin",
    )
    member = auth.create_user(
        email="member@example.com",
        display_name="Member",
        password_hash="hash",
    )
    deployments = DeploymentRepository(database)
    connection = deployments.create_connection(
        owner_id=admin.id,
        platform="discord",
        display_name="Character Relay Discord Bot",
        connection_mode="managed",
        external_account_id="bot",
        status="connected",
        metadata={},
    )
    catalog = deployments.sync_discord_server_catalog(
        connection_id=connection.id,
        servers=[("guild-1", "Notebook Club", [])],
    )[0]
    return admin, member, connection, catalog


def test_join_config_can_be_regenerated_and_disabled(tmp_path) -> None:
    database = build_database(tmp_path)
    _, _, connection, catalog = seed_server(database)
    access = ServerAccessRepository(database)

    config = access.ensure_join_config(
        connection_id=connection.id,
        guild_id=catalog.guild_id,
    )

    assert config.join_code.startswith("CR-")
    assert len(config.join_code) == 11
    assert access.get_join_config_by_code(config.join_code.lower()) is not None

    regenerated = access.regenerate_join_code(
        connection_id=connection.id,
        guild_id=catalog.guild_id,
    )
    assert regenerated is not None
    assert regenerated.join_code != config.join_code

    disabled = access.set_join_enabled(
        connection_id=connection.id,
        guild_id=catalog.guild_id,
        enabled=False,
    )
    assert disabled is not None
    assert disabled.join_enabled is False


def test_access_grant_creates_compatibility_profile_and_member_listing(tmp_path) -> None:
    database = build_database(tmp_path)
    admin, member, connection, catalog = seed_server(database)
    access = ServerAccessRepository(database)

    grant = access.grant_access(
        user_id=member.id,
        connection_id=connection.id,
        guild_id=catalog.guild_id,
        source="join_code",
    )
    repeated = access.grant_access(
        user_id=member.id,
        connection_id=connection.id,
        guild_id=catalog.guild_id,
        source="join_code",
    )
    profile, created = access.ensure_profile_for_access(
        user_id=member.id,
        catalog=catalog,
    )
    same_profile, created_again = access.ensure_profile_for_access(
        user_id=member.id,
        catalog=catalog,
    )

    assert repeated.id == grant.id
    assert created is True
    assert created_again is False
    assert same_profile.id == profile.id
    assert profile.owner_id == member.id
    assert profile.connection_id == connection.id
    assert profile.guild_id == catalog.guild_id

    members = access.list_server_members(
        connection_id=connection.id,
        guild_id=catalog.guild_id,
        exclude_user_id=admin.id,
    )
    assert [(item.user_id, user.id) for item, user in members] == [(member.id, member.id)]

    assert access.revoke_access(
        user_id=member.id,
        connection_id=connection.id,
        guild_id=catalog.guild_id,
    )
    assert access.list_user_access(member.id) == []
