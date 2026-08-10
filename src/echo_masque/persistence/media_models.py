"""Content-addressed shared Media Analysis cache models."""

from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from echo_masque.persistence.models import Base, utcnow


class MediaAnalysisRecord(Base):
    """Objective media-derived context reusable across characters and accounts."""

    __tablename__ = "media_analyses"
    __table_args__ = (
        UniqueConstraint(
            "media_key",
            "analysis_version",
            "provider",
            "model",
            name="uq_media_analysis_identity",
        ),
        Index("ix_media_analyses_expires_at", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    media_key: Mapped[str] = mapped_column(String(300), index=True, nullable=False)
    media_type: Mapped[str] = mapped_column(String(30), nullable=False)
    analysis_version: Mapped[str] = mapped_column(String(80), nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    result_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_accessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
