"""SQLAlchemy models for human-controlled calibration datasets."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from echo_masque.persistence.models import Base, utcnow


class CalibrationDatasetRecord(Base):
    __tablename__ = "calibration_datasets"
    __table_args__ = (
        UniqueConstraint(
            "owner_id",
            "lineage_id",
            "version",
            name="uq_calibration_dataset_lineage_version",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    lineage_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    parent_dataset_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CalibrationCaseRecord(Base):
    __tablename__ = "calibration_cases"
    __table_args__ = (
        UniqueConstraint(
            "dataset_id",
            "position",
            name="uq_calibration_case_dataset_position",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("calibration_datasets.id"), index=True, nullable=False
    )
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str | None] = mapped_column(
        String(20), default="manual", nullable=False
    )
    run_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    scenario_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    character_card_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    scenario_name: Mapped[str] = mapped_column(String(160), nullable=False)
    scenario_category: Mapped[str] = mapped_column(String(80), nullable=False)
    language: Mapped[str | None] = mapped_column(String(20), nullable=False)
    turn_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tester_message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    subject_response: Mapped[str] = mapped_column(Text, nullable=False)
    expected_verdict: Mapped[str | None] = mapped_column(String(20), nullable=False)
    failure_type: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    evidence_excerpt: Mapped[str] = mapped_column(Text, default="", nullable=False)
    coverage_dimensions_json: Mapped[str] = mapped_column(
        Text, default="[]", nullable=False
    )
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
