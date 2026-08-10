"""Persistence models for Phase 5 durable orchestration and Runtime Trace."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from echo_masque.persistence.models import Base, utcnow


class RuntimeOperationRecord(Base):
    """One durable connector-level workflow operation."""

    __tablename__ = "runtime_operations"

    operation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    operation_kind: Mapped[str] = mapped_column(String(32), default="social_turn", index=True)
    owner_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    connection_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    guild_id: Mapped[str] = mapped_column(String(200), default="")
    channel_id: Mapped[str] = mapped_column(String(200), default="")
    thread_id: Mapped[str] = mapped_column(String(200), default="")
    source_message_id: Mapped[str] = mapped_column(String(200), default="", index=True)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    initial_deployment_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    available_deployment_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    cursor_json: Mapped[str] = mapped_column(Text, default="{}")
    sources_json: Mapped[str] = mapped_column(Text, default="[]")
    continuation_budget: Mapped[int] = mapped_column(Integer, default=0)
    max_depth: Mapped[int] = mapped_column(Integer, default=0)
    resume_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RuntimeStepRecord(Base):
    """One idempotent Character generation + delivery boundary."""

    __tablename__ = "runtime_steps"
    __table_args__ = (
        UniqueConstraint("operation_id", "step_index", name="uq_runtime_step_operation_index"),
    )

    step_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    operation_id: Mapped[str] = mapped_column(String(64), index=True)
    step_index: Mapped[int] = mapped_column(Integer, default=0)
    deployment_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    status: Mapped[str] = mapped_column(String(32), default="generating", index=True)
    request_hash: Mapped[str] = mapped_column(String(64), default="")
    response_json: Mapped[str] = mapped_column(Text, default="{}")
    cursor_json: Mapped[str] = mapped_column(Text, default="{}")
    delivery_claim_nonce: Mapped[str] = mapped_column(String(64), default="")
    sent_message_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    outgoing_text: Mapped[str] = mapped_column(Text, default="")
    applied: Mapped[bool] = mapped_column(Boolean, default=False)
    last_error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RuntimeSideEffectRecord(Base):
    """At-most-once ledger entry for one side-effect Tool execution."""

    __tablename__ = "runtime_side_effects"

    idempotency_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    operation_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    step_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    deployment_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    tool_id: Mapped[str] = mapped_column(String(120), default="", index=True)
    arguments_hash: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(24), default="claimed", index=True)
    content: Mapped[str] = mapped_column(Text, default="")
    trace_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class RuntimeTraceRunRecord(Base):
    """Query-efficient summary of one LangGraph invocation."""

    __tablename__ = "runtime_trace_runs"

    graph_run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    trace_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    operation_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    graph_name: Mapped[str] = mapped_column(String(64), default="", index=True)
    status: Mapped[str] = mapped_column(String(24), default="running", index=True)
    owner_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    deployment_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    character_card_id: Mapped[str] = mapped_column(String(64), default="")
    last_node: Mapped[str] = mapped_column(String(120), default="")
    event_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class RuntimeTraceEventRecord(Base):
    """One privacy-safe node transition in a durable Runtime trace."""

    __tablename__ = "runtime_trace_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    graph_run_id: Mapped[str] = mapped_column(String(64), index=True)
    trace_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    operation_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    graph_name: Mapped[str] = mapped_column(String(64), default="", index=True)
    node_name: Mapped[str] = mapped_column(String(120), default="")
    node_kind: Mapped[str] = mapped_column(String(32), default="")
    status: Mapped[str] = mapped_column(String(24), default="")
    changed_keys_json: Mapped[str] = mapped_column(Text, default="[]")
    metadata_json: Mapped[str] = mapped_column(Text, default="[]")
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
