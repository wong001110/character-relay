"""Public-reader cleanup for guest-visible pages with nuisance overlays or app prompts."""

from __future__ import annotations

import re
from dataclasses import dataclass

_WHITESPACE = re.compile(r"[ \t\u00a0]+")
_NOISE_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"^(?:登录|登入|註冊|注册)(?:后|後)?(?:继续|繼續|查看|阅读|閱讀)?[\s.!！。]*$",
        r"^(?:扫码|掃碼).{0,30}(?:登录|登入|打开|打開).*$",
        r"^(?:打开|打開|下载|下載).{0,30}(?:app|客户端|客戶端).*$",
        r"^(?:前往|使用).{0,30}(?:app|客户端|客戶端).*$",
        r"^(?:立即)?(?:登录|登入|注册|註冊)[\s/|·•]*(?:注册|註冊|登录|登入)?$",
        r"^(?:sign\s*in|log\s*in|register|create\s+account)(?:\s+to\s+continue)?[\s.!]*$",
        r"^(?:open|continue|view).{0,24}\bapp\b.*$",
        r"^(?:download|get)\s+(?:the\s+)?app.*$",
        r"^(?:scan|use)\s+(?:the\s+)?qr\s+code.*$",
    )
)
_STRONG_GUEST_MARKERS = (
    "登录后继续",
    "登入後繼續",
    "登录后查看",
    "登入後查看",
    "扫码登录",
    "掃碼登入",
    "打开app",
    "打開app",
    "下载app",
    "下載app",
    "sign in to continue",
    "log in to continue",
    "open in app",
    "continue in app",
)


@dataclass(frozen=True, slots=True)
class ReaderCleanupResult:
    text: str
    state: str
    removed_line_count: int = 0


def _normalize_line(line: str) -> str:
    return _WHITESPACE.sub(" ", line).strip()


def _is_noise_line(line: str) -> bool:
    if not line or len(line) > 180:
        return False
    return any(pattern.search(line) for pattern in _NOISE_PATTERNS)


def clean_public_reader_text(text: str, *, max_chars: int = 14_000) -> ReaderCleanupResult:
    """Remove short guest/login UI lines without attempting to bypass access controls."""

    raw_lines = [_normalize_line(line) for line in text.replace("\r\n", "\n").split("\n")]
    kept: list[str] = []
    removed = 0
    seen: set[str] = set()
    for line in raw_lines:
        if not line:
            continue
        if _is_noise_line(line):
            removed += 1
            continue
        dedupe_key = line.casefold()
        if dedupe_key in seen and len(line) < 240:
            continue
        seen.add(dedupe_key)
        kept.append(line)

    cleaned = "\n".join(kept).strip()[:max_chars]
    lowered = text.casefold()
    strong_markers = sum(marker in lowered for marker in _STRONG_GUEST_MARKERS)
    meaningful_lines = sum(1 for line in kept if len(line) >= 20)
    guest_blocked = bool(
        strong_markers >= 2
        and (
            not cleaned
            or (len(cleaned) < 180 and meaningful_lines <= 1)
        )
    )
    if guest_blocked:
        return ReaderCleanupResult(text=cleaned, state="guest_blocked", removed_line_count=removed)
    if removed:
        return ReaderCleanupResult(text=cleaned, state="cleaned", removed_line_count=removed)
    return ReaderCleanupResult(text=cleaned, state="ok", removed_line_count=0)
