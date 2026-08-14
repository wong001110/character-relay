from pathlib import Path

from echo_masque.api.smart_participation_v4_schemas import (
    SmartParticipationBurstMessage,
    SmartParticipationResolveCandidate,
    SmartParticipationResolveRequest,
)
from echo_masque.conversation_graph_topic_shadow import ConversationGraphTopicShadowService
from echo_masque.persistence import Database
from echo_masque.persistence.conversation_graph_repository import (
    ConversationGraphRepository,
    ConversationGraphScope,
)
from echo_masque.persistence.conversation_topic_repository import ConversationTopicRepository


def repositories(
    tmp_path: Path,
) -> tuple[ConversationGraphRepository, ConversationTopicRepository]:
    database = Database(f"sqlite:///{tmp_path / 'topic-shadow.db'}")
    database.initialize()
    return ConversationGraphRepository(database), ConversationTopicRepository(database)


def payload() -> SmartParticipationResolveRequest:
    return SmartParticipationResolveRequest(
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="channel-1",
        thread_id="thread-1",
        message_id="message-2",
        author_id="user-2",
        burst_id="burst-1",
        burst_messages=[
            SmartParticipationBurstMessage(
                message_id="message-1",
                author_id="user-1",
                author_display_name="Alice",
                text="first",
            ),
            SmartParticipationBurstMessage(
                message_id="message-2",
                author_id="user-2",
                author_display_name="Bob",
                text="second",
            ),
        ],
        candidates=[SmartParticipationResolveCandidate(deployment_id="deployment-ann")],
    )


def create_topic(repository: ConversationTopicRepository, owner_id: str, label: str) -> str:
    record = repository.create(
        owner_id=owner_id,
        platform="discord",
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="channel-1",
        thread_id="thread-1",
        topic_label=label,
        summary="authoritative summary stays in Topic Memory",
        keywords_json="[]",
        open_loops_json="[]",
        pending_actions_json="[]",
        participants_json="[]",
        last_message_id="message-1",
    )
    return record.id


def test_active_topic_is_projected_only_into_owner_private_overlay(tmp_path: Path) -> None:
    graph, topics = repositories(tmp_path)
    topic_id = create_topic(topics, "owner-1", "Photography")
    observer = ConversationGraphTopicShadowService(graph, topics)

    result = observer.observe(payload(), owner_ids=["owner-1", "owner-1"])

    assert result.observed is True
    assert result.owner_count == 1
    assert result.topic_count == 1
    assert result.node_count == 2
    assert result.edge_count == 1

    private_scope = ConversationGraphScope(
        scope_owner_id="owner-1",
        platform="discord",
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="channel-1",
        thread_id="thread-1",
    )
    topic_node = graph.upsert_node(
        scope=private_scope,
        node_type="Topic",
        canonical_key=f"topic:{topic_id}",
    )
    neighbors = graph.neighbors(
        scope=private_scope,
        node_id=topic_node.id,
        relations=("ACTIVE_IN_BURST",),
    )
    assert len(neighbors) == 1
    assert neighbors[0].node.node_type == "ConversationBurst"
    assert neighbors[0].edge.source_type == "topic_memory"
    assert neighbors[0].edge.source_burst_id == "burst-1"

    public_scope = ConversationGraphScope(
        platform="discord",
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="channel-1",
        thread_id="thread-1",
    )
    assert graph.get_node(topic_node.id, scope=public_scope) is None


def test_each_owner_reads_only_its_own_authoritative_topic(tmp_path: Path) -> None:
    graph, topics = repositories(tmp_path)
    create_topic(topics, "owner-1", "Photography")
    create_topic(topics, "owner-2", "Deployment")
    observer = ConversationGraphTopicShadowService(graph, topics)

    result = observer.observe(payload(), owner_ids=["owner-1", "owner-2"])

    assert result.observed is True
    assert result.owner_count == 2
    assert result.topic_count == 2
    assert result.node_count == 4
    assert result.edge_count == 2


def test_no_active_topic_creates_no_private_overlay(tmp_path: Path) -> None:
    graph, topics = repositories(tmp_path)
    observer = ConversationGraphTopicShadowService(graph, topics)

    result = observer.observe(payload(), owner_ids=["owner-1"])

    assert result.observed is False
    assert result.owner_count == 0
    assert result.topic_count == 0
    assert result.node_count == 0
    assert result.edge_count == 0
