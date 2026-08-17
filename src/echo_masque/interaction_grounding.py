"""Cheap conversational-pragmatics grounding before Character roleplay generation.

Semantic relevance answers whether a Character is related to a topic. This module answers a
separate question: how is the latest group-chat message socially addressed? It is intentionally
deterministic for common cases so profession/background relevance cannot by itself become an
interview, accusation, challenge, or request for professional advice.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from echo_masque.api.connector_schemas import DiscordInboundMessage

InteractionAudience = Literal[
    "direct_character",
    "group_invited",
    "ambient",
    "role_group_directed",
    "ambiguous",
]
InteractionType = Literal[
    "direct_request",
    "direct_challenge",
    "group_request",
    "casual_discussion",
    "role_group_discussion",
    "ambiguous",
]
ResponsePosture = Literal[
    "informed_response",
    "respond_to_challenge",
    "group_participant",
    "casual_peer",
    "role_peer",
    "cautious_peer",
]

_GROUP_INVITATION = re.compile(
    r"(?:大家|各位|你们|你們|所有人|全部人|全员|全員|everyone|everybody|you\s+all|all\s+of\s+you)",
    re.IGNORECASE,
)
_QUESTION = re.compile(
    r"(?:\?|？|为什么|為什麼|怎么|怎麼|如何|能不能|可不可以|有没有|有沒有|"
    r"\bwhy\b|\bwhat\b|\bhow\b|\bcan\b|\bcould\b|\bwould\b|\bshould\b)",
    re.IGNORECASE,
)
_CHALLENGE = re.compile(
    r"(?:不是你说|不是你說|你刚才说|你剛才說|你不是说|你不是說|怎么解释|怎麼解釋|"
    r"凭什么|憑什麼|你确定|你確定|\byou\s+said\b|\bdidn['’]?t\s+you\s+say\b|"
    r"\bhow\s+do\s+you\s+explain\b|\bare\s+you\s+sure\b)",
    re.IGNORECASE,
)
_ROLE_GROUP_DIRECTION = re.compile(
    r"(?:你们这些|你們這些|你们做|你們做|你们当|你們當|做.+的|当.+的|當.+的|"
    r"people\s+in|those\s+of\s+you|you\s+(?:developers|engineers|lawyers|doctors|designers))",
    re.IGNORECASE,
)
_TOKEN = re.compile(r"[\w\u3400-\u9fff]+", re.UNICODE)


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def _role_terms(role_hint: str) -> tuple[str, ...]:
    normalized = _normalize(role_hint)
    terms = [item for item in _TOKEN.findall(normalized) if len(item) >= 2]
    # Full subtitle catches exact multilingual profession labels; individual terms catch common
    # English descriptions such as "senior software engineer".
    values = [normalized] if normalized else []
    values.extend(item for item in terms if item not in values)
    return tuple(values[:8])


def _name_addressed(text: str, character_name: str) -> bool:
    name = _normalize(character_name)
    if not name:
        return False
    normalized = _normalize(text)
    position = normalized.find(name)
    if position < 0:
        return False
    tail = normalized[position + len(name) : position + len(name) + 4]
    head = normalized[max(0, position - 2) : position]
    # Prefer vocative punctuation/placement. A bare name embedded in a factual sentence should not
    # automatically turn ambient discussion into a direct interrogation.
    return position == 0 or any(mark in tail for mark in (",", "，", ":", "：", "?", "？")) or "@" in head


def _role_relevant(text: str, role_hint: str) -> bool:
    normalized = _normalize(text)
    return any(term and term in normalized for term in _role_terms(role_hint))


@dataclass(frozen=True, slots=True)
class InteractionGrounding:
    audience: InteractionAudience
    interaction_type: InteractionType
    directed_at_character: bool
    expertise_relevant: bool
    expertise_requested: bool
    response_posture: ResponsePosture
    confidence: float
    reason: str

    def prompt_guidance(self) -> tuple[str, ...]:
        common = (
            "Conversation grounding is runtime context, not Character identity.",
            (
                "Topic relevance or professional background alone does NOT mean the latest "
                "message is addressed to you, questions your competence, or requests professional advice."
            ),
            f"Audience: {self.audience}; interaction: {self.interaction_type}; response posture: {self.response_posture}.",
        )
        if self.audience == "ambient":
            return (
                *common,
                (
                    "This is ambient group discussion. If you speak, join as a peer in the room. "
                    "Do not answer as if you are being interviewed, examined, accused, challenged, "
                    "or formally consulted unless the visible conversation actually establishes that."
                ),
            )
        if self.audience == "group_invited":
            return (*common, "The group was invited to respond; contribute as one participant, not as the sole addressee.")
        if self.audience == "role_group_directed":
            return (
                *common,
                (
                    "The message appears directed at people sharing a role/background. You may answer from that "
                    "perspective, but do not assume a personal accusation or one-to-one consultation."
                ),
            )
        if self.interaction_type == "direct_challenge":
            return (*common, "The latest message directly challenges or asks you to account for a prior position; respond to that challenge naturally.")
        if self.audience == "direct_character":
            return (*common, "The latest message is directly addressed to you; answer according to the visible request and your persona.")
        return (*common, "Address is ambiguous. Avoid assuming hostility, interrogation, or professional consultation without stronger evidence.")


def ground_interaction(
    *,
    payload: DiscordInboundMessage,
    character_name: str,
    role_hint: str = "",
) -> InteractionGrounding:
    """Resolve common group-chat address modes without an LLM call."""

    text = payload.text.strip()
    question = bool(_QUESTION.search(text))
    role_relevant = _role_relevant(text, role_hint)
    explicit_direct = bool(
        payload.mentioned_bot
        or payload.replied_to_bot
        or _name_addressed(text, character_name)
    )
    if explicit_direct:
        challenged = bool(_CHALLENGE.search(text))
        return InteractionGrounding(
            audience="direct_character",
            interaction_type="direct_challenge" if challenged else "direct_request",
            directed_at_character=True,
            expertise_relevant=role_relevant,
            expertise_requested=bool(role_relevant and question),
            response_posture="respond_to_challenge" if challenged else "informed_response",
            confidence=0.98 if payload.mentioned_bot or payload.replied_to_bot else 0.9,
            reason=(
                "platform_direct_address"
                if payload.mentioned_bot or payload.replied_to_bot
                else "character_name_address"
            ),
        )

    if _GROUP_INVITATION.search(text):
        return InteractionGrounding(
            audience="group_invited",
            interaction_type="group_request",
            directed_at_character=False,
            expertise_relevant=role_relevant,
            expertise_requested=bool(role_relevant and question),
            response_posture="group_participant",
            confidence=0.94,
            reason="explicit_group_invitation",
        )

    if role_relevant and _ROLE_GROUP_DIRECTION.search(text):
        return InteractionGrounding(
            audience="role_group_directed",
            interaction_type="role_group_discussion",
            directed_at_character=False,
            expertise_relevant=True,
            expertise_requested=question,
            response_posture="role_peer",
            confidence=0.82,
            reason="role_group_address",
        )

    # A question about a relevant profession is still ambient unless the message addresses the
    # Character or that profession group. E5/Smart Participation may decide the Character is a good
    # participant; this layer prevents that semantic match from becoming a false direct address.
    return InteractionGrounding(
        audience="ambient",
        interaction_type="casual_discussion",
        directed_at_character=False,
        expertise_relevant=role_relevant,
        expertise_requested=False,
        response_posture="casual_peer",
        confidence=0.9 if text else 0.75,
        reason="no_direct_address_evidence",
    )


__all__ = [
    "InteractionAudience",
    "InteractionGrounding",
    "InteractionType",
    "ResponsePosture",
    "ground_interaction",
]
