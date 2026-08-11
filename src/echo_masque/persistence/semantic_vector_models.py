"""Reusable persisted semantic vectors for runtime retrieval features."""

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from echo_masque.persistence.models import Base, utcnow


class SemanticVectorRecord(Base):
    """One cached embedding for an owner-scoped runtime resource."""

    __tablename__ = "semantic_vectors"
    __table_args__ = (
        UniqueConstraint(
            "owner_id",
            "namespace",
            "resource_id",
            name="uq_semantic_vector_resource",
        ),
        Index("ix_semantic_vector_scope", "owner_id", "namespace"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    namespace: Mapped[str] = mapped_column(String(80), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(500), nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    semantic_text: Mapped[str] = mapped_column(Text, nullable=False)
    model_name: Mapped[str] = mapped_column(String(160), nullable=False)
    dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding_blob: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
