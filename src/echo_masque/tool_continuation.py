"""Semantic side-effect Tool intent and standalone PendingAction v3 continuation planning."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from echo_masque.config import Settings, get_settings
from echo_masque.persistence.conversation_runtime_repository import (
    ConversationRuntimeRepository,
    PendingActionV3View,
)
from echo_masque.persistence.conversation_structure_repository import (
    ConversationStructureRepository,
)
from echo_masque.persistence.repository import Repository
from echo_masque.prompt_budget import _explicit_intent, _tool_encoder
from echo_masque.semantic_participation import (
    SemanticEmbeddingUnavailable,
    SemanticEncoder,
    _cosine,
)
from echo_masque.services.runtime import RuntimeService
from echo_masque.utility_gateway_contracts import (
    ToolContinuationUtilityDecision,
    UtilityGatewayUnavailable,
)
from echo_masque.utility_gateway_live import ExistingProviderUtilityCaller
from echo_masque.utility_gateway_router import UtilityGatewayRouter

if TYPE_CHECKING:
    from echo_masque.api.connector_schemas import DiscordInboundMessage

_SIDE_EFFECT_INTENT_MINIMUM = 0.50
_SIDE_EFFECT_INTENT_MAX_SELECTED = 2
_CONTINUATION_ACT_MINIMUM = 0.48
_UTILITY_CONTINUATION_FLOOR = 0.28
_UTILITY_CONTINUATION_CONFIDENCE = 0.72

_SIDE_EFFECT_PROFILES: dict[str, str] = {
    "discord.create_poll": (
        "Create, start, or open a Discord poll or vote with choices for the group. "
        "Examples: create a poll, let everyone vote, 开个投票, 建立投票."
    ),
    "scheduler.remind": (
        "Create a future reminder or notification for the user. Examples: remind me later, "
        "notify me tomorrow, 提醒我, 到时候叫我."
    ),
    "scheduler.cancel": (
        "Cancel or remove an existing scheduled reminder. Examples: cancel that reminder, "
        "取消提醒, 删除那个提醒."
    ),
    "watch.condition": (
        "Create a persistent future condition watch and notify when a condition becomes true. "
        "Examples: tell me when it is available, monitor until it changes, 有了就通知我."
    ),
    "image.generate": (
        "Generate, create, draw, or make a new image, picture, illustration, artwork, avatar, "
        "or visual and share the generated result. Examples: generate a cat image, draw this, "
        "生成一张猫图, 画个头像."
    ),
}

_TOOL_INTENT_VECTOR_CACHE: dict[tuple[str, int, str], list[float]] = {}


@dataclass(frozen=True, slots=True)
class PendingActionContinuationEvidence:
    """One pending action that needs only a gray-zone continuation decision."""

    action_id: str
    tool_id: str
    current_message: str
    conversation_thread_id: str
    pending_intent_summary: str
    pending_source_message_id: str
    continuation_strength: float


@dataclass(frozen=True, slots=True)
class ToolContinuationPlan:
    """Turn-local Tool relevance derived from standalone pending-action evidence."""

    conversation_thread_id: str = ""
    continuation_tool_ids: tuple[str, ...] = ()
    detected_side_effect_intents: tuple[str, ...] = ()
    blocked_side_effect_intents: tuple[str, ...] = ()
    continuity_reason: str = ""
    retry_score: float = 0.0
    pending_action_evidence: PendingActionContinuationEvidence | None = None


def detect_side_effect_tool_intents(
    query: str,
    *,
    settings: Settings | None = None,
    encoder: SemanticEncoder | None = None,
) -> tuple[str, ...]:
    """Detect side-effect intent before Deployment assignment is considered."""

    normalized = " ".join(query.split())[:4000]
    if not normalized:
        return ()
    forced = [
        tool_id for tool_id in _SIDE_EFFECT_PROFILES if _explicit_intent(tool_id, normalized)
    ]
    resolved = settings or get_settings()
    if not resolved.semantic_embedding_runtime_enabled:
        return tuple(forced[:_SIDE_EFFECT_INTENT_MAX_SELECTED])

    try:
        active_encoder = encoder or _tool_encoder(resolved)
        query_vector = active_encoder.embed_query(normalized)
    except (SemanticEmbeddingUnavailable, ValueError, RuntimeError):
        return tuple(forced[:_SIDE_EFFECT_INTENT_MAX_SELECTED])

    scored: list[tuple[float, str]] = []
    for tool_id, semantic_text in _SIDE_EFFECT_PROFILES.items():
        cache_key = (active_encoder.model_name, active_encoder.dimension, tool_id)
        vector = _TOOL_INTENT_VECTOR_CACHE.get(cache_key)
        if vector is None:
            try:
                vector = active_encoder.embed_passage(semantic_text)
            except (SemanticEmbeddingUnavailable, ValueError, RuntimeError):
                continue
            _TOOL_INTENT_VECTOR_CACHE[cache_key] = vector
        score = _cosine(query_vector, vector)
        if score >= _SIDE_EFFECT_INTENT_MINIMUM:
            scored.append((score, tool_id))

    scored.sort(key=lambda value: (-value[0], value[1]))
    selected = list(dict.fromkeys(forced))
    for _, tool_id in scored:
        if tool_id not in selected:
            selected.append(tool_id)
        if len(selected) >= _SIDE_EFFECT_INTENT_MAX_SELECTED:
            break
    return tuple(selected[:_SIDE_EFFECT_INTENT_MAX_SELECTED])


class ToolContinuationService:
    """Resolve PendingAction continuation without granting Tool execution authority."""

    def __init__(
        self,
        runtime: ConversationRuntimeRepository,
        structure: ConversationStructureRepository | None = None,
        *,
        settings: Settings | None = None,
        encoder: SemanticEncoder | None = None,
        utility_gateway: UtilityGatewayRouter | None = None,
    ) -> None:
        self.runtime = runtime
        self.structure = structure or ConversationStructureRepository(runtime.database)
        self.settings = settings or get_settings()
        self.encoder = encoder
        self._utility_gateway_override = utility_gateway
        self._utility_gateway_live: UtilityGatewayRouter | None = None

    def _encoder(self) -> SemanticEncoder:
        if self.encoder is None:
            self.encoder = _tool_encoder(self.settings)
        return self.encoder

    def _continuation_strength(self, current_message: str, action: PendingActionV3View) -> float:
        normalized = " ".join(current_message.split())[:2400]
        pending = " ".join(action.intent_summary.split())[:1200]
        if not normalized or not pending:
            return 0.0
        if _explicit_intent(action.tool_id, normalized):
            return 0.95
        if not self.settings.semantic_embedding_runtime_enabled:
            return 0.0
        try:
            encoder = self._encoder()
            return max(0.0, _cosine(encoder.embed_query(normalized), encoder.embed_passage(pending)))
        except (SemanticEmbeddingUnavailable, ValueError, RuntimeError):
            return 0.0

    def _current_structure(
        self,
        *,
        owner_id: str,
        payload: DiscordInboundMessage,
    ) -> tuple[str, str]:
        recent = self.structure.recent_segments(
            owner_id=owner_id,
            connection_id=payload.connection_id,
            guild_id=payload.guild_id,
            limit=80,
        )
        segment = next(
            (item for item in recent if payload.message_id in item.message_ids),
            None,
        )
        if segment is None:
            return "", ""
        membership = self.structure.current_membership(
            owner_id=owner_id,
            segment_id=segment.id,
        )
        return segment.id, membership.thread_id if membership is not None else ""

    def pending_action_evidence(
        self,
        *,
        payload: DiscordInboundMessage,
        action: PendingActionV3View,
        continuation_strength: float,
        current_thread_id: str,
    ) -> PendingActionContinuationEvidence | None:
        if not (_UTILITY_CONTINUATION_FLOOR <= continuation_strength < _CONTINUATION_ACT_MINIMUM):
            return None
        if (
            current_thread_id
            and action.conversation_thread_id
            and current_thread_id != action.conversation_thread_id
        ):
            return None
        return PendingActionContinuationEvidence(
            action_id=action.id,
            tool_id=action.tool_id,
            current_message=payload.text[:2200],
            conversation_thread_id=current_thread_id or action.conversation_thread_id,
            pending_intent_summary=action.intent_summary[:500],
            pending_source_message_id=action.source_message_id[:200],
            continuation_strength=round(continuation_strength, 6),
        )

    def _utility_gateway(self) -> UtilityGatewayRouter:
        if self._utility_gateway_override is not None:
            return self._utility_gateway_override
        if self._utility_gateway_live is None:
            runtime = RuntimeService(Repository(self.runtime.database), self.settings)
            self._utility_gateway_live = UtilityGatewayRouter(
                runtime,
                caller=ExistingProviderUtilityCaller(),
            )
        return self._utility_gateway_live

    @staticmethod
    def _capability_enabled(gateway: object) -> bool:
        runtime = getattr(gateway, "runtime", None)
        if runtime is None:
            return True
        config = runtime.config().utility_gateway
        return bool(
            config.enabled
            and any(
                member.enabled and "tool_continuation" in member.capabilities
                for member in config.members
            )
        )

    def resolve_pending_action_evidence(
        self,
        evidence: PendingActionContinuationEvidence,
    ) -> str:
        """Apply Utility only to one pre-bounded ambiguous PendingAction candidate."""

        gateway = self._utility_gateway()
        if not self._capability_enabled(gateway):
            return ""
        prompt = "\n".join(
            (
                f"Current message: {evidence.current_message}",
                f"Conversation thread id: {evidence.conversation_thread_id}",
                f"Pending tool id: {evidence.tool_id}",
                f"Pending intent: {evidence.pending_intent_summary}",
                f"Pending source message: {evidence.pending_source_message_id}",
                f"Continuation score: {evidence.continuation_strength:.4f}",
                "Decide only whether the current message continues this exact pending action.",
            )
        )
        try:
            value, _ = gateway.tool_continuation_decision(prompt=prompt)
        except UtilityGatewayUnavailable:
            return ""
        if (
            not value.continue_action
            or value.tool_id != evidence.tool_id
            or value.confidence < _UTILITY_CONTINUATION_CONFIDENCE
        ):
            return ""
        return evidence.tool_id

    def plan_turn(
        self,
        *,
        owner_id: str,
        payload: DiscordInboundMessage,
        character_card_id: str,
        deployment_id: str,
        assigned_tool_ids: tuple[str, ...],
        defer_utility: bool = False,
    ) -> ToolContinuationPlan:
        """Persist blocked requests and expose scoped continuation candidates."""

        current_segment_id, current_thread_id = self._current_structure(
            owner_id=owner_id,
            payload=payload,
        )
        detected: tuple[str, ...] = ()
        if not payload.author_is_bot:
            detected = detect_side_effect_tool_intents(
                payload.text,
                settings=self.settings,
                encoder=self.encoder,
            )
        assigned = set(assigned_tool_ids)
        pending_before = self.runtime.active_pending_actions(
            owner_id=owner_id,
            connection_id=payload.connection_id,
            guild_id=payload.guild_id,
            requested_by_user_id=payload.author_id,
            target_character_card_id=character_card_id,
            deployment_id=deployment_id,
            limit=20,
        )

        blocked: list[str] = []
        if not payload.author_is_bot:
            for tool_id in detected:
                if tool_id in assigned:
                    continue
                blocked.append(tool_id)
                self.runtime.create_pending_action(
                    owner_id=owner_id,
                    connection_id=payload.connection_id,
                    guild_id=payload.guild_id,
                    channel_id=payload.channel_id,
                    discord_thread_id=payload.thread_id,
                    source_message_id=payload.message_id,
                    source_segment_id=current_segment_id,
                    conversation_thread_id=current_thread_id,
                    requested_by_user_id=payload.author_id,
                    target_character_card_id=character_card_id,
                    deployment_id=deployment_id,
                    tool_id=tool_id,
                    intent_summary=payload.text,
                    state="blocked_unavailable",
                )

        continuation_ids: list[str] = []
        deferred_evidence: PendingActionContinuationEvidence | None = None
        utility_selected = False
        retry_score = 0.0
        eligible = [item for item in pending_before if item.tool_id in assigned]
        if not payload.author_is_bot:
            explicit_reply = [
                item
                for item in eligible
                if payload.reply_to_message_id
                and item.source_message_id == payload.reply_to_message_id
            ]
            if explicit_reply:
                continuation_ids.extend(item.tool_id for item in explicit_reply)
                retry_score = 1.0
            else:
                ranked: list[tuple[float, PendingActionV3View]] = []
                for action in eligible:
                    if (
                        current_thread_id
                        and action.conversation_thread_id
                        and current_thread_id != action.conversation_thread_id
                    ):
                        continue
                    strength = self._continuation_strength(payload.text, action)
                    ranked.append((strength, action))
                ranked.sort(key=lambda item: (-item[0], item[1].updated_at), reverse=False)
                if ranked:
                    strength, action = ranked[0]
                    retry_score = round(strength, 6)
                    if strength >= _CONTINUATION_ACT_MINIMUM:
                        continuation_ids.append(action.tool_id)
                    elif len(ranked) == 1:
                        evidence = self.pending_action_evidence(
                            payload=payload,
                            action=action,
                            continuation_strength=strength,
                            current_thread_id=current_thread_id,
                        )
                        if evidence is not None and defer_utility:
                            deferred_evidence = evidence
                        elif evidence is not None:
                            utility_tool_id = self.resolve_pending_action_evidence(evidence)
                            if utility_tool_id:
                                continuation_ids.append(utility_tool_id)
                                utility_selected = True

        if utility_selected:
            reason = "utility_tool_continuation"
        elif deferred_evidence is not None:
            reason = "pending_action_gray_zone"
        elif continuation_ids and payload.reply_to_message_id:
            reason = "explicit_reply_to_pending_action"
        elif continuation_ids:
            reason = "pending_action_semantic_continuation"
        elif pending_before:
            reason = "pending_action_not_continued"
        else:
            reason = ""

        return ToolContinuationPlan(
            conversation_thread_id=current_thread_id,
            continuation_tool_ids=tuple(dict.fromkeys(continuation_ids)),
            detected_side_effect_intents=detected,
            blocked_side_effect_intents=tuple(blocked),
            continuity_reason=reason,
            retry_score=retry_score,
            pending_action_evidence=deferred_evidence,
        )


__all__ = [
    "PendingActionContinuationEvidence",
    "ToolContinuationPlan",
    "ToolContinuationService",
    "detect_side_effect_tool_intents",
]
