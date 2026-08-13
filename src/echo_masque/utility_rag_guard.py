"""Post-process contextual RAG fallback with current-turn Utility evidence."""

from __future__ import annotations

from typing import TYPE_CHECKING

from echo_masque.context_layer import CharacterTurnContext
from echo_masque.semantic_turn_runtime import SemanticTurnSignalStore
from echo_masque.utility_gateway_contracts import UtilityGatewayUnavailable
from echo_masque.utility_gateway_router import UtilityGatewayRouter

if TYPE_CHECKING:
    from echo_masque.api.connector_schemas import DiscordInboundMessage
    from echo_masque.persistence.deployment_models import CharacterDeploymentRecord


class UtilityRagGuard:
    def __init__(self, gateway: UtilityGatewayRouter) -> None:
        self.gateway = gateway

    @staticmethod
    def _continuation(
        payload: DiscordInboundMessage,
        deployment: CharacterDeploymentRecord,
    ) -> bool:
        signals = SemanticTurnSignalStore.get(deployment.id, payload.message_id)
        if signals is None:
            return bool(payload.reply_to_message_id)
        return bool(
            signals.continuation_tool_ids
            or signals.retry_score >= 0.48
            or signals.continuity_reason
            in {
                "semantic_continuation",
                "empty_message_keeps_active_topic",
                "utility_topic_continue",
                "utility_topic_clarify",
            }
            or payload.reply_to_message_id
        )

    @staticmethod
    def _without_knowledge(
        context: CharacterTurnContext,
        reason: str,
    ) -> CharacterTurnContext:
        trace = context.trace.model_copy(
            update={
                "rag_status": "skipped",
                "rag_reason": reason,
                "selected_chunk_count": 0,
                "selected_knowledge_tokens": 0,
                "selected": [],
            }
        )
        return CharacterTurnContext(
            smart_output=context.smart_output,
            knowledge=(),
            trace=trace,
        )

    def apply(
        self,
        *,
        context: CharacterTurnContext,
        payload: DiscordInboundMessage,
        deployment: CharacterDeploymentRecord,
    ) -> CharacterTurnContext:
        if context.trace.retrieval_mode != "contextual_fallback":
            return context
        if not self._continuation(payload, deployment):
            return self._without_knowledge(
                context,
                "contextual_fallback_blocked_no_continuity",
            )
        prompt = "\n".join(
            (
                f"Current message: {payload.text[:3000]}",
                f"Topic id: {context.trace.topic_id}",
                f"RAG dense score: {context.trace.rag_gate_dense_score:.4f}",
                f"RAG sparse score: {context.trace.rag_gate_sparse_score:.4f}",
                "Does the current message genuinely require the carried-over Knowledge?",
            )
        )
        try:
            decision, _ = self.gateway.rag_decision(prompt=prompt)
        except UtilityGatewayUnavailable:
            return self._without_knowledge(
                context,
                "contextual_fallback_blocked_judge_unavailable",
            )
        if not decision.need_knowledge or decision.confidence < 0.65:
            return self._without_knowledge(
                context,
                "contextual_fallback_rejected_by_utility",
            )
        return context


__all__ = ["UtilityRagGuard"]
