"""Raw, room-scoped conversation evidence and bounded reply-chain context.

A message is evidence, not a semantic topic or an authorization. Platform adapters
must verify the original destination before constructing these observations.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from echo_masque.room_routing import RoomMessage, RoomScope


class SourceAttachment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    attachment_id: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=1, max_length=3000)
    proxy_url: str = Field(default="", max_length=3000)
    filename: str = Field(default="attachment", max_length=255)
    description: str = Field(default="", max_length=1024)
    content_type: str = Field(default="", max_length=160)
    size_bytes: int | None = Field(default=None, ge=0)
    width: int | None = Field(default=None, ge=0)
    height: int | None = Field(default=None, ge=0)


class SourceExpression(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    resource_id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=160)
    animated: bool = False
    asset_url: str = Field(default="", max_length=3000)
    format_type: str = Field(default="", max_length=40)
    description: str = Field(default="", max_length=1000)


class SourceReaction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    key: str = Field(min_length=1, max_length=240)
    resource_id: str = Field(default="", max_length=200)
    name: str = Field(min_length=1, max_length=160)
    animated: bool = False
    asset_url: str = Field(default="", max_length=3000)
    count: int = Field(default=0, ge=0)


class SourceMessage(BaseModel):
    """One normalized platform observation, including tombstones and unreadable input."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    message_id: str = Field(min_length=1, max_length=200)
    channel_id: str = Field(min_length=1, max_length=200)
    thread_id: str = Field(default="", max_length=200)
    author_id: str = Field(default="", max_length=200)
    author_display_name: str = Field(default="", max_length=160)
    author_avatar_url: str = Field(default="", max_length=1000)
    author_external_id: str = Field(default="", max_length=64)
    webhook_id: str = Field(default="", max_length=200)
    author_is_bot: bool = False
    author_deployment_id: str = Field(default="", max_length=200)
    text: str = Field(default="", max_length=10000)
    reply_to_message_id: str = Field(default="", max_length=200)
    response_to_message_id: str = Field(default="", max_length=200)
    response_delivery_complete: bool | None = None
    mentioned_deployment_ids: tuple[str, ...] = Field(default=(), max_length=24)
    created_at: datetime | None = None
    edited_at: datetime | None = None
    deleted: bool = False
    content_available: bool = True
    has_unseen_media: bool = False
    media_fingerprint: str = Field(default="", max_length=64)
    attachments: tuple[SourceAttachment, ...] = Field(default=(), max_length=10)
    custom_emojis: tuple[SourceExpression, ...] = Field(default=(), max_length=20)
    stickers: tuple[SourceExpression, ...] = Field(default=(), max_length=3)
    reactions: tuple[SourceReaction, ...] = Field(default=(), max_length=40)
    pinned: bool = False

    @model_validator(mode="after")
    def validate_observation(self) -> SourceMessage:
        if not self.deleted and not self.author_id:
            raise ValueError("A readable observation needs a stable author identity.")
        if self.author_external_id and (not self.author_is_bot or self.author_deployment_id):
            raise ValueError("External participant identity cannot be a human or character.")
        if self.author_deployment_id and not self.author_is_bot:
            raise ValueError("Only a verified bot message has a deployment identity.")
        if self.deleted and self.text:
            raise ValueError("A tombstone must not retain message content.")
        if self.deleted and (self.attachments or self.custom_emojis or self.stickers or self.reactions):
            raise ValueError("A tombstone must not retain presentation content.")
        if not self.content_available and self.text:
            raise ValueError("Unavailable content must not be serialized as readable evidence.")
        for timestamp in (self.created_at, self.edited_at):
            if timestamp is not None and timestamp.tzinfo is None:
                raise ValueError("Source timestamps must include their original timezone.")
        return self

    def draft_fingerprint(self) -> str:
        """Content/identity changes matter; display-name or timestamp enrichment does not."""
        payload = [
            self.author_id,
            self.author_is_bot,
            self.author_external_id,
            self.author_deployment_id,
            self.text,
            self.reply_to_message_id,
            self.response_to_message_id,
            self.deleted,
            self.content_available,
            self.has_unseen_media,
            self.media_fingerprint,
        ]
        return hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode()).hexdigest()

    def effective_time(self) -> datetime:
        return self.edited_at or self.created_at or datetime.min.replace(tzinfo=UTC)

    def in_scope(self, scope: RoomScope) -> bool:
        return self.channel_id == scope.channel_id and self.thread_id == scope.thread_id

    def routing_message(self, scope: RoomScope, revision: int) -> RoomMessage:
        if not self.in_scope(scope) or not self.author_id:
            raise ValueError("A source cannot be relabeled to another room.")
        return RoomMessage(
            id=self.message_id,
            scope=scope,
            author_id=self.author_id,
            author_kind=(
                "external_agent"
                if self.author_external_id
                else "character"
                if self.author_deployment_id
                else "other_bot"
                if self.author_is_bot
                else "human"
            ),
            author_deployment_id=self.author_deployment_id or None,
            text=self.text[:4000],
            version=revision,
            reply_to_message_id=self.reply_to_message_id or None,
            response_to_message_id=self.response_to_message_id or None,
            response_delivery_complete=self.response_delivery_complete,
            mentioned_deployment_ids=self.mentioned_deployment_ids,
            deleted=self.deleted,
            content_available=self.content_available,
            has_unseen_media=self.has_unseen_media,
        )


def scope_key(scope: RoomScope) -> str:
    """Unambiguous identity; concatenation of colon-delimited IDs is not sufficient."""
    return hashlib.sha256(scope.model_dump_json().encode()).hexdigest()


def evidence_key(scope: RoomScope, message_id: str) -> str:
    return hashlib.sha256(json.dumps([scope_key(scope), message_id]).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class StoredSource:
    message: SourceMessage
    revision: int
    room_revision: int


@dataclass(frozen=True, slots=True)
class FocusedContext:
    scope: RoomScope
    target_message_id: str
    sources: tuple[StoredSource, ...]
    anchor_ids: tuple[str, ...]
    missing_ancestor_ids: tuple[str, ...]
    room_revision: int

    @property
    def message_ids(self) -> tuple[str, ...]:
        return tuple(source.message.message_id for source in self.sources)

    @property
    def fingerprint(self) -> str:
        payload = [
            scope_key(self.scope),
            self.target_message_id,
            [(source.message.message_id, source.revision) for source in self.sources],
            self.anchor_ids,
            self.missing_ancestor_ids,
        ]
        return hashlib.sha256(json.dumps(payload).encode()).hexdigest()


class SourceUnavailable(ValueError):
    """A missing, deleted, unreadable or out-of-scope source is not a retarget request."""


def delivery_key(scope: RoomScope, message_id: str) -> str:
    """Shared destination provenance excludes role-owner identity, never room identity."""
    return hashlib.sha256(
        json.dumps(
            [scope.connection_id, scope.guild_id, scope.channel_id, scope.thread_id, message_id]
        ).encode()
    ).hexdigest()
