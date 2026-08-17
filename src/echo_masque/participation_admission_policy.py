"""Dynamic admission limits for multi-character Smart Participation turns."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

_EMERGENCY_HARD_CAP = 10
_GROUP_INVITATION_PATTERN = re.compile(
    r"(?:"
    r"大家|各位|你们|你們|所有人|全部人|全员|全員|大家都|你们都|你們都|"
    r"everyone|everybody|all\s+of\s+you|you\s+all|what\s+do\s+you\s+all\s+think"
    r")",
    re.IGNORECASE,
)


class BurstMessageLike(Protocol):
    text: str


@dataclass(frozen=True, slots=True)
class AdmissionLimitDecision:
    """Effective per-turn participant limit with a traceable policy reason."""

    limit: int
    reason: str
    group_invitation: bool
    candidate_count: int
    burst_message_count: int
    analysis_chars: int


def _analysis_text(message: str, burst_messages: Sequence[BurstMessageLike]) -> str:
    parts = [item.text.strip() for item in burst_messages if item.text.strip()]
    if not parts and message.strip():
        parts.append(message.strip())
    return "\n".join(parts)[:12_000]


def resolve_admission_limit(
    *,
    message: str,
    burst_messages: Sequence[BurstMessageLike],
    eligible_candidate_count: int,
    requested_max: int,
    emergency_hard_cap: int = _EMERGENCY_HARD_CAP,
) -> AdmissionLimitDecision:
    """Resolve a soft conversational cap without making it a structural data-model limit."""

    hard_cap = max(1, min(emergency_hard_cap, _EMERGENCY_HARD_CAP))
    candidates = max(0, eligible_candidate_count)
    available = min(candidates, hard_cap)
    text = _analysis_text(message, burst_messages)
    burst_count = max(1, len([item for item in burst_messages if item.text.strip()]))
    analysis_chars = len(text)
    group_invitation = bool(_GROUP_INVITATION_PATTERN.search(text))

    if available <= 0:
        return AdmissionLimitDecision(
            limit=1,
            reason="no_eligible_candidates",
            group_invitation=group_invitation,
            candidate_count=candidates,
            burst_message_count=burst_count,
            analysis_chars=analysis_chars,
        )

    requested = max(1, min(requested_max, available))
    if group_invitation:
        return AdmissionLimitDecision(
            limit=available,
            reason="explicit_group_invitation",
            group_invitation=True,
            candidate_count=candidates,
            burst_message_count=burst_count,
            analysis_chars=analysis_chars,
        )

    # The soft cap expands only when the current conversational burst is meaningfully active.
    # These thresholds are product tuning, not architecture limits; the emergency cap remains
    # the only last-resort protection against accidental all-bot floods.
    if burst_count >= 4 or analysis_chars >= 900:
        soft_limit = 6
        reason = "high_conversation_intensity"
    elif burst_count >= 3 or analysis_chars >= 500:
        soft_limit = 4
        reason = "active_conversation"
    elif burst_count >= 2 or analysis_chars >= 250:
        soft_limit = 3
        reason = "multi_message_conversation"
    else:
        soft_limit = 2
        reason = "normal_conversation"

    return AdmissionLimitDecision(
        limit=min(available, max(requested, soft_limit)),
        reason=reason,
        group_invitation=False,
        candidate_count=candidates,
        burst_message_count=burst_count,
        analysis_chars=analysis_chars,
    )


__all__ = ["AdmissionLimitDecision", "resolve_admission_limit"]
