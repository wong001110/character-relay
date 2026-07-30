"""SQLAlchemy persistence models."""

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
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


class PromptVersionRecord(Base):
    __tablename__ = "prompt_versions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    character_card_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    temperature: Mapped[float] = mapped_column(Float, nullable=False)
    config_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_production: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ExperimentMatrixRecord(Base):
    __tablename__ = "experiment_matrices"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="draft", nullable=False)
    definition_json: Mapped[str] = mapped_column(Text, nullable=False)
    total_tasks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pending_tasks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    running_tasks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_tasks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_tasks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cancelled_tasks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_baseline: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ExperimentMatrixTaskRecord(Base):
    __tablename__ = "experiment_matrix_tasks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    matrix_id: Mapped[str] = mapped_column(
        ForeignKey("experiment_matrices.id"), index=True, nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False)
    combination_json: Mapped[str] = mapped_column(Text, nullable=False)
    run_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    backoff_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


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


class UserRecord(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="user", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class AuthSessionRecord(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    user_agent_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class InvitationRecord(Base):
    __tablename__ = "invitations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    code_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    role: Mapped[str] = mapped_column(String(20), default="user", nullable=False)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    accepted_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EncryptedCredentialRecord(Base):
    __tablename__ = "encrypted_credentials"
    __table_args__ = (
        UniqueConstraint(
            "owner_id",
            "scope_kind",
            "scope_id",
            name="uq_encrypted_credentials_owner_scope",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    scope_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    scope_id: Mapped[str] = mapped_column(String(120), nullable=False)
    encrypted_value: Mapped[str] = mapped_column(Text, nullable=False)
    key_version: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TargetOwnershipRecord(Base):
    __tablename__ = "target_ownership"
    __table_args__ = (
        UniqueConstraint(
            "target_id",
            "owner_id",
            name="uq_target_ownership_target_owner",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    target_id: Mapped[str] = mapped_column(ForeignKey("targets.id"), index=True, nullable=False)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditEventRecord(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    resource_type: Mapped[str] = mapped_column(String(60), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
