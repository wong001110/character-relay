"""Persistent ledgers for schema and one-time data migrations.

The ledgers are deliberately generic.  Product migrations keep their own domain
records, while this module records database-foundation work that must be safe to
run before any product service is composed.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from echo_masque.persistence.models import Base, utcnow


class DatabaseSchemaMigrationRecord(Base):
    """One applied database schema/foundation revision."""

    __tablename__ = "database_schema_migrations"

    revision: Mapped[str] = mapped_column(String(120), primary_key=True)
    database_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DatabaseDataMigrationRecord(Base):
    """One explicitly initiated source-to-empty-target data-copy operation."""

    __tablename__ = "database_data_migrations"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    source_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    table_counts_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str] = mapped_column(String(120), default="", nullable=False)


__all__ = ["DatabaseDataMigrationRecord", "DatabaseSchemaMigrationRecord"]
