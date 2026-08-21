"""Project authoritative v3 Smart Participation outcomes into durable Behavior State."""

from __future__ import annotations

from dataclasses import dataclass

from echo_masque.api.smart_participation_outcome_schemas import SmartParticipationOutcomeObservation
from echo_masque.character_learned_state import CharacterLearnedStateService, LearnedStateEvidence
from echo_masque.persistence import DeploymentRepository
from echo_masque.persistence.conversation_structure_repository import (
    ConversationStructureRepository,
)
from echo_masque.persistence.discord_identity_repository import DiscordIdentityRepository
from echo_masque.smart_participation_durable_state import SmartParticipationDurableStateService


@dataclass(frozen=True, slots=True)
class SmartParticipationOutcomeProjection:
    recorded: bool
    selected_count: int
    graph_edge_count: int
    learned_evidence_count: int
    durable_recorded: bool


class SmartParticipationOutcomeService:
    """Record admission as behavior evidence without inventing relationship or Topic truth."""

    def __init__(self, deployments: DeploymentRepository) -> None:
        self.deployments = deployments
        self.database = deployments.database
        self.identities = DiscordIdentityRepository(self.database)
        self.structure = ConversationStructureRepository(self.database)
        self.behavior = CharacterLearnedStateService(self.database)
        self.durable = SmartParticipationDurableStateService(self.database)

    @staticmethod
    def _burst_key(payload: SmartParticipationOutcomeObservation) -> str:
        burst = payload.burst_id.strip()
        if burst:
            return burst[:80]
        return f"message:{payload.message_id}"[:80] if payload.message_id else ""

    def _thread_for_message(
        self,
        *,
        owner_id: str,
        payload: SmartParticipationOutcomeObservation,
    ) -> str:
        if not payload.message_id:
            return ""
        thread = self.structure.thread_for_message(
            owner_id=owner_id,
            connection_id=payload.connection_id,
            guild_id=payload.guild_id,
            channel_id=payload.channel_id,
            discord_thread_id=payload.thread_id,
            message_id=payload.message_id,
        )
        return thread.id if thread is not None else ""

    def record(
        self,
        payload: SmartParticipationOutcomeObservation,
    ) -> SmartParticipationOutcomeProjection:
        selected_ids = tuple(
            dict.fromkeys(item for item in payload.selected_deployment_ids if item)
        )
        if not selected_ids:
            return SmartParticipationOutcomeProjection(False, 0, 0, 0, False)
        records = self.deployments.list_connector_deployments(
            platform="discord",
            connection_id=payload.connection_id,
        )
        record_by_id = {item.id: item for item in records if item.id in selected_ids}
        selected = [record_by_id[item] for item in selected_ids if item in record_by_id]
        if not selected:
            return SmartParticipationOutcomeProjection(False, 0, 0, 0, False)

        if payload.author_id and payload.guild_id:
            for owner_id in dict.fromkeys(record.owner_id for record in selected):
                self.identities.upsert_guild_actor_identity(
                    owner_id=owner_id,
                    connection_id=payload.connection_id,
                    guild_id=payload.guild_id,
                    user_id=payload.author_id,
                    guild_display_name=payload.author_display_name,
                    global_display_name=payload.author_global_name,
                    username=payload.author_username,
                    avatar_url=payload.author_avatar_url,
                    is_bot=payload.author_is_bot,
                )

        self.durable.record_admission(
            connection_id=payload.connection_id,
            guild_id=payload.guild_id,
            channel_id=payload.channel_id,
            thread_id=payload.thread_id,
            deployment_ids=tuple(item.id for item in selected),
            window_seconds=600,
        )
        burst_key = self._burst_key(payload)
        learned_count = 0
        scope_key = ":".join(
            (payload.connection_id, payload.guild_id, payload.channel_id, payload.thread_id)
        )

        for record in selected:
            thread_id = self._thread_for_message(owner_id=record.owner_id, payload=payload)
            evidence_base = dict(
                owner_id=record.owner_id,
                character_card_id=record.character_card_id,
                source_type="runtime_admission",
                source_message_id=payload.message_id,
                source_burst_id=burst_key,
                connection_id=payload.connection_id,
                guild_id=payload.guild_id,
                channel_id=payload.channel_id,
                conversation_thread_id=thread_id,
            )
            self.behavior.record_evidence(
                LearnedStateEvidence(
                    state_type="participation_fatigue",
                    subject_type="concept",
                    subject_key=f"scope:{scope_key}",
                    delta=1.0,
                    confidence=0.9,
                    reason_code="selected_smart_participation",
                    **evidence_base,
                )
            )
            learned_count += 1

            # Admission proves only that the Character took ownership of this resolved line for
            # the current turn. It does not prove liking, trust, comfort, familiarity, expertise,
            # or durable interest. Those require their own evidence paths.
            if thread_id:
                for state_type, delta, confidence, reason in (
                    (
                        "conversation_ownership",
                        0.55,
                        0.75,
                        "selected_to_answer_conversation_thread",
                    ),
                    ("salience", 0.35, 0.65, "recent_selected_conversation_thread"),
                ):
                    self.behavior.record_evidence(
                        LearnedStateEvidence(
                            state_type=state_type,  # type: ignore[arg-type]
                            subject_type="thread",
                            subject_key=f"thread:{thread_id}",
                            delta=delta,
                            confidence=confidence,
                            reason_code=reason,
                            **evidence_base,
                        )
                    )
                    learned_count += 1

        # Legacy graph_edge_count is kept only as a response-shape compatibility metric. v3
        # Evidence Graph relations are written by actual structure/social/media evidence producers,
        # not by mere admission.
        return SmartParticipationOutcomeProjection(
            recorded=True,
            selected_count=len(selected),
            graph_edge_count=0,
            learned_evidence_count=learned_count,
            durable_recorded=True,
        )


__all__ = ["SmartParticipationOutcomeProjection", "SmartParticipationOutcomeService"]
