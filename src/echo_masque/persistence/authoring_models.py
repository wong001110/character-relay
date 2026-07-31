"""SQLAlchemy models for Phase 16 reviewable authoring drafts."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from echo_masque.persistence.models import Base, utcnow


class AuthoringRuntimeRecord(Base):
    __tablename__ = "authoring_runtime"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default="default")
    config_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class AuthoringScenarioDraftRecord(Base):
    __tablename__ = "authoring_scenario_drafts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
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
    provenance_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    review_notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    approved_scenario_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuthoringTestPackDraftRecord(Base):
    __tablename__ = "authoring_test_pack_drafts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    provenance_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    review_notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    approved_test_pack_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuthoringTestPackDraftItemRecord(Base):
    __tablename__ = "authoring_test_pack_draft_items"
    __table_args__ = (
        UniqueConstraint("pack_draft_id", "position", name="uq_authoring_pack_draft_position"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pack_draft_id: Mapped[str] = mapped_column(
        ForeignKey("authoring_test_pack_drafts.id"), index=True, nullable=False
    )
    scenario_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    scenario_draft_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
