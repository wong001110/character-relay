"""Discord-server derived Wiki, authority Graph, and consolidation checkpoint models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    delete,
    event,
    update,
)
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapped, Mapper, mapped_column

from echo_masque.persistence.models import Base, utcnow


class ServerWikiPageRecord(Base):
    """One derived page whose maximum visibility is one Discord server."""

    __tablename__ = "server_wiki_pages"
    __table_args__ = (
        UniqueConstraint(
            "owner_id",
            "connection_id",
            "guild_id",
            "page_key",
            name="uq_server_wiki_scope_page",
        ),
        Index(
            "ix_server_wiki_scope_updated",
            "owner_id",
            "connection_id",
            "guild_id",
            "updated_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    connection_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    guild_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    page_key: Mapped[str] = mapped_column(String(180), index=True, nullable=False)
    page_type: Mapped[str] = mapped_column(String(32), default="topic", index=True, nullable=False)
    visibility_scope: Mapped[str] = mapped_column(
        String(32), default="server", index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    keywords_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    source_topic_ids_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    source_episode_ids_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.65, nullable=False)
    stale: Mapped[bool] = mapped_column(Boolean, default=False, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ConversationAuthorityEdgeRecord(Base):
    """Typed interpretation edge; raw Episode/source records remain provenance truth."""

    __tablename__ = "conversation_authority_edges"
    __table_args__ = (
        UniqueConstraint(
            "owner_id",
            "connection_id",
            "guild_id",
            "source_ref",
            "relation",
            "target_ref",
            "authority_class",
            name="uq_conversation_authority_edge",
        ),
        Index(
            "ix_conversation_authority_scope_source",
            "owner_id",
            "connection_id",
            "guild_id",
            "source_ref",
        ),
        Index(
            "ix_conversation_authority_scope_target",
            "owner_id",
            "connection_id",
            "guild_id",
            "target_ref",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    connection_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    guild_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    source_ref: Mapped[str] = mapped_column(String(280), nullable=False)
    relation: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    target_ref: Mapped[str] = mapped_column(String(280), nullable=False)
    authority_class: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    evidence_refs_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    model_version: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="active", index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ConversationConsolidationCheckpointRecord(Base):
    """Idempotency and retry state for one Topic consolidation projection."""

    __tablename__ = "conversation_consolidation_checkpoints"
    __table_args__ = (
        UniqueConstraint(
            "owner_id",
            "topic_id",
            name="uq_conversation_consolidation_topic",
        ),
        Index(
            "ix_conversation_consolidation_status_updated",
            "status",
            "updated_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    topic_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    connection_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    guild_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), default="", index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True, nullable=False)
    reason: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    episode_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    memory_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    wiki_page_id: Mapped[str] = mapped_column(String(36), default="", nullable=False)
    graph_edge_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    utility_status: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    last_error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# Import after the server-derived models are declared so mapper registration remains acyclic.
from echo_masque.conversation_consolidation_events import (  # noqa: E402
    ConversationConsolidationEventBus,
)
from echo_masque.persistence.conversation_topic_models import (  # noqa: E402
    ConversationTopicRecord,
)


@event.listens_for(ConversationTopicRecord, "after_update")
def _topic_update_stales_server_wiki(
    _mapper: Mapper[Any],
    connection: Connection,
    target: ConversationTopicRecord,
) -> None:
    # Derived Wiki knowledge is never authoritative. Any Topic capsule/lifecycle update marks the
    # page stale immediately; the background service replaces it from Episode/source evidence.
    connection.execute(
        update(ServerWikiPageRecord)
        .where(
            ServerWikiPageRecord.owner_id == target.owner_id,
            ServerWikiPageRecord.page_key == f"topic:{target.id}",
            ServerWikiPageRecord.stale.is_(False),
        )
        .values(stale=True, updated_at=utcnow())
    )
    if target.status in {"cooling", "closed", "archived"}:
        ConversationConsolidationEventBus.publish(
            target.owner_id,
            target.id,
            f"topic_{target.status}",
        )
    elif target.message_count > 0 and target.message_count % 30 == 0:
        ConversationConsolidationEventBus.publish(
            target.owner_id,
            target.id,
            "size_checkpoint",
        )


@event.listens_for(ConversationTopicRecord, "after_delete")
def _topic_delete_removes_server_wiki(
    _mapper: Mapper[Any],
    connection: Connection,
    target: ConversationTopicRecord,
) -> None:
    connection.execute(
        delete(ServerWikiPageRecord).where(
            ServerWikiPageRecord.owner_id == target.owner_id,
            ServerWikiPageRecord.page_key == f"topic:{target.id}",
        )
    )


__all__ = [
    "ConversationAuthorityEdgeRecord",
    "ConversationConsolidationCheckpointRecord",
    "ServerWikiPageRecord",
]
