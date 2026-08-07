"""Shared deterministic Smart Participation scoring for Portal Playground previews."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

ParticipationStyle = Literal["quiet", "balanced", "active"]
GroupRole = Literal["primary", "secondary", "independent"]

STYLE_PRESETS: dict[str, tuple[float, float]] = {
    "quiet": (0.15, 6.0),
    "balanced": (0.45, 5.0),
    "active": (0.8, 4.0),
}

LOW_INFORMATION_MESSAGES = {
    "ok",
    "okay",
    "k",
    "yes",
    "no",
    "yep",
    "nope",
    "lol",
    "lmao",
    "haha",
    "thanks",
    "thank you",
    "好的",
    "好",
    "嗯",
    "哦",
    "噢",
    "哈哈",
    "收到",
    "谢谢",
    "謝謝",
    "晚安",
    "早",
    "早安",
}

QUESTION_PHRASES = (
    "why",
    "what",
    "when",
    "where",
    "which",
    "who",
    "how",
    "can i",
    "can we",
    "could you",
    "does anyone",
    "is there",
    "为什么",
    "為什麼",
    "怎么",
    "怎麼",
    "如何",
    "谁知道",
    "誰知道",
    "能不能",
    "可不可以",
    "有没有",
    "有沒有",
)

HELP_PHRASES = (
    "help",
    "need help",
    "any idea",
    "does anyone know",
    "can someone",
    "could someone",
    "stuck",
    "not working",
    "doesn't work",
    "does not work",
    "帮忙",
    "幫忙",
    "帮我",
    "幫我",
    "有人知道",
    "卡住",
    "没反应",
    "沒反應",
    "不能用",
    "无法",
    "無法",
    "出错",
    "出錯",
)


@dataclass(frozen=True)
class ParticipationProfile:
    enabled: bool
    style: ParticipationStyle
    group_role: GroupRole
    topics: list[str]
    keywords: list[str]
    trigger_phrases: list[str]
    avoid_phrases: list[str]
    cooldown_seconds: int
    preferred_follow_up_character_card_id: str
    follow_up_window_seconds: int


@dataclass(frozen=True)
class ParticipationPreview:
    decision: Literal["participate", "silent"]
    reason: str
    score: float
    minimum_score: float
    signals: dict[str, float]
    matched_topics: list[str]
    matched_keywords: list[str]
    matched_trigger_phrases: list[str]
    matched_avoid_phrases: list[str]
    follow_up_eligible: bool
    follow_up_reason: str


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value).casefold()).strip()


def normalize_list(values: list[str]) -> list[str]:
    return list(dict.fromkeys(item for value in values if (item := normalize_text(value))))


def matched_phrases(text: str, phrases: list[str]) -> list[str]:
    return [phrase for phrase in normalize_list(phrases) if phrase in text]


def _is_question(text: str) -> bool:
    return "?" in text or "？" in text or any(item in text for item in QUESTION_PHRASES)


def _is_help_request(text: str) -> bool:
    return any(item in text for item in HELP_PHRASES)


def _is_low_information(text: str) -> bool:
    stripped = re.sub(r"[\s.,!?，。！？~～…]+", "", text).strip()
    return len(stripped) <= 16 and stripped in LOW_INFORMATION_MESSAGES


def style_values(style: str) -> tuple[float, float]:
    return STYLE_PRESETS.get(style, STYLE_PRESETS["balanced"])


def evaluate_participation(
    *,
    profile: ParticipationProfile,
    message: str,
    character_display_name: str = "",
    previous_character_card_id: str = "",
    previous_character_is_primary: bool = False,
) -> ParticipationPreview:
    initiative, minimum_score = style_values(profile.style)
    signals: dict[str, float] = {
        "question": 0.0,
        "help_request": 0.0,
        "name_match": 0.0,
        "topic_match": 0.0,
        "keyword_match": 0.0,
        "trigger_phrase": 0.0,
        "initiative": initiative,
        "short_message_penalty": 0.0,
        "avoid_phrase_blocked": 0.0,
    }
    text = normalize_text(message)
    follow_up_eligible = bool(
        profile.enabled
        and profile.group_role == "secondary"
        and previous_character_is_primary
        and previous_character_card_id
        and profile.preferred_follow_up_character_card_id == previous_character_card_id
        and profile.follow_up_window_seconds > 0
    )
    follow_up_reason = (
        "preferred_primary_match" if follow_up_eligible else "no_preferred_primary_match"
    )

    if not profile.enabled:
        return ParticipationPreview(
            decision="silent",
            reason="profile_disabled",
            score=0.0,
            minimum_score=minimum_score,
            signals=signals,
            matched_topics=[],
            matched_keywords=[],
            matched_trigger_phrases=[],
            matched_avoid_phrases=[],
            follow_up_eligible=False,
            follow_up_reason="profile_disabled",
        )
    if not text:
        return ParticipationPreview(
            decision="silent",
            reason="empty_message",
            score=0.0,
            minimum_score=minimum_score,
            signals=signals,
            matched_topics=[],
            matched_keywords=[],
            matched_trigger_phrases=[],
            matched_avoid_phrases=[],
            follow_up_eligible=follow_up_eligible,
            follow_up_reason=follow_up_reason,
        )
    if _is_low_information(text):
        return ParticipationPreview(
            decision="silent",
            reason="low_information_message",
            score=initiative,
            minimum_score=minimum_score,
            signals=signals,
            matched_topics=[],
            matched_keywords=[],
            matched_trigger_phrases=[],
            matched_avoid_phrases=[],
            follow_up_eligible=follow_up_eligible,
            follow_up_reason=follow_up_reason,
        )

    matched_avoid = matched_phrases(text, profile.avoid_phrases)
    if matched_avoid:
        signals["avoid_phrase_blocked"] = 1.0
        return ParticipationPreview(
            decision="silent",
            reason="avoid_phrase",
            score=0.0,
            minimum_score=minimum_score,
            signals=signals,
            matched_topics=[],
            matched_keywords=[],
            matched_trigger_phrases=[],
            matched_avoid_phrases=matched_avoid,
            follow_up_eligible=False,
            follow_up_reason="avoid_phrase",
        )

    matched_topics = matched_phrases(text, profile.topics)
    matched_keywords = matched_phrases(text, profile.keywords)
    matched_triggers = matched_phrases(text, profile.trigger_phrases)
    display_name = normalize_text(character_display_name)

    signals["question"] = 2.0 if _is_question(text) else 0.0
    signals["help_request"] = 2.0 if _is_help_request(text) else 0.0
    signals["name_match"] = 5.0 if display_name and display_name in text else 0.0
    signals["topic_match"] = float(min(6, len(matched_topics) * 3))
    signals["keyword_match"] = float(min(6, len(matched_keywords) * 2))
    signals["trigger_phrase"] = float(min(4, len(matched_triggers) * 2))
    signals["short_message_penalty"] = -2.0 if len(text) < 4 else 0.0
    score = round(sum(signals.values()), 3)
    decision: Literal["participate", "silent"] = (
        "participate" if score >= minimum_score else "silent"
    )
    reason = "selected" if decision == "participate" else "below_threshold"
    return ParticipationPreview(
        decision=decision,
        reason=reason,
        score=score,
        minimum_score=minimum_score,
        signals=signals,
        matched_topics=matched_topics,
        matched_keywords=matched_keywords,
        matched_trigger_phrases=matched_triggers,
        matched_avoid_phrases=[],
        follow_up_eligible=follow_up_eligible,
        follow_up_reason=follow_up_reason,
    )
