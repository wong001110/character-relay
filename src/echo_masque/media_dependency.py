"""Runtime-owned media dependency classification for Character turns.

The Character model may decide whether optional shared content interests it, but it must not
answer questions that epistemically require unseen media. Deterministic rules lock obvious
REQUIRED/NONE cases; ambiguous cases stay OPTIONAL and may be refined by Conversation
Intelligence without downgrading a locked REQUIRED decision.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

MediaDependency = Literal["required", "optional", "none"]

_REQUIRED_PATTERNS = (
    re.compile(
        r"(?:看(?:看|一下)?|读|讀|打开|打開|检查|檢查|分析|总结|總結).{0,16}"
        r"(?:这个|這個|视频|影片|gif|GIF|链接|連結|图片|圖片|照片|附件|media|video|link|image)",
        re.I,
    ),
    re.compile(
        r"(?:这个|這個|视频|影片|gif|GIF|链接|連結|图片|圖片|照片|附件|里面|裡面).{0,24}"
        r"(?:讲了什么|講了什麼|说了什么|說了什麼|是什么|是什麼|写了什么|寫了什麼|做什么|做什麼|"
        r"在做什么|在做什麼|干嘛|幹嘛|干吗|幹嗎|"
        r"内容|內容|总结|總結|分析|谁|誰|哪里|哪裡|为什么|為什麼)",
        re.I,
    ),
    re.compile(
        r"(?:what(?:'s|\s+is)?\s+(?:in|on)|what\s+does|summari[sz]e|inspect|open|read|analy[sz]e)"
        r".{0,24}(?:video|image|gif|link|attachment|media|clip|page)",
        re.I,
    ),
    re.compile(
        r"(?:video|image|gif|link|attachment|media|clip|page).{0,24}"
        r"(?:say|show|contain|about|mean|summari[sz]e|explain)",
        re.I,
    ),
)
_NONE_PATTERNS = (
    re.compile(r"(?:不用|不必|别|別|不要).{0,12}(?:看|打开|打開|读|讀|分析|检查|檢查)", re.I),
    re.compile(
        r"(?:do\s+not|don't|dont|no\s+need\s+to).{0,16}"
        r"(?:open|read|inspect|watch|analy[sz]e)",
        re.I,
    ),
)


@dataclass(frozen=True, slots=True)
class MediaDependencyDecision:
    dependency: MediaDependency
    reason: str
    locked: bool
    utility_refinement_allowed: bool


def resolve_media_dependency(*, text: str, has_media: bool) -> MediaDependencyDecision:
    """Classify whether the response requires media content before Character generation."""

    if not has_media:
        return MediaDependencyDecision("none", "no_shared_media", True, False)
    compact = " ".join(text.split())[:4000]
    if compact and any(pattern.search(compact) for pattern in _NONE_PATTERNS):
        return MediaDependencyDecision("none", "explicit_do_not_inspect", True, False)
    if compact and any(pattern.search(compact) for pattern in _REQUIRED_PATTERNS):
        return MediaDependencyDecision("required", "explicit_media_content_request", True, False)
    return MediaDependencyDecision("optional", "media_interest_or_relevance_gray_zone", False, True)


def apply_utility_media_dependency(
    deterministic: MediaDependencyDecision,
    proposed: MediaDependency,
) -> MediaDependencyDecision:
    """Apply a Utility refinement without weakening Runtime-locked epistemic boundaries."""

    if deterministic.locked:
        return deterministic
    if proposed not in {"required", "optional", "none"}:
        return deterministic
    return MediaDependencyDecision(
        proposed,
        "utility_gray_zone_refinement",
        False,
        True,
    )


__all__ = [
    "MediaDependency",
    "MediaDependencyDecision",
    "apply_utility_media_dependency",
    "resolve_media_dependency",
]
