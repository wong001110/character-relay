from echo_masque.api.connector_schemas import DiscordInboundMessage
from echo_masque.conversation_episode import ConversationEpisodeProjectionService
from echo_masque.persistence.conversation_episode_repository import ConversationEpisodeRepository
from echo_masque.persistence.database import Database


def test_episode_projection_keeps_source_refs_not_duplicate_transcript() -> None:
    database = Database("sqlite://")
    database.initialize()
    repository = ConversationEpisodeRepository(database)
    service = ConversationEpisodeProjectionService(repository)
    payload = DiscordInboundMessage(
        connection_id="connection-1",
        deployment_id="ann",
        message_id="m3",
        guild_id="guild-1",
        channel_id="general",
        author_id="user-1",
        author_display_name="Juen",
        text="讨论这个反派是不是她。",
        conversation_burst_id="burst-1",
        burst_source_message_ids=["m1", "m2", "m3"],
    )

    service.observe(owner_id="owner-1", payload=payload, topic_id="topic-1")
    rows = repository.recent_for_scope(
        owner_id="owner-1",
        platform="discord",
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="general",
        thread_id="",
    )
    assert len(rows) == 1
    row = rows[0]
    assert row.topic_id == "topic-1"
    assert row.source_count == 3
    assert "m1" in row.source_message_ids_json
    assert len(row.summary) < 800


def test_episode_projection_is_discord_server_isolated() -> None:
    database = Database("sqlite://")
    database.initialize()
    service = ConversationEpisodeProjectionService(ConversationEpisodeRepository(database))
    for guild_id, message_id in (("guild-a", "a1"), ("guild-b", "b1")):
        service.observe(
            owner_id="owner-1",
            payload=DiscordInboundMessage(
                connection_id="connection-1",
                deployment_id="ann",
                message_id=message_id,
                guild_id=guild_id,
                channel_id="general",
                author_id="user-1",
                author_display_name="Juen",
                text="same words",
                conversation_burst_id="same-burst-label",
            ),
            topic_id="topic-1",
        )
    repository = service.repository
    guild_a = repository.recent_for_scope(
        owner_id="owner-1",
        platform="discord",
        connection_id="connection-1",
        guild_id="guild-a",
        channel_id="general",
        thread_id="",
    )
    guild_b = repository.recent_for_scope(
        owner_id="owner-1",
        platform="discord",
        connection_id="connection-1",
        guild_id="guild-b",
        channel_id="general",
        thread_id="",
    )
    assert len(guild_a) == 1
    assert len(guild_b) == 1
    assert guild_a[0].id != guild_b[0].id
