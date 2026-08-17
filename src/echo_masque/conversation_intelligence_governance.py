"""Owner-scoped governance for derived Conversation Intelligence data.

Raw Discord message/event evidence is intentionally outside this service. Topic, Episode, Memory,
Wiki, Graph, Learned State, consolidation checkpoints, semantic vectors, and decision traces are
derived/rebuildable intelligence and may be inspected or removed when historical data is polluted.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, or_, select

from echo_masque.persistence.character_learned_state_models import CharacterLearnedStateRecord
from echo_masque.persistence.conversation_episode_models import ConversationEpisodeRecord
from echo_masque.persistence.conversation_graph_models import (
    ConversationGraphEdgeRecord,
    ConversationGraphNodeRecord,
)
from echo_masque.persistence.conversation_topic_decision_repository import (
    ConversationTopicDecisionRepository,
)
from echo_masque.persistence.conversation_topic_models import ConversationTopicRecord
from echo_masque.persistence.database import Database
from echo_masque.persistence.memory_vnext_models import ConversationMemoryVNextRecord
from echo_masque.persistence.semantic_vector_models import SemanticVectorRecord
from echo_masque.persistence.server_knowledge_models import (
    ConversationAuthorityEdgeRecord,
    ConversationConsolidationCheckpointRecord,
    ServerWikiPageRecord,
)

_TOPIC_VECTOR_NAMESPACE = "conversation-topic"


def _decode_strings(raw: str) -> set[str]:
    try:
        value = json.loads(raw or "[]")
    except (json.JSONDecodeError, TypeError):
        return set()
    if not isinstance(value, list):
        return set()
    return {str(item) for item in value if isinstance(item, str) and item}


@dataclass(frozen=True, slots=True)
class TopicDerivedImpact:
    topic_id: str
    topic_found: bool
    episodes: int = 0
    memories: int = 0
    wiki_pages: int = 0
    authority_edges: int = 0
    checkpoints: int = 0
    learned_states: int = 0
    graph_nodes: int = 0
    graph_edges: int = 0
    semantic_vectors: int = 0

    @property
    def total_derived_records(self) -> int:
        return (
            int(self.topic_found)
            + self.episodes
            + self.memories
            + self.wiki_pages
            + self.authority_edges
            + self.checkpoints
            + self.learned_states
            + self.graph_nodes
            + self.graph_edges
            + self.semantic_vectors
        )


# Keep a normal instance __dict__: the API layer deliberately serializes this compact aggregate.
@dataclass(frozen=True)
class DerivedResetResult:
    topics: int = 0
    episodes: int = 0
    memories: int = 0
    wiki_pages: int = 0
    authority_edges: int = 0
    checkpoints: int = 0
    learned_states: int = 0
    graph_nodes: int = 0
    graph_edges: int = 0
    semantic_vectors: int = 0

    def plus(self, impact: TopicDerivedImpact) -> DerivedResetResult:
        return DerivedResetResult(
            topics=self.topics + int(impact.topic_found),
            episodes=self.episodes + impact.episodes,
            memories=self.memories + impact.memories,
            wiki_pages=self.wiki_pages + impact.wiki_pages,
            authority_edges=self.authority_edges + impact.authority_edges,
            checkpoints=self.checkpoints + impact.checkpoints,
            learned_states=self.learned_states + impact.learned_states,
            graph_nodes=self.graph_nodes + impact.graph_nodes,
            graph_edges=self.graph_edges + impact.graph_edges,
            semantic_vectors=self.semantic_vectors + impact.semantic_vectors,
        )


class ConversationIntelligenceGovernanceService:
    """Inspect and mutate only derived Conversation Intelligence under one owner."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self.topic_decisions = ConversationTopicDecisionRepository(database)

    def list_character_memories(
        self,
        *,
        owner_id: str,
        character_card_id: str,
        connection_id: str,
        guild_id: str,
        status: str = "",
        limit: int = 200,
    ) -> list[ConversationMemoryVNextRecord]:
        with self.database.session() as session:
            query = select(ConversationMemoryVNextRecord).where(
                ConversationMemoryVNextRecord.owner_id == owner_id,
                ConversationMemoryVNextRecord.character_card_id == character_card_id,
                ConversationMemoryVNextRecord.connection_id == connection_id,
                ConversationMemoryVNextRecord.guild_id == guild_id,
            )
            if status:
                query = query.where(ConversationMemoryVNextRecord.status == status)
            return list(
                session.scalars(
                    query.order_by(
                        ConversationMemoryVNextRecord.updated_at.desc(),
                        ConversationMemoryVNextRecord.importance.desc(),
                    ).limit(max(1, min(limit, 500)))
                )
            )

    def archive_topic(self, *, owner_id: str, topic_id: str) -> ConversationTopicRecord:
        now = datetime.now(UTC)
        with self.database.session() as session:
            topic = session.scalar(
                select(ConversationTopicRecord).where(
                    ConversationTopicRecord.id == topic_id,
                    ConversationTopicRecord.owner_id == owner_id,
                )
            )
            if topic is None:
                raise KeyError("topic")
            topic.status = "archived"
            topic.closed_at = now
            topic.updated_at = now
            session.commit()
            session.refresh(topic)
            return topic

    def invalidate_memory(
        self,
        *,
        owner_id: str,
        memory_id: str,
    ) -> ConversationMemoryVNextRecord:
        now = datetime.now(UTC)
        with self.database.session() as session:
            memory = session.scalar(
                select(ConversationMemoryVNextRecord).where(
                    ConversationMemoryVNextRecord.id == memory_id,
                    ConversationMemoryVNextRecord.owner_id == owner_id,
                )
            )
            if memory is None:
                raise KeyError("memory")
            memory.status = "invalidated"
            memory.valid_to = now
            memory.updated_at = now
            session.commit()
            session.refresh(memory)
            return memory

    def delete_memory(self, *, owner_id: str, memory_id: str) -> bool:
        memory_ref = f"memory:{memory_id}"
        with self.database.session() as session:
            memory = session.scalar(
                select(ConversationMemoryVNextRecord).where(
                    ConversationMemoryVNextRecord.id == memory_id,
                    ConversationMemoryVNextRecord.owner_id == owner_id,
                )
            )
            if memory is None:
                return False
            session.execute(
                delete(ConversationAuthorityEdgeRecord).where(
                    ConversationAuthorityEdgeRecord.owner_id == owner_id,
                    or_(
                        ConversationAuthorityEdgeRecord.source_ref == memory_ref,
                        ConversationAuthorityEdgeRecord.target_ref == memory_ref,
                    ),
                )
            )
            session.delete(memory)
            session.commit()
            return True

    def reset_character_memories(
        self,
        *,
        owner_id: str,
        character_card_id: str,
        connection_id: str,
        guild_id: str,
    ) -> int:
        with self.database.session() as session:
            memories = list(
                session.scalars(
                    select(ConversationMemoryVNextRecord).where(
                        ConversationMemoryVNextRecord.owner_id == owner_id,
                        ConversationMemoryVNextRecord.character_card_id == character_card_id,
                        ConversationMemoryVNextRecord.connection_id == connection_id,
                        ConversationMemoryVNextRecord.guild_id == guild_id,
                    )
                )
            )
            refs = [f"memory:{item.id}" for item in memories]
            if refs:
                session.execute(
                    delete(ConversationAuthorityEdgeRecord).where(
                        ConversationAuthorityEdgeRecord.owner_id == owner_id,
                        ConversationAuthorityEdgeRecord.connection_id == connection_id,
                        ConversationAuthorityEdgeRecord.guild_id == guild_id,
                        or_(
                            ConversationAuthorityEdgeRecord.source_ref.in_(refs),
                            ConversationAuthorityEdgeRecord.target_ref.in_(refs),
                        ),
                    )
                )
            for item in memories:
                session.delete(item)
            session.commit()
            return len(memories)

    def _topic_components(
        self,
        *,
        owner_id: str,
        topic_id: str,
    ) -> tuple[
        ConversationTopicRecord | None,
        list[ConversationEpisodeRecord],
        list[ConversationMemoryVNextRecord],
        list[ServerWikiPageRecord],
        list[ConversationGraphNodeRecord],
    ]:
        with self.database.session() as session:
            topic = session.scalar(
                select(ConversationTopicRecord).where(
                    ConversationTopicRecord.id == topic_id,
                    ConversationTopicRecord.owner_id == owner_id,
                )
            )
            if topic is None:
                return None, [], [], [], []
            episodes = list(
                session.scalars(
                    select(ConversationEpisodeRecord).where(
                        ConversationEpisodeRecord.owner_id == owner_id,
                        ConversationEpisodeRecord.topic_id == topic_id,
                    )
                )
            )
            episode_ids = {item.id for item in episodes}
            memory_candidates = list(
                session.scalars(
                    select(ConversationMemoryVNextRecord).where(
                        ConversationMemoryVNextRecord.owner_id == owner_id,
                        ConversationMemoryVNextRecord.connection_id == topic.connection_id,
                        ConversationMemoryVNextRecord.guild_id == topic.guild_id,
                    )
                )
            )
            memories = [
                item
                for item in memory_candidates
                if item.topic_id == topic_id
                or bool(_decode_strings(item.provenance_episode_ids_json) & episode_ids)
            ]
            wiki_pages = list(
                session.scalars(
                    select(ServerWikiPageRecord).where(
                        ServerWikiPageRecord.owner_id == owner_id,
                        ServerWikiPageRecord.connection_id == topic.connection_id,
                        ServerWikiPageRecord.guild_id == topic.guild_id,
                        ServerWikiPageRecord.page_key == f"topic:{topic_id}",
                    )
                )
            )
            graph_nodes = list(
                session.scalars(
                    select(ConversationGraphNodeRecord).where(
                        ConversationGraphNodeRecord.connection_id == topic.connection_id,
                        ConversationGraphNodeRecord.guild_id == topic.guild_id,
                        ConversationGraphNodeRecord.channel_id == topic.channel_id,
                        ConversationGraphNodeRecord.thread_id == topic.thread_id,
                        ConversationGraphNodeRecord.canonical_key == f"topic:{topic_id}",
                        ConversationGraphNodeRecord.scope_owner_id.in_(("", owner_id)),
                    )
                )
            )
            return topic, episodes, memories, wiki_pages, graph_nodes

    def topic_delete_impact(self, *, owner_id: str, topic_id: str) -> TopicDerivedImpact:
        topic, episodes, memories, wiki_pages, graph_nodes = self._topic_components(
            owner_id=owner_id,
            topic_id=topic_id,
        )
        if topic is None:
            return TopicDerivedImpact(topic_id=topic_id, topic_found=False)
        episode_refs = [f"episode:{item.id}" for item in episodes]
        memory_refs = [f"memory:{item.id}" for item in memories]
        wiki_refs = [f"wiki:{item.id}" for item in wiki_pages]
        refs = [f"topic:{topic_id}", *episode_refs, *memory_refs, *wiki_refs]
        node_ids = [item.id for item in graph_nodes]
        with self.database.session() as session:
            authority_edges = list(
                session.scalars(
                    select(ConversationAuthorityEdgeRecord).where(
                        ConversationAuthorityEdgeRecord.owner_id == owner_id,
                        ConversationAuthorityEdgeRecord.connection_id == topic.connection_id,
                        ConversationAuthorityEdgeRecord.guild_id == topic.guild_id,
                        or_(
                            ConversationAuthorityEdgeRecord.source_ref.in_(refs),
                            ConversationAuthorityEdgeRecord.target_ref.in_(refs),
                        ),
                    )
                )
            )
            checkpoints = list(
                session.scalars(
                    select(ConversationConsolidationCheckpointRecord).where(
                        ConversationConsolidationCheckpointRecord.owner_id == owner_id,
                        ConversationConsolidationCheckpointRecord.topic_id == topic_id,
                    )
                )
            )
            learned_states = list(
                session.scalars(
                    select(CharacterLearnedStateRecord).where(
                        CharacterLearnedStateRecord.owner_id == owner_id,
                        CharacterLearnedStateRecord.subject_type == "topic",
                        CharacterLearnedStateRecord.subject_key == f"topic:{topic_id}",
                    )
                )
            )
            graph_edges: list[ConversationGraphEdgeRecord] = []
            if node_ids:
                graph_edges = list(
                    session.scalars(
                        select(ConversationGraphEdgeRecord).where(
                            or_(
                                ConversationGraphEdgeRecord.source_node_id.in_(node_ids),
                                ConversationGraphEdgeRecord.target_node_id.in_(node_ids),
                            )
                        )
                    )
                )
            vectors = list(
                session.scalars(
                    select(SemanticVectorRecord).where(
                        SemanticVectorRecord.owner_id == owner_id,
                        SemanticVectorRecord.namespace == _TOPIC_VECTOR_NAMESPACE,
                        SemanticVectorRecord.resource_id == topic_id,
                    )
                )
            )
        return TopicDerivedImpact(
            topic_id=topic_id,
            topic_found=True,
            episodes=len(episodes),
            memories=len(memories),
            wiki_pages=len(wiki_pages),
            authority_edges=len(authority_edges),
            checkpoints=len(checkpoints),
            learned_states=len(learned_states),
            graph_nodes=len(graph_nodes),
            graph_edges=len(graph_edges),
            semantic_vectors=len(vectors),
        )

    def delete_topic_derived(
        self,
        *,
        owner_id: str,
        topic_id: str,
    ) -> TopicDerivedImpact:
        impact = self.topic_delete_impact(owner_id=owner_id, topic_id=topic_id)
        if not impact.topic_found:
            return impact
        topic, episodes, memories, wiki_pages, graph_nodes = self._topic_components(
            owner_id=owner_id,
            topic_id=topic_id,
        )
        if topic is None:
            return TopicDerivedImpact(topic_id=topic_id, topic_found=False)
        episode_refs = [f"episode:{item.id}" for item in episodes]
        memory_refs = [f"memory:{item.id}" for item in memories]
        wiki_refs = [f"wiki:{item.id}" for item in wiki_pages]
        refs = [f"topic:{topic_id}", *episode_refs, *memory_refs, *wiki_refs]
        node_ids = [item.id for item in graph_nodes]
        with self.database.session() as session:
            if node_ids:
                session.execute(
                    delete(ConversationGraphEdgeRecord).where(
                        or_(
                            ConversationGraphEdgeRecord.source_node_id.in_(node_ids),
                            ConversationGraphEdgeRecord.target_node_id.in_(node_ids),
                        )
                    )
                )
                session.execute(
                    delete(ConversationGraphNodeRecord).where(
                        ConversationGraphNodeRecord.id.in_(node_ids)
                    )
                )
            session.execute(
                delete(ConversationAuthorityEdgeRecord).where(
                    ConversationAuthorityEdgeRecord.owner_id == owner_id,
                    ConversationAuthorityEdgeRecord.connection_id == topic.connection_id,
                    ConversationAuthorityEdgeRecord.guild_id == topic.guild_id,
                    or_(
                        ConversationAuthorityEdgeRecord.source_ref.in_(refs),
                        ConversationAuthorityEdgeRecord.target_ref.in_(refs),
                    ),
                )
            )
            session.execute(
                delete(ConversationConsolidationCheckpointRecord).where(
                    ConversationConsolidationCheckpointRecord.owner_id == owner_id,
                    ConversationConsolidationCheckpointRecord.topic_id == topic_id,
                )
            )
            session.execute(
                delete(CharacterLearnedStateRecord).where(
                    CharacterLearnedStateRecord.owner_id == owner_id,
                    CharacterLearnedStateRecord.subject_type == "topic",
                    CharacterLearnedStateRecord.subject_key == f"topic:{topic_id}",
                )
            )
            session.execute(
                delete(SemanticVectorRecord).where(
                    SemanticVectorRecord.owner_id == owner_id,
                    SemanticVectorRecord.namespace == _TOPIC_VECTOR_NAMESPACE,
                    SemanticVectorRecord.resource_id == topic_id,
                )
            )
            if memories:
                session.execute(
                    delete(ConversationMemoryVNextRecord).where(
                        ConversationMemoryVNextRecord.id.in_([item.id for item in memories])
                    )
                )
            if episodes:
                session.execute(
                    delete(ConversationEpisodeRecord).where(
                        ConversationEpisodeRecord.id.in_([item.id for item in episodes])
                    )
                )
            session.execute(
                delete(ServerWikiPageRecord).where(
                    ServerWikiPageRecord.owner_id == owner_id,
                    ServerWikiPageRecord.page_key == f"topic:{topic_id}",
                )
            )
            session.execute(
                delete(ConversationTopicRecord).where(
                    ConversationTopicRecord.id == topic_id,
                    ConversationTopicRecord.owner_id == owner_id,
                )
            )
            session.commit()
        # Decision observations are derived traces as well and must not retain references to a
        # deliberately purged polluted Topic.
        self.topic_decisions.delete_topic(owner_id=owner_id, topic_id=topic_id)
        return impact

    def reset_topic_scope(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        channel_id: str,
        thread_id: str = "",
    ) -> DerivedResetResult:
        with self.database.session() as session:
            topic_ids = list(
                session.scalars(
                    select(ConversationTopicRecord.id).where(
                        ConversationTopicRecord.owner_id == owner_id,
                        ConversationTopicRecord.platform == "discord",
                        ConversationTopicRecord.connection_id == connection_id,
                        ConversationTopicRecord.guild_id == guild_id,
                        ConversationTopicRecord.channel_id == channel_id,
                        ConversationTopicRecord.thread_id == thread_id,
                    )
                )
            )
        result = DerivedResetResult()
        for topic_id in topic_ids:
            result = result.plus(
                self.delete_topic_derived(owner_id=owner_id, topic_id=topic_id)
            )
        return result


__all__ = [
    "ConversationIntelligenceGovernanceService",
    "DerivedResetResult",
    "TopicDerivedImpact",
]
