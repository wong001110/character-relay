"""API schemas for scoped Knowledge Bases and RAG V1 retrieval."""

from datetime import datetime
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from echo_masque.persistence.knowledge_models import (
    KnowledgeBaseRecord,
    KnowledgeDocumentRecord,
)

KnowledgeScopeType = Literal["global", "server", "channel"]


class KnowledgeBaseWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=4000)
    scope_type: KnowledgeScopeType = "server"
    connection_id: str = Field(default="", max_length=64)
    guild_id: str = Field(default="", max_length=200)
    channel_id: str = Field(default="", max_length=200)
    thread_id: str = Field(default="", max_length=200)
    character_card_id: str = Field(default="", max_length=64)
    enabled: bool = True

    @model_validator(mode="after")
    def validate_scope(self) -> "KnowledgeBaseWrite":
        if self.scope_type == "global":
            if any((self.connection_id, self.guild_id, self.channel_id, self.thread_id)):
                raise ValueError("Global knowledge cannot include Discord location filters.")
            return self
        if not self.connection_id or not self.guild_id:
            raise ValueError("Server/channel knowledge requires connection_id and guild_id.")
        if self.scope_type == "server" and any((self.channel_id, self.thread_id)):
            raise ValueError("Server knowledge cannot include channel/thread filters.")
        if self.scope_type == "channel" and not self.channel_id:
            raise ValueError("Channel knowledge requires channel_id.")
        return self


class KnowledgeBaseCreate(KnowledgeBaseWrite):
    pass


class KnowledgeBaseUpdate(KnowledgeBaseWrite):
    pass


class KnowledgeBaseView(KnowledgeBaseWrite):
    id: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_record(cls, record: KnowledgeBaseRecord) -> "KnowledgeBaseView":
        return cls(
            id=record.id,
            name=record.name,
            description=record.description,
            scope_type=cast(KnowledgeScopeType, record.scope_type),
            connection_id=record.connection_id,
            guild_id=record.guild_id,
            channel_id=record.channel_id,
            thread_id=record.thread_id,
            character_card_id=record.character_card_id,
            enabled=record.enabled,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )


class KnowledgeDocumentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=240)
    content: str = Field(min_length=1, max_length=200_000)


class KnowledgeDocumentView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    knowledge_base_id: str
    title: str
    source_type: str
    content_sha256: str
    chunk_count: int
    content_chars: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_record(cls, record: KnowledgeDocumentRecord) -> "KnowledgeDocumentView":
        return cls(
            id=record.id,
            knowledge_base_id=record.knowledge_base_id,
            title=record.title,
            source_type=record.source_type,
            content_sha256=record.content_sha256,
            chunk_count=record.chunk_count,
            content_chars=len(record.content),
            created_at=record.created_at,
            updated_at=record.updated_at,
        )


class KnowledgeRetrieveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=4000)
    connection_id: str = Field(default="", max_length=64)
    guild_id: str = Field(default="", max_length=200)
    channel_id: str = Field(default="", max_length=200)
    thread_id: str = Field(default="", max_length=200)
    character_card_id: str = Field(default="", max_length=64)
    top_k: int = Field(default=4, ge=1, le=8)


class KnowledgeRetrieveHit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    knowledge_base_id: str
    document_id: str
    document_title: str
    chunk_index: int
    content: str
    score: float
    signals: dict[str, float]


class KnowledgeRetrieveView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    eligible_base_count: int
    candidate_chunk_count: int
    hits: list[KnowledgeRetrieveHit]
