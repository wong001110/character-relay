"""Persistence models for private model-provider traces."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from echo_masque.persistence.models import Base, utcnow


class ProviderTraceRecord(Base):
    """One correlated provider request, retries, and eventual result."""

    __tablename__ = "provider_traces"

    trace_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    trace_mode: Mapped[str] = mapped_column(String(24), default="summary")
    endpoint: Mapped[str] = mapped_column(Text, default="")
    request_model: Mapped[str] = mapped_column(String(200), default="", index=True)
    response_model: Mapped[str] = mapped_column(String(200), default="")
    request_json: Mapped[str] = mapped_column(Text, default="{}")
    retries_json: Mapped[str] = mapped_column(Text, default="[]")
    response_json: Mapped[str] = mapped_column(Text, default="{}")
    error_json: Mapped[str] = mapped_column(Text, default="{}")
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ProviderTraceIndexRecord(Base):
    """Query-efficient account and category metadata for one provider trace."""

    __tablename__ = "provider_trace_indexes"

    trace_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    deployment_id: Mapped[str] = mapped_column(String(64), default="")
    character_card_id: Mapped[str] = mapped_column(String(64), default="")
    category: Mapped[str] = mapped_column(String(32), default="model_call", index=True)
    tool_names_json: Mapped[str] = mapped_column(Text, default="[]")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
