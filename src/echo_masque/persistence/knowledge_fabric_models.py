"""Durable scope and access records for the Knowledge Fabric.

These records deliberately do not reuse Discord deployment profiles or join-code
access.  A KnowledgeServerScope is a stable product principal and its explicit
administrator membership is the only Phase 2 server-local authority.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from echo_masque.persistence.models import Base, utcnow


class KnowledgeServerScopeRecord(Base):
    """Canonical server identity, stable across profile and connector changes."""

    __tablename__ = "knowledge_server_scopes"
    __table_args__ = (
        UniqueConstraint(
            "platform",
            "connection_id",
            "workspace_id",
            name="uq_knowledge_server_scope_identity",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    connection_id: Mapped[str] = mapped_column(String(64), nullable=False)
    workspace_id: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class KnowledgeServerAdministratorRecord(Base):
    """An explicit account membership authorized for one canonical server scope."""

    __tablename__ = "knowledge_server_administrators"
    __table_args__ = (
        UniqueConstraint(
            "server_scope_id",
            "user_id",
            name="uq_knowledge_server_administrator",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    server_scope_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_server_scopes.id"), index=True, nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"), index=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class KnowledgeCorpusRecord(Base):
    """Corpus ownership and visibility metadata; imported content arrives later."""

    __tablename__ = "knowledge_corpora"
    __table_args__ = (Index("ix_knowledge_corpora_owner_scope", "owner_type", "owner_id"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    owner_type: Mapped[str] = mapped_column(String(24), index=True, nullable=False)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    visibility: Mapped[str] = mapped_column(String(24), nullable=False)
    default_authority_profile: Mapped[str] = mapped_column(
        String(80), default="standard", nullable=False
    )
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class KnowledgeSourceRecord(Base):
    """Registered source metadata only; source versions and artifacts are Phase 3."""

    __tablename__ = "knowledge_sources"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    corpus_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_corpora.id"), index=True, nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    locator: Mapped[str] = mapped_column(String(1000), nullable=False)
    access_profile_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    parser_profile_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    sync_policy_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    freshness_policy_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    authority_profile: Mapped[str] = mapped_column(String(80), default="standard", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(24), default="registered", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class KnowledgeAccessGrantRecord(Base):
    """One enable/disable state for a grantee's access to a corpus."""

    __tablename__ = "knowledge_access_grants"
    __table_args__ = (
        UniqueConstraint(
            "corpus_id",
            "grantee_type",
            "grantee_id",
            name="uq_knowledge_access_grant_grantee",
        ),
        Index(
            "ix_knowledge_grant_grantee_access",
            "grantee_type",
            "grantee_id",
            "enabled",
            "corpus_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    corpus_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_corpora.id"), index=True, nullable=False
    )
    grantee_type: Mapped[str] = mapped_column(String(24), index=True, nullable=False)
    grantee_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    access_mode: Mapped[str] = mapped_column(String(24), default="read", nullable=False)
    policy_metadata_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class KnowledgeOverlayPolicyRecord(Base):
    """Non-destructive, per-server precedence for one granted corpus."""

    __tablename__ = "knowledge_overlay_policies"
    __table_args__ = (
        UniqueConstraint(
            "server_scope_id",
            "corpus_id",
            name="uq_knowledge_overlay_policy_scope_corpus",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    server_scope_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_server_scopes.id"), index=True, nullable=False
    )
    corpus_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_corpora.id"), index=True, nullable=False
    )
    mode: Mapped[str] = mapped_column(String(24), nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


__all__ = [
    "KnowledgeAccessGrantRecord",
    "KnowledgeCorpusRecord",
    "KnowledgeOverlayPolicyRecord",
    "KnowledgeServerAdministratorRecord",
    "KnowledgeServerScopeRecord",
    "KnowledgeSourceRecord",
]
