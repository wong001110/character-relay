"""Persistence, versioning, grounding, and archive operations for calibration data."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

from sqlalchemy import delete, func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from echo_masque.calibration import (
    CalibrationArchive,
    CalibrationCaseCreate,
    CalibrationCaseUpdate,
    CalibrationCaseView,
    CalibrationDatasetCreate,
    CalibrationDatasetStatus,
    CalibrationDatasetUpdate,
    CalibrationDatasetView,
    CalibrationImportResult,
    CalibrationRunImport,
)
from echo_masque.persistence.calibration_models import (
    CalibrationCaseRecord,
    CalibrationDatasetRecord,
)
from echo_masque.persistence.database import Database
from echo_masque.persistence.repository import Repository
from echo_masque.persistence.workspace_repository import WorkspaceRepository


class CalibrationConflict(RuntimeError):
    """Raised when a calibration mutation violates the human-approval boundary."""


class CalibrationRepository:
    def __init__(
        self,
        database: Database,
        repository: Repository,
        workspace_repository: WorkspaceRepository,
    ) -> None:
        self.database = database
        self.repository = repository
        self.workspace_repository = workspace_repository

    def list_datasets(self, owner_id: str) -> list[CalibrationDatasetView]:
        with self.database.session() as session:
            records = session.scalars(
                select(CalibrationDatasetRecord)
                .where(CalibrationDatasetRecord.owner_id == owner_id)
                .order_by(
                    CalibrationDatasetRecord.updated_at.desc(),
                    CalibrationDatasetRecord.version.desc(),
                )
            )
            return [self._dataset_view(session, record) for record in records]

    def get_dataset(
        self,
        dataset_id: str,
        owner_id: str,
    ) -> CalibrationDatasetView | None:
        with self.database.session() as session:
            record = session.get(CalibrationDatasetRecord, dataset_id)
            if record is None or record.owner_id != owner_id:
                return None
            return self._dataset_view(session, record)

    def create_dataset(
        self,
        owner_id: str,
        payload: CalibrationDatasetCreate,
    ) -> CalibrationDatasetView:
        dataset_id = str(uuid4())
        record = CalibrationDatasetRecord(
            id=dataset_id,
            owner_id=owner_id,
            lineage_id=dataset_id,
            parent_dataset_id=None,
            name=payload.name,
            description=payload.description,
            version=1,
            status="draft",
        )
        with self.database.session() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
            return self._dataset_view(session, record)

    def update_dataset(
        self,
        dataset_id: str,
        owner_id: str,
        payload: CalibrationDatasetUpdate,
    ) -> CalibrationDatasetView | None:
        with self.database.session() as session:
            record = self._owned_dataset(session, dataset_id, owner_id)
            if record is None:
                return None
            self._require_draft(record)
            record.name = payload.name
            record.description = payload.description
            record.updated_at = datetime.now(UTC)
            session.commit()
            session.refresh(record)
            return self._dataset_view(session, record)

    def approve_dataset(
        self,
        dataset_id: str,
        owner_id: str,
    ) -> CalibrationDatasetView | None:
        with self.database.session() as session:
            record = self._owned_dataset(session, dataset_id, owner_id)
            if record is None:
                return None
            self._require_draft(record)
            case_count = session.scalar(
                select(func.count())
                .select_from(CalibrationCaseRecord)
                .where(CalibrationCaseRecord.dataset_id == dataset_id)
            )
            if int(case_count or 0) == 0:
                raise CalibrationConflict(
                    "A Calibration Dataset requires at least one Case before approval."
                )
            now = datetime.now(UTC)
            record.status = "approved"
            record.approved_at = now
            record.updated_at = now
            session.commit()
            session.refresh(record)
            return self._dataset_view(session, record)

    def archive_dataset(
        self,
        dataset_id: str,
        owner_id: str,
    ) -> CalibrationDatasetView | None:
        with self.database.session() as session:
            record = self._owned_dataset(session, dataset_id, owner_id)
            if record is None:
                return None
            if record.status == "archived":
                return self._dataset_view(session, record)
            now = datetime.now(UTC)
            record.status = "archived"
            record.archived_at = now
            record.updated_at = now
            session.commit()
            session.refresh(record)
            return self._dataset_view(session, record)

    def create_next_version(
        self,
        dataset_id: str,
        owner_id: str,
    ) -> CalibrationDatasetView | None:
        with self.database.session() as session:
            source = self._owned_dataset(session, dataset_id, owner_id)
            if source is None:
                return None
            if source.status == "draft":
                raise CalibrationConflict(
                    "Finish or archive the current Draft before creating a new version."
                )
            latest = session.scalar(
                select(func.max(CalibrationDatasetRecord.version)).where(
                    CalibrationDatasetRecord.owner_id == owner_id,
                    CalibrationDatasetRecord.lineage_id == source.lineage_id,
                )
            )
            next_record = CalibrationDatasetRecord(
                id=str(uuid4()),
                owner_id=owner_id,
                lineage_id=source.lineage_id,
                parent_dataset_id=source.id,
                name=source.name,
                description=source.description,
                version=int(latest or source.version) + 1,
                status="draft",
            )
            session.add(next_record)
            session.flush()
            source_cases = self._case_records(session, source.id)
            for item in source_cases:
                session.add(
                    CalibrationCaseRecord(
                        id=str(uuid4()),
                        dataset_id=next_record.id,
                        owner_id=owner_id,
                        position=item.position,
                        source=item.source,
                        run_id=item.run_id,
                        scenario_id=item.scenario_id,
                        character_card_id=item.character_card_id,
                        scenario_name=item.scenario_name,
                        scenario_category=item.scenario_category,
                        language=item.language,
                        turn_index=item.turn_index,
                        tester_message=item.tester_message,
                        subject_response=item.subject_response,
                        expected_verdict=item.expected_verdict,
                        failure_type=item.failure_type,
                        evidence_excerpt=item.evidence_excerpt,
                        coverage_dimensions_json=item.coverage_dimensions_json,
                        notes=item.notes,
                    )
                )
            session.commit()
            session.refresh(next_record)
            return self._dataset_view(session, next_record)

    def delete_dataset(self, dataset_id: str, owner_id: str) -> bool:
        with self.database.session() as session:
            record = self._owned_dataset(session, dataset_id, owner_id)
            if record is None:
                return False
            self._require_draft(record)
            session.execute(
                delete(CalibrationCaseRecord).where(
                    CalibrationCaseRecord.dataset_id == dataset_id
                )
            )
            session.delete(record)
            session.commit()
            return True

    def create_case(
        self,
        dataset_id: str,
        owner_id: str,
        payload: CalibrationCaseCreate,
    ) -> CalibrationCaseView | None:
        with self.database.session() as session:
            dataset = self._owned_dataset(session, dataset_id, owner_id)
            if dataset is None:
                return None
            self._require_draft(dataset)
            record = CalibrationCaseRecord(
                id=str(uuid4()),
                dataset_id=dataset_id,
                owner_id=owner_id,
                position=self._next_position(session, dataset_id),
                source="manual",
                run_id=None,
                **self._case_columns(payload),
            )
            session.add(record)
            dataset.updated_at = datetime.now(UTC)
            session.commit()
            session.refresh(record)
            return self._case_view(record)

    def update_case(
        self,
        case_id: str,
        owner_id: str,
        payload: CalibrationCaseUpdate,
    ) -> CalibrationCaseView | None:
        with self.database.session() as session:
            record = session.get(CalibrationCaseRecord, case_id)
            if record is None or record.owner_id != owner_id:
                return None
            dataset = self._owned_dataset(session, record.dataset_id, owner_id)
            if dataset is None:
                return None
            self._require_draft(dataset)
            for key, value in self._case_columns(payload).items():
                setattr(record, key, value)
            record.source = "manual"
            record.run_id = None
            record.updated_at = datetime.now(UTC)
            dataset.updated_at = record.updated_at
            session.commit()
            session.refresh(record)
            return self._case_view(record)

    def delete_case(self, case_id: str, owner_id: str) -> bool:
        with self.database.session() as session:
            record = session.get(CalibrationCaseRecord, case_id)
            if record is None or record.owner_id != owner_id:
                return False
            dataset = self._owned_dataset(session, record.dataset_id, owner_id)
            if dataset is None:
                return False
            self._require_draft(dataset)
            dataset_id = record.dataset_id
            session.delete(record)
            session.flush()
            self._normalize_positions(session, dataset_id)
            dataset.updated_at = datetime.now(UTC)
            session.commit()
            return True

    def import_run_case(
        self,
        dataset_id: str,
        owner_id: str,
        payload: CalibrationRunImport,
    ) -> CalibrationCaseView | None:
        snapshot = self.workspace_repository.get_run_snapshot(payload.run_id, owner_id)
        if snapshot is None:
            raise KeyError("Completed Run snapshot not found.")
        run = self.repository.get_run(payload.run_id)
        if run is None or run.status != "completed" or run.result_json is None:
            raise CalibrationConflict("Only a completed Run can enter a Calibration Dataset.")
        turn = next(
            (
                item
                for item in self.repository.replay(payload.run_id)
                if item.scenario_id == payload.scenario_id
                and item.turn_index == payload.turn_index
            ),
            None,
        )
        if turn is None:
            raise KeyError("The requested Run turn was not found.")
        scenario = next(
            (
                item
                for item in snapshot.scenarios
                if str(item.get("id", "")) == payload.scenario_id
            ),
            None,
        )
        if scenario is None:
            raise KeyError("Scenario snapshot not found for the requested Run turn.")
        character_id = snapshot.character_card_id
        case_payload = CalibrationCaseCreate(
            scenario_id=payload.scenario_id,
            character_card_id=character_id,
            scenario_name=str(scenario.get("name", payload.scenario_id)),
            scenario_category=str(
                scenario.get("category", scenario.get("kind", "unknown"))
            ),
            language=cast(str, scenario.get("language", "en")),
            turn_index=payload.turn_index,
            tester_message=turn.tester_message,
            subject_response=turn.target_response,
            expected_verdict=payload.expected_verdict,
            failure_type=payload.failure_type,
            evidence_excerpt=payload.evidence_excerpt,
            coverage_dimensions=payload.coverage_dimensions,
            notes=payload.notes,
        )
        with self.database.session() as session:
            dataset = self._owned_dataset(session, dataset_id, owner_id)
            if dataset is None:
                return None
            self._require_draft(dataset)
            record = CalibrationCaseRecord(
                id=str(uuid4()),
                dataset_id=dataset_id,
                owner_id=owner_id,
                position=self._next_position(session, dataset_id),
                source="run",
                run_id=payload.run_id,
                **self._case_columns(case_payload),
            )
            session.add(record)
            dataset.updated_at = datetime.now(UTC)
            session.commit()
            session.refresh(record)
            return self._case_view(record)

    def export_archive(self, owner_id: str) -> CalibrationArchive:
        return CalibrationArchive(
            exported_at=datetime.now(UTC),
            owner_id=owner_id,
            datasets=self.list_datasets(owner_id),
        )

    def import_archive(
        self,
        owner_id: str,
        archive: CalibrationArchive,
        mode: str,
    ) -> CalibrationImportResult:
        imported = {"datasets": 0, "cases": 0}
        skipped = {"datasets": 0, "cases": 0}
        with self.database.session() as session:
            if mode == "replace":
                self._delete_owner_in_session(session, owner_id)
            for dataset in archive.datasets:
                existing = session.get(CalibrationDatasetRecord, dataset.id)
                if existing is not None:
                    if existing.owner_id != owner_id:
                        raise CalibrationConflict(
                            "Calibration import conflicts with another user's Dataset."
                        )
                    skipped["datasets"] += 1
                    skipped["cases"] += len(dataset.cases)
                    continue
                session.add(self._dataset_record(owner_id, dataset))
                session.flush()
                imported["datasets"] += 1
                for item in dataset.cases:
                    session.add(self._case_record(owner_id, dataset.id, item))
                    imported["cases"] += 1
            session.commit()
        return CalibrationImportResult(imported=imported, skipped=skipped)

    def delete_owner(self, owner_id: str) -> dict[str, int]:
        with self.database.session() as session:
            counts = self._delete_owner_in_session(session, owner_id)
            session.commit()
            return counts

    def claim_owner(self, source_owner: str, destination_owner: str) -> dict[str, int]:
        with self.database.session() as session:
            cases = self._rowcount(
                session.execute(
                    update(CalibrationCaseRecord)
                    .where(CalibrationCaseRecord.owner_id == source_owner)
                    .values(owner_id=destination_owner)
                )
            )
            datasets = self._rowcount(
                session.execute(
                    update(CalibrationDatasetRecord)
                    .where(CalibrationDatasetRecord.owner_id == source_owner)
                    .values(owner_id=destination_owner)
                )
            )
            session.commit()
            return {"calibration_datasets": datasets, "calibration_cases": cases}

    @staticmethod
    def _owned_dataset(
        session: Session,
        dataset_id: str,
        owner_id: str,
    ) -> CalibrationDatasetRecord | None:
        record = session.get(CalibrationDatasetRecord, dataset_id)
        if record is None or record.owner_id != owner_id:
            return None
        return record

    @staticmethod
    def _require_draft(record: CalibrationDatasetRecord) -> None:
        if record.status != "draft":
            raise CalibrationConflict(
                "Approved or archived Calibration Datasets are immutable."
            )

    @staticmethod
    def _next_position(session: Session, dataset_id: str) -> int:
        latest = session.scalar(
            select(func.max(CalibrationCaseRecord.position)).where(
                CalibrationCaseRecord.dataset_id == dataset_id
            )
        )
        return int(latest if latest is not None else -1) + 1

    @staticmethod
    def _normalize_positions(session: Session, dataset_id: str) -> None:
        for position, record in enumerate(
            CalibrationRepository._case_records(session, dataset_id)
        ):
            record.position = position

    @staticmethod
    def _case_records(
        session: Session,
        dataset_id: str,
    ) -> list[CalibrationCaseRecord]:
        return list(
            session.scalars(
                select(CalibrationCaseRecord)
                .where(CalibrationCaseRecord.dataset_id == dataset_id)
                .order_by(CalibrationCaseRecord.position)
            )
        )

    @staticmethod
    def _case_columns(
        payload: CalibrationCaseCreate | CalibrationCaseUpdate,
    ) -> dict[str, object]:
        return {
            "scenario_id": payload.scenario_id,
            "character_card_id": payload.character_card_id,
            "scenario_name": payload.scenario_name,
            "scenario_category": payload.scenario_category,
            "language": payload.language,
            "turn_index": payload.turn_index,
            "tester_message": payload.tester_message,
            "subject_response": payload.subject_response,
            "expected_verdict": payload.expected_verdict,
            "failure_type": payload.failure_type,
            "evidence_excerpt": payload.evidence_excerpt,
            "coverage_dimensions_json": json.dumps(payload.coverage_dimensions),
            "notes": payload.notes,
        }

    @staticmethod
    def _dataset_view(
        session: Session,
        record: CalibrationDatasetRecord,
    ) -> CalibrationDatasetView:
        return CalibrationDatasetView(
            id=record.id,
            owner_id=record.owner_id,
            lineage_id=record.lineage_id,
            parent_dataset_id=record.parent_dataset_id,
            name=record.name,
            description=record.description,
            version=record.version,
            status=cast(CalibrationDatasetStatus, record.status),
            cases=[
                CalibrationRepository._case_view(item)
                for item in CalibrationRepository._case_records(session, record.id)
            ],
            created_at=record.created_at,
            updated_at=record.updated_at,
            approved_at=record.approved_at,
            archived_at=record.archived_at,
        )

    @staticmethod
    def _case_view(record: CalibrationCaseRecord) -> CalibrationCaseView:
        return CalibrationCaseView(
            id=record.id,
            dataset_id=record.dataset_id,
            owner_id=record.owner_id,
            position=record.position,
            source=cast(str, record.source),
            run_id=record.run_id,
            scenario_id=record.scenario_id,
            character_card_id=record.character_card_id,
            scenario_name=record.scenario_name,
            scenario_category=record.scenario_category,
            language=cast(str, record.language),
            turn_index=record.turn_index,
            tester_message=record.tester_message,
            subject_response=record.subject_response,
            expected_verdict=cast(str, record.expected_verdict),
            failure_type=record.failure_type,
            evidence_excerpt=record.evidence_excerpt,
            coverage_dimensions=json.loads(record.coverage_dimensions_json),
            notes=record.notes,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    @staticmethod
    def _dataset_record(
        owner_id: str,
        dataset: CalibrationDatasetView,
    ) -> CalibrationDatasetRecord:
        return CalibrationDatasetRecord(
            id=dataset.id,
            owner_id=owner_id,
            lineage_id=dataset.lineage_id,
            parent_dataset_id=dataset.parent_dataset_id,
            name=dataset.name,
            description=dataset.description,
            version=dataset.version,
            status=dataset.status,
            created_at=dataset.created_at,
            updated_at=dataset.updated_at,
            approved_at=dataset.approved_at,
            archived_at=dataset.archived_at,
        )

    @staticmethod
    def _case_record(
        owner_id: str,
        dataset_id: str,
        item: CalibrationCaseView,
    ) -> CalibrationCaseRecord:
        return CalibrationCaseRecord(
            id=item.id,
            dataset_id=dataset_id,
            owner_id=owner_id,
            position=item.position,
            source=item.source,
            run_id=item.run_id,
            scenario_id=item.scenario_id,
            character_card_id=item.character_card_id,
            scenario_name=item.scenario_name,
            scenario_category=item.scenario_category,
            language=item.language,
            turn_index=item.turn_index,
            tester_message=item.tester_message,
            subject_response=item.subject_response,
            expected_verdict=item.expected_verdict,
            failure_type=item.failure_type,
            evidence_excerpt=item.evidence_excerpt,
            coverage_dimensions_json=json.dumps(item.coverage_dimensions),
            notes=item.notes,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )

    @staticmethod
    def _delete_owner_in_session(session: Session, owner_id: str) -> dict[str, int]:
        cases = CalibrationRepository._rowcount(
            session.execute(
                delete(CalibrationCaseRecord).where(
                    CalibrationCaseRecord.owner_id == owner_id
                )
            )
        )
        datasets = CalibrationRepository._rowcount(
            session.execute(
                delete(CalibrationDatasetRecord).where(
                    CalibrationDatasetRecord.owner_id == owner_id
                )
            )
        )
        return {"calibration_datasets": datasets, "calibration_cases": cases}

    @staticmethod
    def _rowcount(result: object) -> int:
        cursor = cast(CursorResult[object], result)
        return int(cursor.rowcount or 0)
