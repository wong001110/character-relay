"""Persistence models for scoped RAG knowledge."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from echo_masque.persistence.models import Base, utcnow


class KnowledgeBaseRecord(Base):
    """One owner-managed knowledge collection with an explicit retrieval scope."""

    __tablename__ = "knowledge_bases"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    scope_type: Mapped[str] = mapped_column(String(24), default="server", nullable=False)
    connection_id: Mapped[str] = mapped_column(String(64), default="", index=True, nullable=False)
    guild_id: Mapped[str] = mapped_column(String(200), default="", index=True, nullable=False)
    channel_id: Mapped[str] = mapped_column(String(200), default="", index=True, nullable=False)
    thread_id: Mapped[str] = mapped_column(String(200), default="", index=True, nullable=False)
    character_card_id: Mapped[str] = mapped_column(
        String(64), default="", index=True, nullable=False
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class KnowledgeDocumentRecord(Base):
    """Original user-authored source text stored inside one Knowledge Base."""

    __tablename__ = "knowledge_documents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    knowledge_base_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    source_type: Mapped[str] = mapped_column(String(24), default="text", nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class KnowledgeChunkRecord(Base):
    """Deterministic retrieval unit derived from one Knowledge Document."""

    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "chunk_index",
            name="uq_knowledge_chunk_document_index",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    knowledge_base_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    document_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    document_title: Mapped[str] = mapped_column(String(240), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
