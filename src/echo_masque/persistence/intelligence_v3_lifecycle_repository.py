"""Account ownership lifecycle for Intelligence Core v3 authority stores."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import delete, update

from echo_masque.persistence.belief_models import (
    BeliefEvidenceDependencyRecord,
    BeliefRevisionEventRecord,
    BeliefV3Record,
)
from echo_masque.persistence.character_relationship_models import (
    CharacterPersonImpressionRecord,
    CharacterRelationshipPriorRecord,
    DeploymentRelationshipEventRecord,
    DeploymentRelationshipStateRecord,
)
from echo_masque.persistence.conversation_runtime_models import (
    ConversationEpisodeV3Record,
    PendingActionV3Record,
    ThreadWorkingStateRecord,
)
from echo_masque.persistence.conversation_structure_models import (
    ConversationSegmentV3Record,
    ConversationThreadRecord,
    MessageRelationRecord,
    ThreadMembershipRecord,
)
from echo_masque.persistence.database import Database
from echo_masque.persistence.entity_evidence_models import (
    EntityV3Record,
    EvidenceEdgeV3Record,
    KnowledgeGapRecord,
)
from echo_masque.persistence.server_knowledge_v3_models import (
    KnowledgeConsolidationCheckpointV3Record,
    ServerWikiPageV3Record,
)
from echo_masque.persistence.social_intelligence_models import (
    ImpressionV3Record,
    SocialEventV3Record,
)

_OWNER_MODELS: Sequence[type[Any]] = (
    BeliefEvidenceDependencyRecord,
    BeliefRevisionEventRecord,
    BeliefV3Record,
    SocialEventV3Record,
    ImpressionV3Record,
    PendingActionV3Record,
    ThreadWorkingStateRecord,
    ConversationEpisodeV3Record,
    ThreadMembershipRecord,
    MessageRelationRecord,
    ConversationSegmentV3Record,
    ConversationThreadRecord,
    KnowledgeGapRecord,
    EvidenceEdgeV3Record,
    EntityV3Record,
    KnowledgeConsolidationCheckpointV3Record,
    ServerWikiPageV3Record,
    DeploymentRelationshipEventRecord,
    CharacterPersonImpressionRecord,
    DeploymentRelationshipStateRecord,
    CharacterRelationshipPriorRecord,
)

_TABLE_KEYS: dict[type[Any], str] = {
    BeliefEvidenceDependencyRecord: "belief_evidence_dependencies_v3",
    BeliefRevisionEventRecord: "belief_revision_events_v3",
    BeliefV3Record: "beliefs_v3",
    SocialEventV3Record: "social_events_v3",
    ImpressionV3Record: "impressions_v3",
    PendingActionV3Record: "pending_actions_v3",
    ThreadWorkingStateRecord: "thread_working_states_v3",
    ConversationEpisodeV3Record: "conversation_episodes_v3",
    ThreadMembershipRecord: "thread_memberships_v3",
    MessageRelationRecord: "message_relations_v3",
    ConversationSegmentV3Record: "conversation_segments_v3",
    ConversationThreadRecord: "conversation_threads_v3",
    KnowledgeGapRecord: "knowledge_gaps_v3",
    EvidenceEdgeV3Record: "evidence_edges_v3",
    EntityV3Record: "entities_v3",
    KnowledgeConsolidationCheckpointV3Record: "knowledge_consolidation_checkpoints_v3",
    ServerWikiPageV3Record: "server_wiki_pages_v3",
    DeploymentRelationshipEventRecord: "deployment_relationship_events",
    CharacterPersonImpressionRecord: "character_person_impressions",
    DeploymentRelationshipStateRecord: "deployment_relationship_states",
    CharacterRelationshipPriorRecord: "character_relationship_priors",
}


class IntelligenceV3LifecycleRepository:
    """Delete/claim all v3 intelligence state as one coherent ownership boundary."""

    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def _rowcount(result: Any) -> int:
        value = getattr(result, "rowcount", 0)
        return int(value) if isinstance(value, int) and value > 0 else 0

    def delete_owner(self, owner_id: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        with self.database.session() as session:
            for model in _OWNER_MODELS:
                owner_column = model.owner_id
                result = session.execute(delete(model).where(owner_column == owner_id))
                counts[_TABLE_KEYS[model]] = self._rowcount(result)
            session.commit()
        return counts

    def claim_owner(self, from_owner_id: str, to_owner_id: str) -> dict[str, int]:
        if not from_owner_id or not to_owner_id or from_owner_id == to_owner_id:
            return {key: 0 for key in _TABLE_KEYS.values()}
        counts: dict[str, int] = {}
        with self.database.session() as session:
            for model in _OWNER_MODELS:
                owner_column = model.owner_id
                result = session.execute(
                    update(model).where(owner_column == from_owner_id).values(owner_id=to_owner_id)
                )
                counts[_TABLE_KEYS[model]] = self._rowcount(result)
            session.commit()
        return counts


__all__ = ["IntelligenceV3LifecycleRepository"]
