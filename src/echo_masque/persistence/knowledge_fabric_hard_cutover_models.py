"""Persistent ledger for retiring the pre-Fabric Knowledge and Server Wiki stores."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from echo_masque.persistence.models import Base, utcnow


class KnowledgeFabricHardCutoverMigrationRecord(Base):
    """One irreversible, restart-safe retirement record with metadata-only evidence."""

    __tablename__ = "knowledge_fabric_hard_cutover_migrations"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    retired_tables_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    retired_row_counts_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    last_error: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


__all__ = ["KnowledgeFabricHardCutoverMigrationRecord"]
