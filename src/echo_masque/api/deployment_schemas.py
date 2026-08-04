"""HTTP schemas for platform connections and character deployments."""

import json
from datetime import datetime
from typing import Literal, cast

from pydantic import BaseModel, Field

from echo_masque.persistence.deployment_models import (
    CharacterDeploymentRecord,
    PlatformConnectionRecord,
)

PlatformId = Literal["discord", "whatsapp", "telegram"]
ConnectionMode = Literal["managed", "local"]
ConnectionStatus = Literal["connected", "offline", "error", "disconnected"]
ParticipationMode = Literal[
    "mention_only",
    "reply_only",
    "mention_and_reply",
    "smart",
]
MemoryScope = Literal["channel_isolated", "server_shared", "custom"]
DeploymentStatus = Literal[
    "active",
    "paused",
    "offline",
    "error",
    "disconnected",
]


class PlatformConnectionCreate(BaseModel):
    platform: PlatformId
    display_name: str = Field(min_length=1, max_length=120)
    connection_mode: ConnectionMode = "managed"
    external_account_id: str = Field(default="", max_length=200)
    status: ConnectionStatus = "disconnected"
    metadata: dict[str, object] = Field(default_factory=dict)


class PlatformConnectionUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    connection_mode: ConnectionMode | None = None
    external_account_id: str | None = Field(default=None, max_length=200)
    status: ConnectionStatus | None = None
    metadata: dict[str, object] | None = None


class PlatformConnectionView(BaseModel):
    id: str
    platform: PlatformId
    display_name: str
    connection_mode: ConnectionMode
    external_account_id: str
    status: ConnectionStatus
    metadata: dict[str, object]
    last_seen_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_record(cls, record: PlatformConnectionRecord) -> "PlatformConnectionView":
        raw = json.loads(record.metadata_json)
        metadata = raw if isinstance(raw, dict) else {}
        return cls(
            id=record.id,
            platform=cast(PlatformId, record.platform),
            display_name=record.display_name,
            connection_mode=cast(ConnectionMode, record.connection_mode),
            external_account_id=record.external_account_id,
            status=cast(ConnectionStatus, record.status),
            metadata=cast(dict[str, object], metadata),
            last_seen_at=record.last_seen_at,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )


class CharacterDeploymentCreate(BaseModel):
    character_card_id: str = Field(min_length=1, max_length=64)
    connection_id: str = Field(min_length=1, max_length=64)
    workspace_id: str = Field(default="", max_length=200)
    workspace_name: str = Field(default="", max_length=160)
    channel_id: str = Field(min_length=1, max_length=200)
    channel_name: str = Field(min_length=1, max_length=160)
    thread_id: str = Field(default="", max_length=200)
    thread_name: str = Field(default="", max_length=160)
    participation_mode: ParticipationMode = "mention_and_reply"
    memory_scope: MemoryScope = "channel_isolated"
    version_label: str = Field(default="Current", min_length=1, max_length=80)
    sticker_count: int = Field(default=0, ge=0, le=500)
    status: DeploymentStatus = "paused"


class CharacterDeploymentUpdate(BaseModel):
    workspace_id: str | None = Field(default=None, max_length=200)
    workspace_name: str | None = Field(default=None, max_length=160)
    channel_id: str | None = Field(default=None, min_length=1, max_length=200)
    channel_name: str | None = Field(default=None, min_length=1, max_length=160)
    thread_id: str | None = Field(default=None, max_length=200)
    thread_name: str | None = Field(default=None, max_length=160)
    participation_mode: ParticipationMode | None = None
    memory_scope: MemoryScope | None = None
    version_label: str | None = Field(default=None, min_length=1, max_length=80)
    sticker_count: int | None = Field(default=None, ge=0, le=500)
    status: DeploymentStatus | None = None
    last_error: str | None = Field(default=None, max_length=2000)


class CharacterDeploymentStatusUpdate(BaseModel):
    status: DeploymentStatus
    last_error: str = Field(default="", max_length=2000)


class CharacterDeploymentView(BaseModel):
    id: str
    character_card_id: str
    character_display_name: str
    connection_id: str
    platform: PlatformId
    workspace_id: str
    workspace_name: str
    channel_id: str
    channel_name: str
    thread_id: str
    thread_name: str
    participation_mode: ParticipationMode
    memory_scope: MemoryScope
    version_label: str
    sticker_count: int
    status: DeploymentStatus
    last_message_at: datetime | None
    last_error: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_record(
        cls,
        record: CharacterDeploymentRecord,
        *,
        character_display_name: str,
    ) -> "CharacterDeploymentView":
        return cls(
            id=record.id,
            character_card_id=record.character_card_id,
            character_display_name=character_display_name,
            connection_id=record.connection_id,
            platform=cast(PlatformId, record.platform),
            workspace_id=record.workspace_id,
            workspace_name=record.workspace_name,
            channel_id=record.channel_id,
            channel_name=record.channel_name,
            thread_id=record.thread_id,
            thread_name=record.thread_name,
            participation_mode=cast(ParticipationMode, record.participation_mode),
            memory_scope=cast(MemoryScope, record.memory_scope),
            version_label=record.version_label,
            sticker_count=record.sticker_count,
            status=cast(DeploymentStatus, record.status),
            last_message_at=record.last_message_at,
            last_error=record.last_error,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
