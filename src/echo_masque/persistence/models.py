"""SQLAlchemy persistence models."""

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class TargetRecord(Base):
    __tablename__ = "targets"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    target_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    config_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CharacterCardRecord(Base):
    __tablename__ = "character_cards"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    target_id: Mapped[str] = mapped_column(ForeignKey("targets.id"), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    subtitle: Mapped[str] = mapped_column(String(180), default="", nullable=False)
    subject_type: Mapped[str] = mapped_column(String(40), default="custom", nullable=False)
    persona_summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    traits_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    tags_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    expected_tone: Mapped[str | None] = mapped_column(Text, nullable=True)
    forbidden_behaviors_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    memory_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    preferred_suites_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    portrait_variant: Mapped[str] = mapped_column(String(40), default="lavender", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AdminRuntimeRecord(Base):
    __tablename__ = "admin_runtime"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default="default")
    config_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class TrialRunRecord(Base):
    __tablename__ = "trial_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    target_id: Mapped[str] = mapped_column(ForeignKey("targets.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    suite_json: Mapped[str] = mapped_column(Text, nullable=False)
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class CharacterTrialRecord(Base):
    __tablename__ = "character_trials"

    run_id: Mapped[str] = mapped_column(ForeignKey("trial_runs.id"), primary_key=True)
    character_card_id: Mapped[str] = mapped_column(
        ForeignKey("character_cards.id"), index=True, nullable=False
    )


class TurnRecord(Base):
    __tablename__ = "trial_turns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("trial_runs.id"), index=True)
    scenario_id: Mapped[str] = mapped_column(String(120), nullable=False)
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False)
    tester_message: Mapped[str] = mapped_column(Text, nullable=False)
    target_response: Mapped[str] = mapped_column(Text, nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    trace_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)


class TrialEventRecord(Base):
    __tablename__ = "trial_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("trial_runs.id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    scenario_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    turn_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payload_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EvidenceRecord(Base):
    __tablename__ = "trial_evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("trial_runs.id"), index=True)
    scenario_id: Mapped[str] = mapped_column(String(120), nullable=False)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False)
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)


class CustomScenarioRecord(Base):
    __tablename__ = "custom_scenarios"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    language: Mapped[str] = mapped_column(String(20), nullable=False)
    messages_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    expected_behavior: Mapped[str] = mapped_column(Text, nullable=False)
    forbidden_phrases_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    required_phrases_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    severity: Mapped[str] = mapped_column(String(20), default="medium", nullable=False)
    max_turns: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    recommended_tester_mode: Mapped[str] = mapped_column(
        String(30), default="benchmark", nullable=False
    )
    recommended_judge_mode: Mapped[str] = mapped_column(
        String(30), default="hybrid", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class TestPackRecord(Base):
    __tablename__ = "test_packs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class TestPackItemRecord(Base):
    __tablename__ = "test_pack_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pack_id: Mapped[str] = mapped_column(ForeignKey("test_packs.id"), index=True)
    scenario_id: Mapped[str] = mapped_column(ForeignKey("custom_scenarios.id"), index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class RunSnapshotRecord(Base):
    __tablename__ = "run_snapshots"

    run_id: Mapped[str] = mapped_column(ForeignKey("trial_runs.id"), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    character_card_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    test_pack_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    character_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    target_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    pack_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    scenarios_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    rerun_of: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_baseline: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PersistenceProbeRecord(Base):
    __tablename__ = "persistence_probes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    marker: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class StorageMetadataRecord(Base):
    __tablename__ = "storage_metadata"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default="default")
    instance_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
