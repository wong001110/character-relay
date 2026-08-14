from __future__ import annotations

from pathlib import Path

from echo_masque.api.smart_participation_v4_schemas import (
    SmartParticipationBurstMessage,
    SmartParticipationResolveCandidate,
    SmartParticipationResolveRequest,
)
from echo_masque.conversation_graph_shadow import ConversationGraphShadowService
from echo_masque.persistence import Database
from echo_masque.persistence.conversation_graph_repository import (
    ConversationGraphRepository,
    ConversationGraphScope,
)


def graph(tmp_path: Path) -> tuple[ConversationGraphRepository, ConversationGraphShadowService]:
    database = Database(f"sqlite:///{tmp_path / 'shadow.db'}")
    database.initialize()
    repository = ConversationGraphRepository(database)
    return repository, ConversationGraphShadowService(repository)


def scope() -> ConversationGraphScope:
    return ConversationGraphScope(
        scope_owner_id="",
        platform="discord",
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="channel-1",
        thread_id="",
    )


def test_shadow_observer_records_only_direct_actor_burst_evidence(tmp_path: Path) -> None:
    repository, observer = graph(tmp_path)
    payload = SmartParticipationResolveRequest(
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="channel-1",
        message_id="message-3",
        author_id="user-a",
        burst_id="burst-123",
        burst_messages=[
            SmartParticipationBurstMessage(
                message_id="message-1",
                author_id="user-a",
                author_display_name="Alice",
                text="first fragment",
            ),
            SmartParticipationBurstMessage(
                message_id="message-2",
                author_id="user-b",
                author_display_name="Bob",
                text="reply fragment",
            ),
            SmartParticipationBurstMessage(
                message_id="message-3",
                author_id="user-a",
                author_display_name="Alice",
                text="last fragment",
            ),
        ],
        candidates=[SmartParticipationResolveCandidate(deployment_id="ann")],
    )

    result = observer.observe(payload)

    assert result.observed is True
    assert result.burst_id == "burst-123"
    assert result.node_count == 3  # one Burst + two distinct Actors
    assert result.edge_count == 2

    burst = repository.upsert_node(
        scope=scope(),
        node_type="ConversationBurst",
        canonical_key="burst:burst-123",
    )
    alice = repository.upsert_node(
        scope=scope(),
        node_type="Actor",
        canonical_key="actor:user-a",
    )
    bob = repository.upsert_node(
        scope=scope(),
        node_type="Actor",
        canonical_key="actor:user-b",
    )
    alice_edges = repository.neighbors(
        scope=scope(),
        node_id=alice.id,
        relations=("PARTICIPATED_IN",),
    )
    bob_edges = repository.neighbors(
        scope=scope(),
        node_id=bob.id,
        relations=("PARTICIPATED_IN",),
    )

    assert len(alice_edges) == 1
    assert alice_edges[0].node.id == burst.id
    assert alice_edges[0].edge.source_message_id == "message-1"
    assert alice_edges[0].edge.source_burst_id == "burst-123"
    assert len(bob_edges) == 1
    assert bob_edges[0].node.id == burst.id
    assert bob_edges[0].edge.source_message_id == "message-2"


def test_shadow_observer_generates_stable_burst_id_without_copying_message_text(tmp_path: Path) -> None:
    repository, observer = graph(tmp_path)
    payload = SmartParticipationResolveRequest(
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="channel-1",
        message_id="message-1",
        author_id="user-a",
        message="sensitive but public chat text should not be duplicated into graph summary",
        candidates=[SmartParticipationResolveCandidate(deployment_id="ann")],
    )

    first = observer.observe(payload)
    second = observer.observe(payload)

    assert first.burst_id == second.burst_id
    assert first.node_count == 2
    assert second.node_count == 2
    burst = repository.upsert_node(
        scope=scope(),
        node_type="ConversationBurst",
        canonical_key=f"burst:{first.burst_id}",
    )
    assert burst.summary == ""
    assert "sensitive but public" not in burst.payload_json


def test_shadow_observer_skips_unscoped_messages(tmp_path: Path) -> None:
    _repository, observer = graph(tmp_path)
    payload = SmartParticipationResolveRequest(
        connection_id="connection-1",
        message="no channel scope",
        candidates=[SmartParticipationResolveCandidate(deployment_id="ann")],
    )

    result = observer.observe(payload)

    assert result.observed is False
    assert result.node_count == 0
    assert result.edge_count == 0
