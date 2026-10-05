"""Shared full-room and batch presentation; source provenance stays unchanged."""

from typing import Any

from echo_masque.room_sources import SourceMessage


def web_message_view(
    message: SourceMessage,
    *,
    reply_id: str,
    reply_preview: dict[str, object] | None,
    reactions: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "id": message.message_id,
        "author_id": message.author_id,
        "display_name": message.author_display_name,
        "avatar_url": message.author_avatar_url,
        "actor_type": "web_participant"
        if message.author_external_id
        else "character"
        if message.author_deployment_id
        else "bot"
        if message.author_is_bot
        else "discord_user",
        "text": message.text,
        "deleted": message.deleted,
        "content_available": message.content_available,
        "created_at": message.created_at.isoformat() if message.created_at else None,
        "edited_at": message.edited_at.isoformat() if message.edited_at else None,
        "reply_to_message_id": reply_id,
        "reply_preview": reply_preview,
        "attachments": [entry.model_dump(mode="json") for entry in message.attachments],
        "custom_emojis": [entry.model_dump(mode="json") for entry in message.custom_emojis],
        "stickers": [entry.model_dump(mode="json") for entry in message.stickers],
        "mentions": [entry.model_dump(mode="json") for entry in message.mentions],
        "embeds": [entry.model_dump(mode="json") for entry in message.embeds],
        "poll": message.poll.model_dump(mode="json") if message.poll is not None else None,
        "reactions": reactions,
        "pinned": message.pinned,
    }


def message_summary(message: object) -> str:
    text = str(getattr(message, "text", "") or "").strip().replace("\n", " ")
    if text:
        return text[:180] + ("…" if len(text) > 180 else "")
    if getattr(message, "stickers", ()):
        return "[Sticker]"
    if getattr(message, "attachments", ()):
        return "[Attachment]"
    if getattr(message, "custom_emojis", ()):
        return "[Emoji]"
    return "[No text content]"
