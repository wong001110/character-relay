"""Persona-driven attention gate for shared Discord media and links."""

from __future__ import annotations

import json
import re
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from echo_masque.api.connector_schemas import DiscordInboundMessage
from echo_masque.content_resolver import resolve_static_url
from echo_masque.providers import ChatMessage
from echo_masque.targets import PromptModelTarget

_URL_PATTERN = re.compile(r"https?://[^\s<>\]\[(){}\"']+", re.IGNORECASE)
_ATTENTION_MARKER = "[MEDIA_ATTENTION]"
_MAX_PREVIEW_LINES = 8
_MAX_RECENT_MESSAGES = 6


class MediaAttentionDecision(BaseModel):
    """Private Character decision made before any expensive content understanding."""

    model_config = ConfigDict(frozen=True)

    action: Literal["watch", "skip"]
    reason: str = Field(default="", max_length=300)


class MediaAttentionDecider(Protocol):
    async def decide(
        self,
        *,
        target: PromptModelTarget,
        payload: DiscordInboundMessage,
    ) -> MediaAttentionDecision: ...


def media_preview_lines(payload: DiscordInboundMessage) -> tuple[str, ...]:
    """Build only information a Discord member could see before opening the content."""

    lines: list[str] = []
    for item in payload.attachments[:4]:
        kind = "media"
        content_type = item.content_type.casefold()
        if content_type.startswith("image/"):
            kind = "image"
        elif content_type.startswith("video/"):
            kind = "video"
        size = f", {item.size_bytes} bytes" if item.size_bytes is not None else ""
        dimensions = (
            f", {item.width}x{item.height}"
            if item.width is not None and item.height is not None
            else ""
        )
        lines.append(f"Discord {kind} attachment: {item.filename}{size}{dimensions}")

    for embed in payload.embeds[:4]:
        parts = [value.strip() for value in (embed.provider_name, embed.title) if value.strip()]
        label = " / ".join(parts) or "Discord link preview"
        if embed.description.strip():
            label += f" — {embed.description.strip()[:700]}"
        lines.append(label)

    trailing = ".,!?;:\uff0c\u3002\uff01\uff1f\uff1b\uff1a"
    urls = list(
        dict.fromkeys(match.rstrip(trailing) for match in _URL_PATTERN.findall(payload.text))
    )
    for raw_url in urls[:4]:
        try:
            source = resolve_static_url(raw_url)
            platform = source.platform or "web"
            lines.append(f"Shared {source.kind} link on {platform}: {source.canonical_url}")
        except ValueError:
            lines.append(f"Shared web link: {raw_url[:1000]}")

    return tuple(dict.fromkeys(lines[:_MAX_PREVIEW_LINES]))


def has_shared_content(payload: DiscordInboundMessage) -> bool:
    return bool(payload.attachments or payload.embeds or _URL_PATTERN.search(payload.text))


class CharacterMediaAttentionDecider:
    """Use the Character model privately to decide whether the Character would inspect media."""

    async def decide(
        self,
        *,
        target: PromptModelTarget,
        payload: DiscordInboundMessage,
    ) -> MediaAttentionDecision:
        previews = media_preview_lines(payload)
        if not previews:
            return MediaAttentionDecision(action="skip", reason="no_shared_content")

        recent = []
        for item in payload.recent_messages[-_MAX_RECENT_MESSAGES:]:
            text = " ".join(item.text.split()).strip()
            if not text:
                continue
            role = "Character" if item.is_bot else "Member"
            recent.append(f"{role} {item.author_display_name}: {text[:600]}")

        prompt = "\n".join(
            (
                _ATTENTION_MARKER,
                "This is a private attention decision. Do not answer the Discord member here.",
                "A member shared content in a group conversation. Decide whether you, as this "
                "Character, would actually open/watch/read it before deciding what to say.",
                "Choose watch only when your persona, interests, relationship to the speaker, "
                "or the current conversation make you genuinely willing or curious to inspect it.",
                "Do not choose watch merely because media exists. A direct request to look is "
                "social pressure, not an override of your personality; you may still skip.",
                "You know only the Discord-visible preview below. Do not infer unseen content.",
                "If you choose skip, the Runtime will not fetch, transcribe, or run Vision on it.",
                "Return exactly one JSON object: "
                '{"action":"watch|skip","reason":"brief persona-grounded reason"}',
                "",
                "Discord-visible content preview:",
                *previews,
                "",
                "Recent conversation:",
                *(recent or ["(No useful recent text.)"]),
                "",
                "Latest member message:",
                payload.text.strip()[:2000] or "(No text; content was shared directly.)",
            )
        )
        try:
            completion = await target.provider.complete(
                messages=(
                    ChatMessage(role="system", content=target.runtime_system_prompt),
                    ChatMessage(role="user", content=prompt),
                ),
                model=target.config.model,
                temperature=min(target.config.temperature, 0.3),
            )
        except Exception:
            return MediaAttentionDecision(action="skip", reason="attention_model_unavailable")
        return self._parse(completion.text)

    @staticmethod
    def _parse(text: str) -> MediaAttentionDecision:
        normalized = text.strip()
        candidates = [normalized]
        match = re.search(r"\{.*?\}", normalized, flags=re.DOTALL)
        if match is not None:
            candidates.append(match.group(0))
        for candidate in candidates:
            try:
                raw = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if not isinstance(raw, dict):
                continue
            action = str(raw.get("action") or "").strip().casefold()
            if action not in {"watch", "skip"}:
                continue
            reason = str(raw.get("reason") or "").replace("\x00", "").strip()[:300]
            return MediaAttentionDecision(
                action="watch" if action == "watch" else "skip",
                reason=reason or "persona_decision",
            )
        return MediaAttentionDecision(action="skip", reason="invalid_attention_output")


__all__ = [
    "CharacterMediaAttentionDecider",
    "MediaAttentionDecider",
    "MediaAttentionDecision",
    "has_shared_content",
    "media_preview_lines",
]
