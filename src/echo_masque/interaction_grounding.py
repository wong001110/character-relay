"""Cheap conversational-pragmatics grounding before Character roleplay generation.

Semantic relevance answers whether a Character is related to a topic. This module answers a
separate question: how is the latest group-chat message socially addressed? It is intentionally
conservative: ambiguous conversational semantics should remain revisable by the Character model
instead of being promoted into a strong interrogation/challenge posture by a cheap heuristic.
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
_GROUP_ACTION_REQUEST = re.compile(
    r"(?:大家|各位|你们|你們|everyone|everybody|you\s+all).{0,12}"
    r"(?:帮|幫|看看|看一下|说说|說說|聊聊|告诉|告訴|试试|試試|"
    r"please|take\s+a\s+look|tell\s+me|share|try)",
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
_QUOTED_SPAN = re.compile(
    r'(?:"[^"\n]*"|“[^”\n]*”|「[^」\n]*」|『[^』\n]*』|‘[^’\n]*’|\'[^\'\n]*\')'
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
    """Recognize a real name address without prefix-matching longer words/names."""

    name = _normalize(character_name)
    if not name:
        return False
    normalized = _normalize(text)
    match = re.search(
        rf"(?<![\w\u3400-\u9fff])@?{re.escape(name)}(?![\w\u3400-\u9fff])",
        normalized,
        re.IGNORECASE,
    )
    if match is None:
        return False
    position = match.start()
    tail = normalized[match.end() : match.end() + 4]
    head = normalized[max(0, position - 2) : position]
    # Prefer vocative punctuation/placement. A bare name embedded in a factual sentence should not
    # automatically turn ambient discussion into a direct interrogation.
    return (
        position == 0
        or any(mark in tail for mark in (",", "，", ":", "：", "?", "？"))
        or "@" in match.group(0)
        or "@" in head
    )


def _role_relevant(text: str, role_hint: str) -> bool:
    normalized = _normalize(text)
    return any(term and term in normalized for term in _role_terms(role_hint))


def _unquoted_text(text: str) -> str:
    """Remove common quoted spans before applying strong conversational-act heuristics."""

    return _QUOTED_SPAN.sub(" ", text)


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
            return (
                *common,
                "Visible, unquoted text appears to challenge a prior position. Respond to the visible evidence only; do not infer hostility beyond it.",
            )
        if self.audience == "direct_character":
            return (*common, "The latest message is directly addressed to you; answer according to the visible request and your persona.")
        return (*common, "Address is ambiguous. Avoid assuming hostility, interrogation, or professional consultation without stronger evidence.")


def ground_interaction(
    *,
    payload: DiscordInboundMessage,
    character_name: str,
    role_hint: str = "",
) -> InteractionGrounding:
    """Resolve high-confidence group-chat address modes without an LLM call."""

    text = payload.text.strip()
    unquoted_text = _unquoted_text(text)
    question = bool(_QUESTION.search(unquoted_text))
    role_relevant = _role_relevant(text, role_hint)
    explicit_direct = bool(
        payload.mentioned_bot
        or payload.replied_to_bot
        or _name_addressed(text, character_name)
    )
    if explicit_direct:
        # Challenge is intentionally evaluated only over the speaker's own visible words. A quoted
        # "are you sure?" should not force a defensive posture merely because the Character is the
        # addressee of the surrounding message.
        challenged = bool(_CHALLENGE.search(unquoted_text))
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

    # A profession/group-qualified "you all" is more specific than a generic group invitation.
    if role_relevant and _ROLE_GROUP_DIRECTION.search(unquoted_text):
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

    # A broad group word is not enough. Declarative text such as "大家都下線了" is ambient; the
    # group must also be asked a question or receive an explicit action request.
    if _GROUP_INVITATION.search(unquoted_text) and (
        question or _GROUP_ACTION_REQUEST.search(unquoted_text)
    ):
        return InteractionGrounding(
            audience="group_invited",
            interaction_type="group_request",
            directed_at_character=False,
            expertise_relevant=role_relevant,
            expertise_requested=bool(role_relevant and question),
            response_posture="group_participant",
            confidence=0.92,
            reason="explicit_group_invitation",
        )

    # A question about a relevant profession is still ambient unless the message addresses the
    # Character or that profession group. Smart Participation may decide the Character is a good
    # candidate; this layer must not promote relevance into a false direct address.
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
