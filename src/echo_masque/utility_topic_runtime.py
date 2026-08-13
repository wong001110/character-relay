"""Utility-assisted gray-zone Topic continuity classification."""

from __future__ import annotations

from typing import TYPE_CHECKING

from echo_masque.conversation_topic import (
    ConversationTopicMemoryService,
    TopicContinuityDecision,
)
from echo_masque.utility_gateway_contracts import UtilityGatewayUnavailable
from echo_masque.utility_gateway_router import UtilityGatewayRouter

if TYPE_CHECKING:
    from echo_masque.persistence.conversation_topic_models import ConversationTopicRecord

_MIN_CONFIDENCE = 0.68


class UtilityTopicMemoryService(ConversationTopicMemoryService):
    """Keep obvious E5 decisions local; ask Utility only for ambiguous discourse turns."""

    def __init__(self, *args: object, gateway: UtilityGatewayRouter, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self.gateway = gateway

    @staticmethod
    def _clear(decision: TopicContinuityDecision) -> bool:
        if decision.reason in {
            "empty_message_keeps_active_topic",
            "semantic_switch_topic",
        }:
            return True
        return bool(
            decision.topic_similarity >= 0.60
            or decision.sparse_similarity >= 0.30
            or decision.acts.continuation >= 0.62
            or decision.acts.switch_topic >= 0.68
        )

    def classify_continuity(
        self,
        *,
        text: str,
        active: ConversationTopicRecord,
    ) -> TopicContinuityDecision:
        base = super().classify_continuity(text=text, active=active)
        if self._clear(base):
            return base
        prompt = "\n".join(
            (
                f"Current message: {text[:3000]}",
                f"Active topic: {active.topic_label[:500]}",
                f"Topic summary: {active.summary[:1600]}",
                f"E5 topic similarity: {base.topic_similarity:.4f}",
                f"Sparse similarity: {base.sparse_similarity:.4f}",
                f"Continuation act: {base.acts.continuation:.4f}",
                f"Switch act: {base.acts.switch_topic:.4f}",
            )
        )
        try:
            judged, _ = self.gateway.topic_decision(prompt=prompt)
        except UtilityGatewayUnavailable:
            return base
        if judged.confidence < _MIN_CONFIDENCE:
            return base
        return TopicContinuityDecision(
            same_topic=judged.decision in {"continue", "clarify"},
            topic_similarity=base.topic_similarity,
            sparse_similarity=base.sparse_similarity,
            acts=base.acts,
            reason=f"utility_topic_{judged.decision}",
        )


__all__ = ["UtilityTopicMemoryService"]
