"""Immutable Judge evaluation snapshot persistence models."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from echo_masque.persistence.models import Base, utcnow


class JudgeEvaluationRecord(Base):
    __tablename__ = "judge_evaluations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("calibration_datasets.id"), index=True, nullable=False
    )
    dataset_version: Mapped[int] = mapped_column(Integer, nullable=False)
    dataset_name: Mapped[str] = mapped_column(String(160), nullable=False)
    modes_json: Mapped[str] = mapped_column(Text, nullable=False)
    judge_config_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    metrics_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="completed", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class JudgePredictionRecord(Base):
    __tablename__ = "judge_predictions"
    __table_args__ = (
        UniqueConstraint(
            "evaluation_id",
            "case_id",
            "mode",
            name="uq_judge_prediction_evaluation_case_mode",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    evaluation_id: Mapped[str] = mapped_column(
        ForeignKey("judge_evaluations.id"), index=True, nullable=False
    )
    case_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    expected_verdict: Mapped[str] = mapped_column(String(20), nullable=False)
    predicted_verdict: Mapped[str | None] = mapped_column(String(20), nullable=True)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence: Mapped[str | None] = mapped_column(String(40), nullable=True)
    failure_types_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    dimensions_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    evidence_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    contract_source: Mapped[str] = mapped_column(String(30), default="generic", nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
