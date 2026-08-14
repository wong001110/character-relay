from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from echo_masque.persistence.models import Base, utcnow


class ConversationGraphNodeRecord(Base):
    __tablename__ = "conversation_graph_nodes"
    __table_args__ = (
        UniqueConstraint(
            "scope_owner_id",
            "platform",
            "connection_id",
            "guild_id",
            "channel_id",
            "thread_id",
            "node_type",
            "canonical_key",
            name="uq_conversation_graph_node_scope_key",
        ),
        Index(
            "ix_conversation_graph_node_scope_activity",
            "platform",
            "connection_id",
            "guild_id",
            "channel_id",
            "thread_id",
            "last_active_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # Empty owner means public conversation-derived state. Non-empty owner is a private overlay.
    scope_owner_id: Mapped[str] = mapped_column(String(120), default="", index=True, nullable=False)
    platform: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    connection_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    guild_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    channel_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    thread_id: Mapped[str] = mapped_column(String(128), default="", index=True, nullable=False)
    node_type: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    canonical_key: Mapped[str] = mapped_column(String(240), nullable=False)
    label: Mapped[str] = mapped_column(String(240), default="", nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    last_active_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ConversationGraphEdgeRecord(Base):
    __tablename__ = "conversation_graph_edges"
    __table_args__ = (
        UniqueConstraint(
            "scope_owner_id",
            "source_node_id",
            "relation",
            "target_node_id",
            name="uq_conversation_graph_edge_relation",
        ),
        Index(
            "ix_conversation_graph_edge_scope_activity",
            "platform",
            "connection_id",
            "guild_id",
            "channel_id",
            "thread_id",
            "last_active_at",
        ),
        Index("ix_conversation_graph_edge_source_relation", "source_node_id", "relation"),
        Index("ix_conversation_graph_edge_target_relation", "target_node_id", "relation"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    scope_owner_id: Mapped[str] = mapped_column(String(120), default="", index=True, nullable=False)
    platform: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    connection_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    guild_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    channel_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    thread_id: Mapped[str] = mapped_column(String(128), default="", index=True, nullable=False)
    source_node_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("conversation_graph_nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    relation: Mapped[str] = mapped_column(String(60), index=True, nullable=False)
    target_node_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("conversation_graph_nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    confidence: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    evidence_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    negative_evidence_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    source_type: Mapped[str] = mapped_column(String(40), default="message", nullable=False)
    source_message_id: Mapped[str] = mapped_column(
        String(200),
        default="",
        index=True,
        nullable=False,
    )
    source_burst_id: Mapped[str] = mapped_column(String(80), default="", index=True, nullable=False)
    provenance_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="active", index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    last_active_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


__all__ = ["ConversationGraphEdgeRecord", "ConversationGraphNodeRecord"]
