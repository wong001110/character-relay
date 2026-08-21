"""Conversation runtime persistence for Episode v3, working state, and standalone actions."""

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from echo_masque.persistence.models import Base, utcnow


class ConversationEpisodeV3Record(Base):
    """Durable event projection over Segment/Thread provenance, never Topic identity."""

    __tablename__ = "conversation_episodes_v3"
    __table_args__ = (
        UniqueConstraint(
            "owner_id",
            "connection_id",
            "guild_id",
            "episode_key",
            name="uq_conversation_episode_v3_scope_key",
        ),
        Index(
            "ix_conversation_episode_v3_scope_time",
            "owner_id",
            "connection_id",
            "guild_id",
            "channel_id",
            "discord_thread_id",
            "ended_at",
        ),
        Index(
            "ix_conversation_episode_v3_thread_status",
            "owner_id",
            "conversation_thread_id",
            "status",
            "updated_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    platform: Mapped[str] = mapped_column(String(24), default="discord", nullable=False)
    connection_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    guild_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    channel_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    discord_thread_id: Mapped[str] = mapped_column(
        String(200), default="", nullable=False
    )
    conversation_thread_id: Mapped[str] = mapped_column(
        String(64), default="", index=True, nullable=False
    )
    episode_key: Mapped[str] = mapped_column(String(160), nullable=False)
    segment_ids_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    source_message_ids_json: Mapped[str] = mapped_column(
        Text, default="[]", nullable=False
    )
    participant_ids_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    entity_ids_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    media_refs_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    key_events_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    segment_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), default="active", index=True, nullable=False
    )
    checkpoint_reason: Mapped[str] = mapped_column(
        String(40), default="", nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ThreadWorkingStateRecord(Base):
    """Short-lived conversational scratch state scoped to one ConversationThread."""

    __tablename__ = "thread_working_states_v3"
    __table_args__ = (
        Index(
            "ix_thread_working_state_v3_scope",
            "owner_id",
            "connection_id",
            "guild_id",
            "status",
            "expires_at",
        ),
    )

    thread_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    connection_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    guild_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    channel_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    discord_thread_id: Mapped[str] = mapped_column(
        String(200), default="", nullable=False
    )
    current_object_ref: Mapped[str] = mapped_column(
        String(320), default="", nullable=False
    )
    active_entity_ids_json: Mapped[str] = mapped_column(
        Text, default="[]", nullable=False
    )
    open_questions_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    waiting_states_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    referenced_media_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    state_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), default="active", index=True, nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class PendingActionV3Record(Base):
    """Standalone Tool action state linked to source evidence and optionally a Thread."""

    __tablename__ = "pending_actions_v3"
    __table_args__ = (
        Index(
            "ix_pending_actions_v3_actor_state",
            "owner_id",
            "connection_id",
            "guild_id",
            "requested_by_user_id",
            "target_character_card_id",
            "state",
            "expires_at",
        ),
        Index(
            "ix_pending_actions_v3_source",
            "owner_id",
            "source_message_id",
            "source_segment_id",
            "state",
        ),
        Index(
            "ix_pending_actions_v3_thread",
            "owner_id",
            "conversation_thread_id",
            "state",
            "updated_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    connection_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    guild_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    channel_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    discord_thread_id: Mapped[str] = mapped_column(
        String(200), default="", nullable=False
    )
    source_message_id: Mapped[str] = mapped_column(
        String(200), index=True, nullable=False
    )
    source_segment_id: Mapped[str] = mapped_column(
        String(64), default="", index=True, nullable=False
    )
    conversation_thread_id: Mapped[str] = mapped_column(
        String(64), default="", index=True, nullable=False
    )
    requested_by_user_id: Mapped[str] = mapped_column(
        String(200), index=True, nullable=False
    )
    target_character_card_id: Mapped[str] = mapped_column(
        String(64), default="", index=True, nullable=False
    )
    deployment_id: Mapped[str] = mapped_column(
        String(64), default="", index=True, nullable=False
    )
    tool_id: Mapped[str] = mapped_column(String(160), index=True, nullable=False)
    intent_summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    state: Mapped[str] = mapped_column(
        String(32), default="pending", index=True, nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


__all__ = [
    "ConversationEpisodeV3Record",
    "PendingActionV3Record",
    "ThreadWorkingStateRecord",
]
