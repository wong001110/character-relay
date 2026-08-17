"""Layered Memory sidecars over the existing conversation consolidation worker."""

from __future__ import annotations

from sqlalchemy import select

from echo_masque.conversation_consolidation import (
    ConsolidationResult,
    ConversationConsolidationService,
    MemoryConsolidationProposal,
)
from echo_masque.memory_layers import (
    CharacterMemorySummaryService,
    SynthesizedMemoryFreshnessRepository,
)
from echo_masque.persistence.conversation_episode_models import ConversationEpisodeRecord
from echo_masque.persistence.conversation_topic_models import ConversationTopicRecord
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord
from echo_masque.persistence.memory_vnext_models import ConversationMemoryVNextRecord


class LayeredConversationConsolidationService(ConversationConsolidationService):
    """Keep freshness/summary metadata in sync without changing Memory authority semantics."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        database = self.memory_repository.database
        self.memory_freshness = SynthesizedMemoryFreshnessRepository(database)
        self.memory_summaries = CharacterMemorySummaryService(
            database,
            freshness=self.memory_freshness,
        )

    def _update_memory(
        self,
        *,
        target: ConversationMemoryVNextRecord,
        proposal: MemoryConsolidationProposal,
        episode_ids: list[str],
        source_message_ids: list[str],
    ) -> ConversationMemoryVNextRecord | None:
        memory = super()._update_memory(
            target=target,
            proposal=proposal,
            episode_ids=episode_ids,
            source_message_ids=source_message_ids,
        )
        if memory is not None:
            self.memory_freshness.mark_confirmed(memory)
        return memory

    def _apply_memory_proposal(
        self,
        *,
        topic: ConversationTopicRecord,
        deployment: CharacterDeploymentRecord,
        proposal: MemoryConsolidationProposal,
        participant_alias: dict[str, str],
        candidate_alias: dict[str, ConversationMemoryVNextRecord],
        episode_ids: list[str],
        source_message_ids: list[str],
    ) -> ConversationMemoryVNextRecord | None:
        memory = super()._apply_memory_proposal(
            topic=topic,
            deployment=deployment,
            proposal=proposal,
            participant_alias=participant_alias,
            candidate_alias=candidate_alias,
            episode_ids=episode_ids,
            source_message_ids=source_message_ids,
        )
        if memory is not None:
            self.memory_freshness.mark_confirmed(memory)
        return memory

    def _refresh_topic_summaries(self, topic: ConversationTopicRecord) -> None:
        with self.memory_repository.database.session() as session:
            character_ids = list(
                dict.fromkeys(
                    item
                    for item in session.scalars(
                        select(ConversationMemoryVNextRecord.character_card_id).where(
                            ConversationMemoryVNextRecord.owner_id == topic.owner_id,
                            ConversationMemoryVNextRecord.connection_id == topic.connection_id,
                            ConversationMemoryVNextRecord.guild_id == topic.guild_id,
                        )
                    )
                    if item
                )
            )
        for character_card_id in character_ids[:50]:
            self.memory_summaries.refresh(
                owner_id=topic.owner_id,
                character_card_id=character_card_id,
                connection_id=topic.connection_id,
                guild_id=topic.guild_id,
            )

    def consolidate_topic(
        self,
        *,
        owner_id: str,
        topic_id: str,
        reason: str,
    ) -> ConsolidationResult:
        result = super().consolidate_topic(
            owner_id=owner_id,
            topic_id=topic_id,
            reason=reason,
        )
        if result.status != "skipped":
            topic = self.topic_repository.get(topic_id, owner_id)
            if topic is not None:
                self._refresh_topic_summaries(topic)
        return result

    async def run_once(self, *, include_maintenance: bool = False) -> int:
        processed = await super().run_once(include_maintenance=include_maintenance)
        if include_maintenance:
            self.memory_freshness.refresh_staleness()
        return processed


__all__ = ["LayeredConversationConsolidationService"]
