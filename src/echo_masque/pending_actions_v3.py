"""Standalone PendingAction lifecycle and continuation resolution for Intelligence Core v3."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from echo_masque.persistence.conversation_runtime_repository import (
    ConversationRuntimeRepository,
    PendingActionV3View,
)

ContinuationSource = Literal[
    "explicit_reply",
    "same_thread",
    "cancelled",
    "none",
]

_CONTINUE_CUES = (
    "繼續",
    "继续",
    "再試",
    "再试",
    "重試",
    "重试",
    "剛才那個",
    "刚才那个",
    "那個",
    "那个",
    "這個",
    "这个",
    "照剛才",
    "照刚才",
    "continue",
    "retry",
    "again",
    "that one",
    "the same",
    "go ahead",
    "please do",
    "yes please",
    "proceed",
)
_CANCEL_CUES = (
    "算了",
    "不用了",
    "取消",
    "別做",
    "别做",
    "停止",
    "cancel",
    "never mind",
    "nevermind",
    "stop",
)


@dataclass(frozen=True, slots=True)
class PendingActionContinuation:
    action: PendingActionV3View | None
    source: ContinuationSource
    confidence: float
    reason: str
    # The connector removes these known pending side effects from the ordinary
    # tool selection for this turn.  A rejected continuation must not fall
    # through to a semantic-selector fallback and execute the same action.
    suppressed_tool_ids: tuple[str, ...] = ()

    @property
    def tool_id(self) -> str:
        return self.action.tool_id if self.action is not None else ""

    @property
    def action_id(self) -> str:
        return self.action.id if self.action is not None else ""


class PendingActionService:
    """Resolve Tool continuation from source evidence, not Topic continuity."""

    def __init__(
        self,
        repository: ConversationRuntimeRepository,
    ) -> None:
        self.repository = repository

    def register(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        channel_id: str,
        discord_thread_id: str,
        source_message_id: str,
        source_segment_id: str,
        conversation_thread_id: str,
        requested_by_user_id: str,
        target_character_card_id: str,
        deployment_id: str,
        tool_id: str,
        intent_summary: str,
        state: str = "pending",
        expires_at: datetime | None = None,
        now: datetime | None = None,
    ) -> PendingActionV3View:
        # Connector delivery may be retried.  Keep one unresolved action for the
        # exact source task instead of creating competing continuation candidates.
        existing = self.repository.active_pending_actions(
            owner_id=owner_id,
            connection_id=connection_id,
            guild_id=guild_id,
            requested_by_user_id=requested_by_user_id,
            target_character_card_id=target_character_card_id,
            deployment_id=deployment_id,
            channel_id=channel_id,
            discord_thread_id=discord_thread_id,
            match_discord_thread_id=True,
            now=now,
            limit=20,
        )
        for item in existing:
            if item.source_message_id == source_message_id and item.tool_id == tool_id:
                return item
        return self.repository.create_pending_action(
            owner_id=owner_id,
            connection_id=connection_id,
            guild_id=guild_id,
            channel_id=channel_id,
            discord_thread_id=discord_thread_id,
            source_message_id=source_message_id,
            source_segment_id=source_segment_id,
            conversation_thread_id=conversation_thread_id,
            requested_by_user_id=requested_by_user_id,
            target_character_card_id=target_character_card_id,
            deployment_id=deployment_id,
            tool_id=tool_id,
            intent_summary=intent_summary,
            state=state,
            expires_at=expires_at,
            now=now,
            idempotency_key="|".join(
                (
                    owner_id,
                    connection_id,
                    guild_id,
                    channel_id,
                    discord_thread_id,
                    source_message_id,
                    requested_by_user_id,
                    target_character_card_id,
                    deployment_id,
                    tool_id,
                )
            ),
        )

    @staticmethod
    def _normalized(text: str) -> str:
        return " ".join(text.lower().split())[:4000]

    @classmethod
    def _has_continue_cue(cls, text: str) -> bool:
        normalized = cls._normalized(text)
        return any(cue in normalized for cue in _CONTINUE_CUES)

    @classmethod
    def _has_cancel_cue(cls, text: str) -> bool:
        normalized = cls._normalized(text)
        return any(cue in normalized for cue in _CANCEL_CUES)

    def resolve_continuation(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        current_message: str,
        requested_by_user_id: str,
        target_character_card_id: str = "",
        deployment_id: str = "",
        channel_id: str = "",
        discord_thread_id: str = "",
        reply_to_message_id: str = "",
        current_segment_id: str = "",
        conversation_thread_id: str = "",
        assigned_tool_ids: tuple[str, ...] = (),
        now: datetime | None = None,
    ) -> PendingActionContinuation:
        del current_segment_id
        current = (now or datetime.now(UTC)).astimezone(UTC)
        candidates = self.repository.active_pending_actions(
            owner_id=owner_id,
            connection_id=connection_id,
            guild_id=guild_id,
            requested_by_user_id=requested_by_user_id,
            target_character_card_id=target_character_card_id,
            deployment_id=deployment_id,
            channel_id=channel_id,
            discord_thread_id=discord_thread_id,
            match_discord_thread_id=True,
            now=current,
            limit=20,
        )
        if assigned_tool_ids:
            allowed = set(assigned_tool_ids)
            candidates = tuple(item for item in candidates if item.tool_id in allowed)
        candidate_tool_ids = tuple(dict.fromkeys(item.tool_id for item in candidates))
        if not candidates:
            return PendingActionContinuation(None, "none", 0.0, "no_active_action")
        resumable = tuple(
            item for item in candidates if item.state in {"pending", "blocked_unavailable"}
        )
        if not resumable:
            return PendingActionContinuation(
                None,
                "none",
                0.0,
                "action_execution_uncertain",
                candidate_tool_ids,
            )
        if reply_to_message_id:
            exact = tuple(
                item for item in resumable if item.source_message_id == reply_to_message_id
            )
            if len(exact) != 1:
                return PendingActionContinuation(
                    None,
                    "none",
                    0.0,
                    "reply_does_not_identify_unique_pending_action",
                    candidate_tool_ids,
                )
            action = exact[0]
            if self._has_cancel_cue(current_message):
                updated = self.repository.update_pending_action_state(
                    owner_id=owner_id,
                    action_id=action.id,
                    state="cancelled",
                    now=current,
                )
                return PendingActionContinuation(
                    updated,
                    "cancelled",
                    1.0,
                    "explicit_reply_cancel",
                    (action.tool_id,),
                )
            if not self._has_continue_cue(current_message):
                return PendingActionContinuation(
                    None,
                    "none",
                    0.0,
                    "continuation_intent_required",
                    (action.tool_id,),
                )
            return PendingActionContinuation(
                action,
                "explicit_reply",
                1.0,
                "reply_to_pending_action_source",
            )

        if not reply_to_message_id:
            same_thread = tuple(
                item
                for item in resumable
                if conversation_thread_id
                and item.conversation_thread_id == conversation_thread_id
            )
            if len(same_thread) == 1:
                action = same_thread[0]
                if self._has_cancel_cue(current_message):
                    updated = self.repository.update_pending_action_state(
                        owner_id=owner_id,
                        action_id=action.id,
                        state="cancelled",
                        now=current,
                    )
                    return PendingActionContinuation(
                        updated,
                        "cancelled",
                        1.0,
                        "same_thread_cancel",
                        (action.tool_id,),
                    )
                if not self._has_continue_cue(current_message):
                    return PendingActionContinuation(
                        None,
                        "none",
                        0.0,
                        "continuation_intent_required",
                        (action.tool_id,),
                    )
                return PendingActionContinuation(
                    action,
                    "same_thread",
                    1.0,
                    "unique_same_thread_pending_action",
                )
            return PendingActionContinuation(
                None,
                "none",
                0.0,
                "continuation_reply_required",
                candidate_tool_ids,
            )


__all__ = [
    "ContinuationSource",
    "PendingActionContinuation",
    "PendingActionService",
]
