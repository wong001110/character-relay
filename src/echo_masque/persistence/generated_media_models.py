"""Short-lived generated media artifacts awaiting connector delivery."""

from datetime import datetime

from sqlalchemy import DateTime, Index, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from echo_masque.persistence.models import Base, utcnow


class GeneratedMediaArtifactRecord(Base):
    """A bounded generated image kept only long enough for delivery/reference reuse."""

    __tablename__ = "generated_media_artifacts"
    __table_args__ = (
        Index("ix_generated_media_owner", "owner_id", "id"),
        Index("ix_generated_media_expires_at", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    deployment_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    character_card_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    media_key: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
