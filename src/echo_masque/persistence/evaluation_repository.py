"""Persistence for immutable Judge evaluation snapshots and predictions."""

from __future__ import annotations

import json
from typing import cast
from uuid import uuid4

from pydantic import TypeAdapter
from sqlalchemy import delete, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from echo_masque.evaluation_analytics import (
    ContractSource,
    EvaluationMode,
    EvaluationStatus,
    EvaluationVerdict,
    JudgeEvaluationMetrics,
    JudgeEvaluationView,
    JudgePredictionView,
)
from echo_masque.persistence.database import Database
from echo_masque.persistence.evaluation_models import (
    JudgeEvaluationRecord,
    JudgePredictionRecord,
)

_MODES = TypeAdapter(list[EvaluationMode])
_STATUS = TypeAdapter(EvaluationStatus)
_VERDICT = TypeAdapter(EvaluationVerdict)
_OPTIONAL_VERDICT = TypeAdapter(EvaluationVerdict | None)
_CONTRACT_SOURCE = TypeAdapter(ContractSource)
_STRING_LIST = TypeAdapter(list[str])
_INT_MAP = TypeAdapter(dict[str, int])
_OBJECT_LIST = TypeAdapter(list[dict[str, object]])
_OBJECT_MAP = TypeAdapter(dict[str, object])


class EvaluationRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def save(
        self,
        *,
        owner_id: str,
        dataset_id: str,
        dataset_version: int,
        dataset_name: str,
        modes: list[EvaluationMode],
        judge_config: dict[str, object],
        metrics: JudgeEvaluationMetrics,
        status: EvaluationStatus,
        predictions: list[JudgePredictionView],
    ) -> JudgeEvaluationView:
        evaluation_id = str(uuid4())
        record = JudgeEvaluationRecord(
            id=evaluation_id,
            owner_id=owner_id,
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            dataset_name=dataset_name,
            modes_json=json.dumps(modes),
            judge_config_json=json.dumps(judge_config, ensure_ascii=False),
            metrics_json=metrics.model_dump_json(),
            status=status,
        )
        with self.database.session() as session:
            session.add(record)
            session.flush()
            for item in predictions:
                session.add(
                    JudgePredictionRecord(
                        id=str(uuid4()),
                        evaluation_id=evaluation_id,
                        case_id=item.case_id,
                        mode=item.mode,
                        expected_verdict=item.expected_verdict,
                        predicted_verdict=item.predicted_verdict,
                        score=item.score,
                        confidence=(
                            str(item.confidence)
                            if item.confidence is not None
                            else None
                        ),
                        failure_types_json=json.dumps(item.failure_types),
                        dimensions_json=json.dumps(item.dimensions),
                        evidence_json=json.dumps(item.evidence, ensure_ascii=False),
                        contract_source=item.contract_source,
                        error=item.error,
                    )
                )
            session.commit()
            session.refresh(record)
            return self._evaluation_view(session, record)

    def list(self, owner_id: str) -> list[JudgeEvaluationView]:
        with self.database.session() as session:
            records = session.scalars(
                select(JudgeEvaluationRecord)
                .where(JudgeEvaluationRecord.owner_id == owner_id)
                .order_by(JudgeEvaluationRecord.created_at.desc())
            )
            return [self._evaluation_view(session, item) for item in records]

    def get(
        self,
        evaluation_id: str,
        owner_id: str,
    ) -> JudgeEvaluationView | None:
        with self.database.session() as session:
            record = session.get(JudgeEvaluationRecord, evaluation_id)
            if record is None or record.owner_id != owner_id:
                return None
            return self._evaluation_view(session, record)

    def delete_owner(self, owner_id: str) -> dict[str, int]:
        with self.database.session() as session:
            evaluation_ids = list(
                session.scalars(
                    select(JudgeEvaluationRecord.id).where(
                        JudgeEvaluationRecord.owner_id == owner_id
                    )
                )
            )
            predictions = 0
            if evaluation_ids:
                predictions = self._rowcount(
                    session.execute(
                        delete(JudgePredictionRecord).where(
                            JudgePredictionRecord.evaluation_id.in_(evaluation_ids)
                        )
                    )
                )
            evaluations = self._rowcount(
                session.execute(
                    delete(JudgeEvaluationRecord).where(
                        JudgeEvaluationRecord.owner_id == owner_id
                    )
                )
            )
            session.commit()
            return {
                "judge_evaluations": evaluations,
                "judge_predictions": predictions,
            }

    def claim_owner(self, source_owner: str, destination_owner: str) -> dict[str, int]:
        with self.database.session() as session:
            evaluations = self._rowcount(
                session.execute(
                    update(JudgeEvaluationRecord)
                    .where(JudgeEvaluationRecord.owner_id == source_owner)
                    .values(owner_id=destination_owner)
                )
            )
            session.commit()
            return {"judge_evaluations": evaluations}

    @staticmethod
    def _evaluation_view(
        session: Session,
        record: JudgeEvaluationRecord,
    ) -> JudgeEvaluationView:
        predictions = list(
            session.scalars(
                select(JudgePredictionRecord)
                .where(JudgePredictionRecord.evaluation_id == record.id)
                .order_by(
                    JudgePredictionRecord.case_id,
                    JudgePredictionRecord.mode,
                )
            )
        )
        return JudgeEvaluationView(
            id=record.id,
            owner_id=record.owner_id,
            dataset_id=record.dataset_id,
            dataset_version=record.dataset_version,
            dataset_name=record.dataset_name,
            modes=_MODES.validate_python(json.loads(record.modes_json)),
            judge_config=_OBJECT_MAP.validate_python(
                json.loads(record.judge_config_json)
            ),
            metrics=JudgeEvaluationMetrics.model_validate_json(record.metrics_json),
            status=_STATUS.validate_python(record.status),
            predictions=[
                EvaluationRepository._prediction_view(item)
                for item in predictions
            ],
            created_at=record.created_at,
        )

    @staticmethod
    def _prediction_view(record: JudgePredictionRecord) -> JudgePredictionView:
        return JudgePredictionView(
            id=record.id,
            evaluation_id=record.evaluation_id,
            case_id=record.case_id,
            mode=TypeAdapter(EvaluationMode).validate_python(record.mode),
            expected_verdict=_VERDICT.validate_python(record.expected_verdict),
            predicted_verdict=_OPTIONAL_VERDICT.validate_python(
                record.predicted_verdict
            ),
            score=record.score,
            confidence=(
                float(record.confidence)
                if record.confidence is not None
                else None
            ),
            failure_types=_STRING_LIST.validate_python(
                json.loads(record.failure_types_json)
            ),
            dimensions=_INT_MAP.validate_python(
                json.loads(record.dimensions_json)
            ),
            evidence=_OBJECT_LIST.validate_python(
                json.loads(record.evidence_json)
            ),
            contract_source=_CONTRACT_SOURCE.validate_python(
                record.contract_source
            ),
            error=record.error,
            created_at=record.created_at,
        )

    @staticmethod
    def _rowcount(result: object) -> int:
        cursor = cast(CursorResult[object], result)
        return int(cursor.rowcount or 0)
