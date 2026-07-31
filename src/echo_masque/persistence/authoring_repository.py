"""Persistence and approval state machine for Phase 16 authoring drafts."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from echo_masque.authoring import (
    DraftStatus,
    PackDraftItemInput,
    ScenarioDraftCreate,
    ScenarioDraftUpdate,
    ScenarioDraftView,
    TestPackDraftCreate,
    TestPackDraftUpdate,
    TestPackDraftView,
)
from echo_masque.persistence.authoring_models import (
    AuthoringScenarioDraftRecord,
    AuthoringTestPackDraftItemRecord,
    AuthoringTestPackDraftRecord,
)
from echo_masque.persistence.database import Database
from echo_masque.persistence.models import (
    CustomScenarioRecord,
    TestPackItemRecord,
    TestPackRecord,
)
from echo_masque.persistence.workspace_repository import WorkspaceRepository
from echo_masque.workspace import ScenarioView, TestPackView


class AuthoringConflict(RuntimeError):
    """Raised when a draft transition or reference violates the review boundary."""


class AuthoringRepository:
    def __init__(self, database: Database, workspace_repository: WorkspaceRepository) -> None:
        self.database = database
        self.workspace_repository = workspace_repository

    # Scenario drafts
    def list_scenario_drafts(
        self,
        owner_id: str,
        *,
        status: DraftStatus | None = None,
    ) -> list[ScenarioDraftView]:
        with self.database.session() as session:
            statement = select(AuthoringScenarioDraftRecord).where(
                AuthoringScenarioDraftRecord.owner_id == owner_id
            )
            if status is not None:
                statement = statement.where(AuthoringScenarioDraftRecord.status == status)
            records = session.scalars(
                statement.order_by(AuthoringScenarioDraftRecord.updated_at.desc())
            )
            return [self._scenario_view(record) for record in records]

    def get_scenario_draft(
        self,
        draft_id: str,
        owner_id: str,
    ) -> ScenarioDraftView | None:
        with self.database.session() as session:
            record = session.get(AuthoringScenarioDraftRecord, draft_id)
            if record is None or record.owner_id != owner_id:
                return None
            return self._scenario_view(record)

    def create_scenario_draft(
        self,
        owner_id: str,
        payload: ScenarioDraftCreate,
    ) -> ScenarioDraftView:
        record = AuthoringScenarioDraftRecord(
            id=str(uuid4()),
            owner_id=owner_id,
            status="draft",
            revision=1,
            **self._scenario_columns(payload),
        )
        with self.database.session() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
            return self._scenario_view(record)

    def update_scenario_draft(
        self,
        draft_id: str,
        owner_id: str,
        payload: ScenarioDraftUpdate,
    ) -> ScenarioDraftView | None:
        with self.database.session() as session:
            record = session.get(AuthoringScenarioDraftRecord, draft_id)
            if record is None or record.owner_id != owner_id:
                return None
            if record.status == "approved":
                raise AuthoringConflict("An approved Scenario Draft is immutable.")
            for key, value in self._scenario_columns(payload).items():
                setattr(record, key, value)
            record.status = "draft"
            record.revision += 1
            record.rejected_at = None
            record.updated_at = datetime.now(UTC)
            session.commit()
            session.refresh(record)
            return self._scenario_view(record)

    def reject_scenario_draft(
        self,
        draft_id: str,
        owner_id: str,
    ) -> ScenarioDraftView | None:
        with self.database.session() as session:
            record = session.get(AuthoringScenarioDraftRecord, draft_id)
            if record is None or record.owner_id != owner_id:
                return None
            if record.status == "approved":
                raise AuthoringConflict("An approved Scenario Draft cannot be rejected.")
            if record.status != "rejected":
                now = datetime.now(UTC)
                record.status = "rejected"
                record.rejected_at = now
                record.updated_at = now
                session.commit()
                session.refresh(record)
            return self._scenario_view(record)

    def approve_scenario_draft(
        self,
        draft_id: str,
        owner_id: str,
    ) -> tuple[ScenarioDraftView, ScenarioView] | None:
        with self.database.session() as session:
            record = session.get(AuthoringScenarioDraftRecord, draft_id)
            if record is None or record.owner_id != owner_id:
                return None
            if record.status != "draft":
                raise AuthoringConflict("Only an active Scenario Draft can be approved.")
            scenario_id = str(uuid4())
            session.add(
                CustomScenarioRecord(
                    id=scenario_id,
                    owner_id=owner_id,
                    name=record.name,
                    category=record.category,
                    description=record.description,
                    language=record.language,
                    messages_json=record.messages_json,
                    expected_behavior=record.expected_behavior,
                    forbidden_phrases_json=record.forbidden_phrases_json,
                    required_phrases_json=record.required_phrases_json,
                    severity=record.severity,
                    max_turns=record.max_turns,
                    recommended_tester_mode=record.recommended_tester_mode,
                    recommended_judge_mode=record.recommended_judge_mode,
                )
            )
            now = datetime.now(UTC)
            record.status = "approved"
            record.approved_scenario_id = scenario_id
            record.approved_at = now
            record.updated_at = now
            session.commit()
            session.refresh(record)
            draft = self._scenario_view(record)
        scenario = self.workspace_repository.get_scenario(scenario_id, owner_id)
        if scenario is None:
            raise RuntimeError("Approved Scenario could not be loaded.")
        return draft, scenario

    def delete_scenario_draft(self, draft_id: str, owner_id: str) -> bool:
        with self.database.session() as session:
            record = session.get(AuthoringScenarioDraftRecord, draft_id)
            if record is None or record.owner_id != owner_id:
                return False
            if record.status == "approved":
                raise AuthoringConflict("Approved Scenario Draft provenance cannot be deleted.")
            session.execute(
                delete(AuthoringTestPackDraftItemRecord).where(
                    AuthoringTestPackDraftItemRecord.scenario_draft_id == draft_id
                )
            )
            session.delete(record)
            session.commit()
            return True

    # Test Pack drafts
    def list_test_pack_drafts(
        self,
        owner_id: str,
        *,
        status: DraftStatus | None = None,
    ) -> list[TestPackDraftView]:
        with self.database.session() as session:
            statement = select(AuthoringTestPackDraftRecord).where(
                AuthoringTestPackDraftRecord.owner_id == owner_id
            )
            if status is not None:
                statement = statement.where(AuthoringTestPackDraftRecord.status == status)
            records = session.scalars(
                statement.order_by(AuthoringTestPackDraftRecord.updated_at.desc())
            )
            return [self._pack_view(session, record) for record in records]

    def get_test_pack_draft(
        self,
        draft_id: str,
        owner_id: str,
    ) -> TestPackDraftView | None:
        with self.database.session() as session:
            record = session.get(AuthoringTestPackDraftRecord, draft_id)
            if record is None or record.owner_id != owner_id:
                return None
            return self._pack_view(session, record)

    def create_test_pack_draft(
        self,
        owner_id: str,
        payload: TestPackDraftCreate,
    ) -> TestPackDraftView:
        with self.database.session() as session:
            self._validate_pack_references(session, owner_id, payload.items)
            record = AuthoringTestPackDraftRecord(
                id=str(uuid4()),
                owner_id=owner_id,
                status="draft",
                revision=1,
                name=payload.name,
                description=payload.description,
                provenance_json=payload.provenance.model_dump_json(),
                review_notes=payload.review_notes,
            )
            session.add(record)
            session.flush()
            self._replace_pack_items(session, record.id, payload.items)
            session.commit()
            session.refresh(record)
            return self._pack_view(session, record)

    def update_test_pack_draft(
        self,
        draft_id: str,
        owner_id: str,
        payload: TestPackDraftUpdate,
    ) -> TestPackDraftView | None:
        with self.database.session() as session:
            record = session.get(AuthoringTestPackDraftRecord, draft_id)
            if record is None or record.owner_id != owner_id:
                return None
            if record.status == "approved":
                raise AuthoringConflict("An approved Test Pack Draft is immutable.")
            self._validate_pack_references(session, owner_id, payload.items)
            record.name = payload.name
            record.description = payload.description
            record.provenance_json = payload.provenance.model_dump_json()
            record.review_notes = payload.review_notes
            record.status = "draft"
            record.revision += 1
            record.rejected_at = None
            record.updated_at = datetime.now(UTC)
            self._replace_pack_items(session, record.id, payload.items)
            session.commit()
            session.refresh(record)
            return self._pack_view(session, record)

    def reject_test_pack_draft(
        self,
        draft_id: str,
        owner_id: str,
    ) -> TestPackDraftView | None:
        with self.database.session() as session:
            record = session.get(AuthoringTestPackDraftRecord, draft_id)
            if record is None or record.owner_id != owner_id:
                return None
            if record.status == "approved":
                raise AuthoringConflict("An approved Test Pack Draft cannot be rejected.")
            if record.status != "rejected":
                now = datetime.now(UTC)
                record.status = "rejected"
                record.rejected_at = now
                record.updated_at = now
                session.commit()
                session.refresh(record)
            return self._pack_view(session, record)

    def approve_test_pack_draft(
        self,
        draft_id: str,
        owner_id: str,
    ) -> tuple[TestPackDraftView, TestPackView] | None:
        with self.database.session() as session:
            record = session.get(AuthoringTestPackDraftRecord, draft_id)
            if record is None or record.owner_id != owner_id:
                return None
            if record.status != "draft":
                raise AuthoringConflict("Only an active Test Pack Draft can be approved.")
            items = self._pack_item_records(session, record.id)
            scenario_ids = [
                self._resolve_approved_scenario_id(session, owner_id, item)
                for item in items
            ]
            if len(scenario_ids) != len(set(scenario_ids)):
                raise AuthoringConflict(
                    "Test Pack Draft references resolve to the same formal Scenario more than once."
                )
            pack_id = str(uuid4())
            session.add(
                TestPackRecord(
                    id=pack_id,
                    owner_id=owner_id,
                    name=record.name,
                    description=record.description,
                    version=1,
                )
            )
            session.flush()
            for position, (item, scenario_id) in enumerate(zip(items, scenario_ids, strict=True)):
                session.add(
                    TestPackItemRecord(
                        pack_id=pack_id,
                        scenario_id=scenario_id,
                        position=position,
                        enabled=item.enabled,
                    )
                )
            now = datetime.now(UTC)
            record.status = "approved"
            record.approved_test_pack_id = pack_id
            record.approved_at = now
            record.updated_at = now
            session.commit()
            session.refresh(record)
            draft = self._pack_view(session, record)
        pack = self.workspace_repository.get_pack(pack_id, owner_id)
        if pack is None:
            raise RuntimeError("Approved Test Pack could not be loaded.")
        return draft, pack

    def delete_test_pack_draft(self, draft_id: str, owner_id: str) -> bool:
        with self.database.session() as session:
            record = session.get(AuthoringTestPackDraftRecord, draft_id)
            if record is None or record.owner_id != owner_id:
                return False
            if record.status == "approved":
                raise AuthoringConflict("Approved Test Pack Draft provenance cannot be deleted.")
            session.execute(
                delete(AuthoringTestPackDraftItemRecord).where(
                    AuthoringTestPackDraftItemRecord.pack_draft_id == draft_id
                )
            )
            session.delete(record)
            session.commit()
            return True

    @staticmethod
    def _scenario_columns(
        payload: ScenarioDraftCreate | ScenarioDraftUpdate,
    ) -> dict[str, object]:
        return {
            "name": payload.name,
            "category": payload.category.value,
            "description": payload.description,
            "language": payload.language.value,
            "messages_json": json.dumps(payload.messages, ensure_ascii=False),
            "expected_behavior": payload.expected_behavior,
            "forbidden_phrases_json": json.dumps(
                payload.forbidden_phrases, ensure_ascii=False
            ),
            "required_phrases_json": json.dumps(
                payload.required_phrases, ensure_ascii=False
            ),
            "severity": payload.severity.value,
            "max_turns": payload.max_turns,
            "recommended_tester_mode": payload.recommended_tester_mode,
            "recommended_judge_mode": payload.recommended_judge_mode.value,
            "provenance_json": payload.provenance.model_dump_json(),
            "review_notes": payload.review_notes,
        }

    @staticmethod
    def _scenario_view(record: AuthoringScenarioDraftRecord) -> ScenarioDraftView:
        return ScenarioDraftView(
            id=record.id,
            owner_id=record.owner_id,
            status=cast(DraftStatus, record.status),
            revision=record.revision,
            name=record.name,
            category=record.category,
            description=record.description,
            language=record.language,
            messages=_string_list(record.messages_json),
            expected_behavior=record.expected_behavior,
            forbidden_phrases=_string_list(record.forbidden_phrases_json),
            required_phrases=_string_list(record.required_phrases_json),
            severity=record.severity,
            max_turns=record.max_turns,
            recommended_tester_mode=record.recommended_tester_mode,
            recommended_judge_mode=record.recommended_judge_mode,
            provenance=json.loads(record.provenance_json),
            review_notes=record.review_notes,
            approved_scenario_id=record.approved_scenario_id,
            created_at=record.created_at,
            updated_at=record.updated_at,
            approved_at=record.approved_at,
            rejected_at=record.rejected_at,
        )

    @staticmethod
    def _pack_view(
        session: Session,
        record: AuthoringTestPackDraftRecord,
    ) -> TestPackDraftView:
        items = [
            PackDraftItemInput(
                scenario_id=item.scenario_id,
                scenario_draft_id=item.scenario_draft_id,
                enabled=item.enabled,
            )
            for item in AuthoringRepository._pack_item_records(session, record.id)
        ]
        return TestPackDraftView(
            id=record.id,
            owner_id=record.owner_id,
            status=cast(DraftStatus, record.status),
            revision=record.revision,
            name=record.name,
            description=record.description,
            items=items,
            provenance=json.loads(record.provenance_json),
            review_notes=record.review_notes,
            approved_test_pack_id=record.approved_test_pack_id,
            created_at=record.created_at,
            updated_at=record.updated_at,
            approved_at=record.approved_at,
            rejected_at=record.rejected_at,
        )

    @staticmethod
    def _pack_item_records(
        session: Session,
        draft_id: str,
    ) -> list[AuthoringTestPackDraftItemRecord]:
        return list(
            session.scalars(
                select(AuthoringTestPackDraftItemRecord)
                .where(AuthoringTestPackDraftItemRecord.pack_draft_id == draft_id)
                .order_by(AuthoringTestPackDraftItemRecord.position)
            )
        )

    @staticmethod
    def _replace_pack_items(
        session: Session,
        draft_id: str,
        items: list[PackDraftItemInput],
    ) -> None:
        session.execute(
            delete(AuthoringTestPackDraftItemRecord).where(
                AuthoringTestPackDraftItemRecord.pack_draft_id == draft_id
            )
        )
        for position, item in enumerate(items):
            session.add(
                AuthoringTestPackDraftItemRecord(
                    pack_draft_id=draft_id,
                    scenario_id=item.scenario_id,
                    scenario_draft_id=item.scenario_draft_id,
                    position=position,
                    enabled=item.enabled,
                )
            )

    @staticmethod
    def _validate_pack_references(
        session: Session,
        owner_id: str,
        items: list[PackDraftItemInput],
    ) -> None:
        for item in items:
            if item.scenario_id is not None:
                scenario = session.get(CustomScenarioRecord, item.scenario_id)
                if scenario is None or scenario.owner_id != owner_id:
                    raise AuthoringConflict("Referenced Scenario was not found.")
            elif item.scenario_draft_id is not None:
                draft = session.get(
                    AuthoringScenarioDraftRecord,
                    item.scenario_draft_id,
                )
                if draft is None or draft.owner_id != owner_id:
                    raise AuthoringConflict("Referenced Scenario Draft was not found.")

    @staticmethod
    def _resolve_approved_scenario_id(
        session: Session,
        owner_id: str,
        item: AuthoringTestPackDraftItemRecord,
    ) -> str:
        if item.scenario_id is not None:
            scenario = session.get(CustomScenarioRecord, item.scenario_id)
            if scenario is None or scenario.owner_id != owner_id:
                raise AuthoringConflict("Referenced Scenario is no longer available.")
            return scenario.id
        if item.scenario_draft_id is None:
            raise AuthoringConflict("Test Pack Draft item has no Scenario reference.")
        draft = session.get(AuthoringScenarioDraftRecord, item.scenario_draft_id)
        if (
            draft is None
            or draft.owner_id != owner_id
            or draft.status != "approved"
            or draft.approved_scenario_id is None
        ):
            raise AuthoringConflict(
                "Every referenced Scenario Draft must be approved before the Test Pack Draft."
            )
        scenario = session.get(CustomScenarioRecord, draft.approved_scenario_id)
        if scenario is None or scenario.owner_id != owner_id:
            raise AuthoringConflict("Approved Scenario is no longer available.")
        return scenario.id


def _string_list(raw: str) -> list[str]:
    value = json.loads(raw)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError("Expected a JSON string list.")
    return value
