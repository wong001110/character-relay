"""Topic-free server Wiki and consolidation checkpoint models for Intelligence Core v3."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from echo_masque.persistence.models import Base, utcnow


class ServerWikiPageV3Record(Base):
    __tablename__ = "server_wiki_pages_v3"
    __table_args__ = (
        UniqueConstraint(
            "owner_id",
            "connection_id",
            "guild_id",
            "page_key",
            name="uq_server_wiki_v3_scope_page",
        ),
        Index(
            "ix_server_wiki_v3_scope_type",
            "owner_id",
            "connection_id",
            "guild_id",
            "page_type",
            "stale",
            "updated_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    connection_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    guild_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    page_key: Mapped[str] = mapped_column(String(220), index=True, nullable=False)
    page_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    subject_ref: Mapped[str] = mapped_column(String(320), index=True, nullable=False)
    visibility_scope: Mapped[str] = mapped_column(String(32), default="server", nullable=False)
    title: Mapped[str] = mapped_column(String(320), nullable=False)
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    keywords_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    source_episode_ids_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    source_entity_ids_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    source_belief_ids_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    source_evidence_edge_ids_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.65, nullable=False)
    stale: Mapped[bool] = mapped_column(Boolean, default=False, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class KnowledgeConsolidationCheckpointV3Record(Base):
    __tablename__ = "knowledge_consolidation_checkpoints_v3"
    __table_args__ = (
        UniqueConstraint(
            "owner_id",
            "connection_id",
            "guild_id",
            "source_ref_type",
            "source_ref",
            name="uq_knowledge_consolidation_v3_source",
        ),
        Index(
            "ix_knowledge_consolidation_v3_status",
            "status",
            "updated_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    connection_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    guild_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    source_ref_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_ref: Mapped[str] = mapped_column(String(320), nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True, nullable=False)
    reason: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    source_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    wiki_page_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    utility_status: Mapped[str] = mapped_column(String(48), default="", nullable=False)
    last_error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


__all__ = ["KnowledgeConsolidationCheckpointV3Record", "ServerWikiPageV3Record"]
