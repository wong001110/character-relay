"""Best-effort Evidence Graph projections after durable v3 runtime observation."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime

from echo_masque.api.smart_participation_v3_schemas import SmartParticipationResolveRequest
from echo_masque.conversation_runtime import (
    ConversationRuntimeCoordinator,
    ConversationRuntimeObservation,
)
from echo_masque.conversation_structure_resolver import ConversationSegmentationResult
from echo_masque.evidence_graph_v3 import EvidenceGraphService
from echo_masque.persistence.conversation_runtime_repository import ConversationRuntimeRepository
from echo_masque.persistence.conversation_structure_repository import (
    ConversationStructureRepository,
)

logger = logging.getLogger(__name__)


class ProjectionConversationRuntimeCoordinator(ConversationRuntimeCoordinator):
    """Keep Episode writes authoritative while isolating derived graph projection failures.

    This coordinator deliberately does not ground names, create Entities, or invoke Discovery.
    It only mirrors already-persisted scoped structure and Episode records into the Evidence Graph.
    """

    def __init__(
        self,
        structure: ConversationStructureRepository,
        runtime: ConversationRuntimeRepository | None = None,
        *,
        graph: EvidenceGraphService,
    ) -> None:
        super().__init__(structure, runtime)
        self.graph = graph

    def observe(
        self,
        *,
        owner_id: str,
        payload: SmartParticipationResolveRequest,
        result: ConversationSegmentationResult,
        now: datetime | None = None,
    ) -> ConversationRuntimeObservation:
        # Runtime/Episode persistence is not derived and must retain its existing caller-visible
        # failure semantics. Only the following graph mirror is failure-isolated.
        observation = super().observe(
            owner_id=owner_id,
            payload=payload,
            result=result,
            now=now,
        )
        try:
            self._project(
                owner_id=owner_id,
                payload=payload,
                result=result,
                observation=observation,
                now=now,
            )
        except Exception:
            logger.exception(
                "Intelligence v3 derived projection failed after runtime observation",
                extra={
                    "owner_id": owner_id,
                    "connection_id": payload.connection_id,
                    "guild_id": payload.guild_id,
                },
            )
        return observation

    def _project(
        self,
        *,
        owner_id: str,
        payload: SmartParticipationResolveRequest,
        result: ConversationSegmentationResult,
        observation: ConversationRuntimeObservation,
        now: datetime | None,
    ) -> None:
        message_ids = tuple(
            dict.fromkeys(
                message_id
                for segment in result.segments
                for message_id in segment.message_ids
            )
        )
        for relation in self.structure.relations_for_messages(
            owner_id=owner_id,
            connection_id=payload.connection_id,
            guild_id=payload.guild_id,
            message_ids=message_ids,
        ):
            self._project_one(
                "message_relation",
                self.graph.project_message_relation,
                owner_id=owner_id,
                connection_id=payload.connection_id,
                guild_id=payload.guild_id,
                relation=relation,
                now=now,
            )
        # Project every Membership version. A later reassignment therefore advances the old
        # graph edge to superseded rather than hiding its provenance.
        for segment in result.segments:
            for membership in self.structure.membership_history(
                owner_id=owner_id,
                connection_id=payload.connection_id,
                guild_id=payload.guild_id,
                segment_id=segment.id,
            ):
                self._project_one(
                    "thread_membership",
                    self.graph.project_membership,
                    owner_id=owner_id,
                    connection_id=payload.connection_id,
                    guild_id=payload.guild_id,
                    segment=segment,
                    membership=membership,
                    now=now,
                )
        for episode in observation.episodes:
            self._project_one(
                "episode",
                self.graph.project_episode,
                owner_id=owner_id,
                connection_id=payload.connection_id,
                guild_id=payload.guild_id,
                episode=episode,
                now=now,
            )

    @staticmethod
    def _project_one(
        kind: str,
        operation: Callable[..., object],
        /,
        **kwargs: object,
    ) -> None:
        try:
            operation(**kwargs)
        except Exception as exc:
            logger.warning(
                "Intelligence v3 derived projection item failed",
                extra={"projection_kind": kind, "error_type": type(exc).__name__},
            )


__all__ = ["ProjectionConversationRuntimeCoordinator"]
