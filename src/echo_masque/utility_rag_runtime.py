"""Fail-closed Utility review for contextual RAG carry-over."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import ConfigDict

from echo_masque.context_layer import (
    CharacterContextTraceView,
    CharacterTurnContext,
    ContextOrchestrator,
)
from echo_masque.semantic_turn_runtime import SemanticTurnSignalStore
from echo_masque.utility_gateway_contracts import UtilityGatewayUnavailable
from echo_masque.utility_gateway_router import UtilityGatewayRouter

if TYPE_CHECKING:
    from echo_masque.api.connector_schemas import DiscordInboundMessage
    from echo_masque.persistence.deployment_models import CharacterDeploymentRecord

_MIN_CONFIDENCE = 0.65
_WEAK_DENSE = 0.28
_WEAK_SPARSE = 0.01


class UtilityContextTraceView(CharacterContextTraceView):
    model_config = ConfigDict(extra="forbid")

    utility_judge_used: bool = False
    utility_judge_provider: str = ""
    utility_judge_model: str = ""
    utility_judge_tier: str = ""
    utility_judge_confidence: float = 0.0
    utility_judge_reason: str = ""


class UtilityContextOrchestrator(ContextOrchestrator):
    """Prevent older messages from turning Knowledge on without current-turn evidence."""

    def __init__(self, *args: object, gateway: UtilityGatewayRouter, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self.gateway = gateway

    @staticmethod
    def _trace(
        context: CharacterTurnContext,
        **updates: object,
    ) -> UtilityContextTraceView:
        values = context.trace.model_dump()
        values.update(updates)
        return UtilityContextTraceView.model_validate(values)

    @classmethod
    def _strip(
        cls,
        context: CharacterTurnContext,
        *,
        reason: str,
        **updates: object,
    ) -> CharacterTurnContext:
        trace = cls._trace(
            context,
            rag_status="skipped",
            rag_reason=reason,
            selected_chunk_count=0,
            selected_knowledge_tokens=0,
            selected=[],
            **updates,
        )
        return CharacterTurnContext(
            smart_output=context.smart_output,
            knowledge=(),
            trace=trace,
        )

    @staticmethod
    def _has_continuation(
        payload: DiscordInboundMessage,
        deployment: CharacterDeploymentRecord,
    ) -> bool:
        signals = SemanticTurnSignalStore.get(deployment.id, payload.message_id)
        if signals is None:
            return bool(payload.reply_to_message_id)
        if signals.continuation_tool_ids or signals.retry_score >= 0.48:
            return True
        if signals.continuity_reason in {
            "semantic_continuation",
            "empty_message_keeps_active_topic",
            "utility_topic_continue",
            "utility_topic_clarify",
        }:
            return True
        return bool(payload.reply_to_message_id)

    def build(
        self,
        *,
        payload: DiscordInboundMessage,
        deployment: CharacterDeploymentRecord,
        character_name: str,
    ) -> CharacterTurnContext:
        context = super().build(
            payload=payload,
            deployment=deployment,
            character_name=character_name,
        )
        if context.trace.retrieval_mode != "contextual_fallback":
            return context
        if not self._has_continuation(payload, deployment):
            return self._strip(
                context,
                reason="contextual_fallback_blocked_no_continuity",
            )

        current_query = self._current_retrieval_query(payload)
        try:
            current_gate = self._route_decision(
                payload=payload,
                deployment=deployment,
                query=current_query,
            )
        except Exception:
            return self._strip(
                context,
                reason="contextual_fallback_blocked_current_gate_error",
            )
        weak_match = bool(
            current_gate.should_retrieve
            or current_gate.best_dense_score >= _WEAK_DENSE
            or current_gate.best_sparse_score >= _WEAK_SPARSE
        )
        if not weak_match:
            return self._strip(
                context,
                reason="contextual_fallback_blocked_current_unrelated",
            )

        contextual, count = self._contextual_retrieval_query(payload, current_query)
        signals = SemanticTurnSignalStore.get(deployment.id, payload.message_id)
        prompt = "\n".join(
            (
                f"Current message: {current_query[:2500]}",
                f"Prior context ({count}): {contextual[:2500]}",
                f"Topic present: {bool(signals and signals.topic_id)}",
                f"Continuity: {signals.continuity_reason if signals else ''}",
                f"Current dense score: {current_gate.best_dense_score:.4f}",
                f"Current sparse score: {current_gate.best_sparse_score:.4f}",
                "Does the CURRENT message genuinely require Knowledge?",
            )
        )
        try:
            judged, result = self.gateway.rag_decision(prompt=prompt)
        except UtilityGatewayUnavailable:
            return self._strip(
                context,
                reason="contextual_fallback_blocked_judge_unavailable",
            )
        updates = {
            "utility_judge_used": True,
            "utility_judge_provider": result.route.provider,
            "utility_judge_model": result.route.model,
            "utility_judge_tier": result.route.tier,
            "utility_judge_confidence": judged.confidence,
            "utility_judge_reason": judged.reason_code,
        }
        if not judged.need_knowledge or judged.confidence < _MIN_CONFIDENCE:
            return self._strip(
                context,
                reason="contextual_fallback_rejected_by_utility",
                **updates,
            )
        return CharacterTurnContext(
            smart_output=context.smart_output,
            knowledge=context.knowledge,
            trace=self._trace(context, **updates),
        )


__all__ = ["UtilityContextOrchestrator", "UtilityContextTraceView"]
