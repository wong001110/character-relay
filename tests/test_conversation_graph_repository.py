from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from echo_masque.persistence import Database
from echo_masque.persistence.conversation_graph_repository import (
    ConversationGraphRepository,
    ConversationGraphScope,
)


def repository(tmp_path: Path) -> ConversationGraphRepository:
    database = Database(f"sqlite:///{tmp_path / 'conversation-graph.db'}")
    database.initialize()
    return ConversationGraphRepository(database)


def scope(*, owner: str = "", channel: str = "channel-1") -> ConversationGraphScope:
    return ConversationGraphScope(
        scope_owner_id=owner,
        platform="discord",
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id=channel,
        thread_id="thread-1",
    )


def test_graph_nodes_are_idempotent_inside_scope_and_isolated_across_private_overlay(
    tmp_path: Path,
) -> None:
    graph = repository(tmp_path)
    public = scope()
    private = scope(owner="owner-1")

    first = graph.upsert_node(
        scope=public,
        node_type="Topic",
        canonical_key=" Photography ",
        label="Photography",
    )
    second = graph.upsert_node(
        scope=public,
        node_type="Topic",
        canonical_key="photography",
        label="Photography updated",
    )
    private_node = graph.upsert_node(
        scope=private,
        node_type="Topic",
        canonical_key="photography",
        label="Private Photography",
    )

    assert first.id == second.id
    assert second.label == "Photography updated"
    assert private_node.id != first.id
    assert graph.get_node(first.id, scope=private) is None
    assert graph.get_node(private_node.id, scope=public) is None


def test_edge_upsert_keeps_bounded_provenance_and_evidence_counts(tmp_path: Path) -> None:
    graph = repository(tmp_path)
    graph_scope = scope()
    character = graph.upsert_node(
        scope=graph_scope,
        node_type="Character",
        canonical_key="character:ning",
        label="Ning",
    )
    topic = graph.upsert_node(
        scope=graph_scope,
        node_type="Topic",
        canonical_key="photography",
        label="Photography",
    )

    edge_id = ""
    for index in range(10):
        edge = graph.upsert_edge(
            scope=graph_scope,
            source_node_id=character.id,
            relation="PARTICIPATED_IN",
            target_node_id=topic.id,
            confidence=0.5 + index / 100,
            source_message_id=f"message-{index}",
            source_burst_id="burst-1",
            provenance={"message_id": f"message-{index}", "kind": "observed"},
        )
        edge_id = edge.id
    negative = graph.upsert_edge(
        scope=graph_scope,
        source_node_id=character.id,
        relation="PARTICIPATED_IN",
        target_node_id=topic.id,
        confidence=0.42,
        negative_evidence=True,
        provenance={"message_id": "message-silent", "kind": "eligible_silent"},
    )

    assert negative.id == edge_id
    assert negative.evidence_count == 10
    assert negative.negative_evidence_count == 1
    assert negative.confidence == 0.42
    provenance = json.loads(negative.provenance_json)
    assert isinstance(provenance, list)
    assert len(provenance) == 8
    assert provenance[-1]["message_id"] == "message-silent"

    neighbors = graph.neighbors(
        scope=graph_scope,
        node_id=character.id,
        relations=("PARTICIPATED_IN",),
    )
    assert len(neighbors) == 1
    assert neighbors[0].node.id == topic.id
    assert neighbors[0].edge.id == negative.id


def test_graph_rejects_cross_scope_edges(tmp_path: Path) -> None:
    graph = repository(tmp_path)
    public = scope()
    private = scope(owner="owner-1")
    public_character = graph.upsert_node(
        scope=public,
        node_type="Character",
        canonical_key="character:ann",
    )
    private_topic = graph.upsert_node(
        scope=private,
        node_type="Topic",
        canonical_key="private-topic",
    )

    with pytest.raises(ValueError, match="cannot cross graph scopes"):
        graph.upsert_edge(
            scope=public,
            source_node_id=public_character.id,
            relation="RELATED_TO",
            target_node_id=private_topic.id,
            confidence=0.8,
        )


def test_expired_graph_state_is_hidden_then_cleaned(tmp_path: Path) -> None:
    graph = repository(tmp_path)
    graph_scope = scope()
    now = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)
    character = graph.upsert_node(
        scope=graph_scope,
        node_type="Character",
        canonical_key="character:ann",
        now=now,
    )
    short_topic = graph.upsert_node(
        scope=graph_scope,
        node_type="Topic",
        canonical_key="temporary-topic",
        ttl_seconds=60,
        now=now,
    )
    graph.upsert_edge(
        scope=graph_scope,
        source_node_id=character.id,
        relation="PARTICIPATED_IN",
        target_node_id=short_topic.id,
        confidence=0.7,
        ttl_seconds=60,
        now=now,
    )

    before = graph.neighbors(
        scope=graph_scope,
        node_id=character.id,
        now=now + timedelta(seconds=30),
    )
    after = graph.neighbors(
        scope=graph_scope,
        node_id=character.id,
        now=now + timedelta(seconds=61),
    )
    cleaned = graph.cleanup_expired(now=now + timedelta(seconds=61))

    assert len(before) == 1
    assert after == ()
    assert cleaned == {"edges": 1, "nodes": 1}
    assert graph.get_node(short_topic.id, scope=graph_scope) is None


def test_scope_cleanup_removes_only_target_scope(tmp_path: Path) -> None:
    graph = repository(tmp_path)
    first_scope = scope(channel="channel-1")
    other_scope = scope(channel="channel-2")
    first = graph.upsert_node(
        scope=first_scope,
        node_type="Topic",
        canonical_key="one",
    )
    other = graph.upsert_node(
        scope=other_scope,
        node_type="Topic",
        canonical_key="two",
    )

    result = graph.delete_scope(first_scope)

    assert result["nodes"] == 1
    assert graph.get_node(first.id) is None
    assert graph.get_node(other.id, scope=other_scope) is not None
