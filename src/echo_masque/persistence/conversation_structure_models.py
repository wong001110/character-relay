"""Persistence contracts for Intelligence Core v3 Conversation Structure."""

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from echo_masque.persistence.models import Base, utcnow


class ConversationThreadRecord(Base):
    """One revisable conversation track; never a durable knowledge authority."""

    __tablename__ = "conversation_threads_v3"
    __table_args__ = (
        Index(
            "ix_conversation_threads_v3_scope_activity",
            "owner_id",
            "connection_id",
            "guild_id",
            "channel_id",
            "discord_thread_id",
            "status",
            "last_active_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    platform: Mapped[str] = mapped_column(String(24), default="discord", nullable=False)
    connection_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    guild_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    channel_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    discord_thread_id: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    canonical_label: Mapped[str] = mapped_column(String(240), default="", nullable=False)
    anchor_summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    working_summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    representative_segment_ids_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    participant_ids_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    active_entity_ids_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="hot", index=True, nullable=False)
    last_active_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ConversationSegmentV3Record(Base):
    """One conversation unit projected from a temporal Burst, without direct Thread authority."""

    __tablename__ = "conversation_segments_v3"
    __table_args__ = (
        UniqueConstraint(
            "owner_id",
            "burst_id",
            "segment_key",
            name="uq_conversation_segments_v3_owner_burst_key",
        ),
        Index(
            "ix_conversation_segments_v3_scope_recent",
            "owner_id",
            "connection_id",
            "guild_id",
            "channel_id",
            "discord_thread_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    burst_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    segment_key: Mapped[str] = mapped_column(String(120), nullable=False)
    connection_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    guild_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    channel_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    discord_thread_id: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    message_ids_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    participant_ids_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    kind: Mapped[str] = mapped_column(String(32), default="discussion", nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    source: Mapped[str] = mapped_column(String(32), default="deterministic", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ThreadMembershipRecord(Base):
    """Versioned, reversible interpretation that assigns a Segment to a conversation track."""

    __tablename__ = "thread_memberships_v3"
    __table_args__ = (
        Index(
            "ix_thread_memberships_v3_segment_active",
            "owner_id",
            "segment_id",
            "status",
            "version",
        ),
        Index(
            "ix_thread_memberships_v3_thread_active",
            "owner_id",
            "thread_id",
            "status",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    segment_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    thread_id: Mapped[str] = mapped_column(String(64), default="", index=True, nullable=False)
    relation: Mapped[str] = mapped_column(String(32), default="belongs_to", nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    source: Mapped[str] = mapped_column(String(32), default="deterministic", nullable=False)
    reason: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="active", index=True, nullable=False)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MessageRelationRecord(Base):
    """Evidence-backed interaction or semantic relation originating from one Discord message."""

    __tablename__ = "message_relations_v3"
    __table_args__ = (
        Index(
            "ix_message_relations_v3_scope_source",
            "owner_id",
            "connection_id",
            "guild_id",
            "channel_id",
            "discord_thread_id",
            "source_message_id",
        ),
        Index(
            "ix_message_relations_v3_target",
            "owner_id",
            "target_ref_type",
            "target_ref",
            "status",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    connection_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    guild_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    channel_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    discord_thread_id: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    source_message_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    source_author_id: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    source_author_display_name: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    relation_class: Mapped[str] = mapped_column(String(24), nullable=False)
    relation_type: Mapped[str] = mapped_column(String(40), nullable=False)
    target_ref_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_ref: Mapped[str] = mapped_column(String(240), default="", nullable=False)
    target_author_id: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    target_author_display_name: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    source: Mapped[str] = mapped_column(String(32), default="deterministic", nullable=False)
    evidence_refs_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="resolved", index=True, nullable=False)
    supersedes_relation_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


__all__ = [
    "ConversationSegmentV3Record",
    "ConversationThreadRecord",
    "MessageRelationRecord",
    "ThreadMembershipRecord",
]
