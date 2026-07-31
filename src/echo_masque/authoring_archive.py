"""Secret-free export, import, cleanup, and ownership migration for authoring drafts."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import delete, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from echo_masque.authoring import (
    AuthoringArchive,
    AuthoringImportResult,
    ScenarioDraftView,
    TestPackDraftView,
)
from echo_masque.persistence.authoring_models import (
    AuthoringScenarioDraftRecord,
    AuthoringTestPackDraftItemRecord,
    AuthoringTestPackDraftRecord,
)
from echo_masque.persistence.authoring_repository import (
    AuthoringConflict,
    AuthoringRepository,
)
from echo_masque.persistence.database import Database
from echo_masque.persistence.models import (
    CustomScenarioRecord,
    TestPackRecord,
)


class AuthoringArchiveService:
    def __init__(self, database: Database, repository: AuthoringRepository) -> None:
        self.database = database
        self.repository = repository

    def export(self, owner_id: str) -> AuthoringArchive:
        return AuthoringArchive(
            exported_at=datetime.now(UTC),
            owner_id=owner_id,
            scenario_drafts=self.repository.list_scenario_drafts(owner_id),
            test_pack_drafts=self.repository.list_test_pack_drafts(owner_id),
        )

    def import_archive(
        self,
        owner_id: str,
        archive: AuthoringArchive,
        mode: str,
    ) -> AuthoringImportResult:
        if mode not in {"merge", "replace"}:
            raise ValueError("Authoring import mode must be merge or replace.")
        imported = {
            "scenario_drafts": 0,
            "test_pack_drafts": 0,
            "test_pack_draft_items": 0,
        }
        skipped = {
            "scenario_drafts": 0,
            "test_pack_drafts": 0,
        }
        with self.database.session() as session:
            if mode == "replace":
                self._delete_owner_in_session(session, owner_id)

            for draft in archive.scenario_drafts:
                existing = session.get(AuthoringScenarioDraftRecord, draft.id)
                if existing is not None:
                    if existing.owner_id != owner_id:
                        raise AuthoringConflict(
                            "Scenario Draft import conflicts with another user's resource."
                        )
                    skipped["scenario_drafts"] += 1
                    continue
                self._validate_scenario_approval(session, owner_id, draft)
                session.add(self._scenario_record(owner_id, draft))
                imported["scenario_drafts"] += 1
            session.flush()

            for draft in archive.test_pack_drafts:
                existing = session.get(AuthoringTestPackDraftRecord, draft.id)
                if existing is not None:
                    if existing.owner_id != owner_id:
                        raise AuthoringConflict(
                            "Test Pack Draft import conflicts with another user's resource."
                        )
                    skipped["test_pack_drafts"] += 1
                    continue
                self._validate_pack_approval(session, owner_id, draft)
                session.add(self._pack_record(owner_id, draft))
                session.flush()
                for position, item in enumerate(draft.items):
                    self._validate_pack_item(session, owner_id, item.scenario_id, item.scenario_draft_id)
                    session.add(
                        AuthoringTestPackDraftItemRecord(
                            pack_draft_id=draft.id,
                            scenario_id=item.scenario_id,
                            scenario_draft_id=item.scenario_draft_id,
                            position=position,
                            enabled=item.enabled,
                        )
                    )
                    imported["test_pack_draft_items"] += 1
                imported["test_pack_drafts"] += 1
            session.commit()
        return AuthoringImportResult(imported=imported, skipped=skipped)

    def delete_owner(self, owner_id: str) -> dict[str, int]:
        with self.database.session() as session:
            counts = self._delete_owner_in_session(session, owner_id)
            session.commit()
            return counts

    def claim_owner(self, source_owner_id: str, target_owner_id: str) -> dict[str, int]:
        with self.database.session() as session:
            scenario_result = session.execute(
                update(AuthoringScenarioDraftRecord)
                .where(AuthoringScenarioDraftRecord.owner_id == source_owner_id)
                .values(owner_id=target_owner_id)
            )
            pack_result = session.execute(
                update(AuthoringTestPackDraftRecord)
                .where(AuthoringTestPackDraftRecord.owner_id == source_owner_id)
                .values(owner_id=target_owner_id)
            )
            session.commit()
            return {
                "authoring_scenario_drafts": self._rowcount(scenario_result),
                "authoring_test_pack_drafts": self._rowcount(pack_result),
            }

    @staticmethod
    def _scenario_record(
        owner_id: str,
        draft: ScenarioDraftView,
    ) -> AuthoringScenarioDraftRecord:
        return AuthoringScenarioDraftRecord(
            id=draft.id,
            owner_id=owner_id,
            status=draft.status,
            revision=draft.revision,
            name=draft.name,
            category=draft.category,
            description=draft.description,
            language=draft.language,
            messages_json=json.dumps(draft.messages, ensure_ascii=False),
            expected_behavior=draft.expected_behavior,
            forbidden_phrases_json=json.dumps(
                draft.forbidden_phrases,
                ensure_ascii=False,
            ),
            required_phrases_json=json.dumps(
                draft.required_phrases,
                ensure_ascii=False,
            ),
            severity=draft.severity,
            max_turns=draft.max_turns,
            recommended_tester_mode=draft.recommended_tester_mode,
            recommended_judge_mode=draft.recommended_judge_mode,
            provenance_json=draft.provenance.model_dump_json(),
            review_notes=draft.review_notes,
            approved_scenario_id=draft.approved_scenario_id,
            created_at=draft.created_at,
            updated_at=draft.updated_at,
            approved_at=draft.approved_at,
            rejected_at=draft.rejected_at,
        )

    @staticmethod
    def _pack_record(
        owner_id: str,
        draft: TestPackDraftView,
    ) -> AuthoringTestPackDraftRecord:
        return AuthoringTestPackDraftRecord(
            id=draft.id,
            owner_id=owner_id,
            status=draft.status,
            revision=draft.revision,
            name=draft.name,
            description=draft.description,
            provenance_json=draft.provenance.model_dump_json(),
            review_notes=draft.review_notes,
            approved_test_pack_id=draft.approved_test_pack_id,
            created_at=draft.created_at,
            updated_at=draft.updated_at,
            approved_at=draft.approved_at,
            rejected_at=draft.rejected_at,
        )

    @staticmethod
    def _validate_scenario_approval(
        session: Session,
        owner_id: str,
        draft: ScenarioDraftView,
    ) -> None:
        if draft.status == "approved":
            if draft.approved_scenario_id is None:
                raise AuthoringConflict(
                    "Approved Scenario Draft is missing its formal Scenario reference."
                )
            scenario = session.get(CustomScenarioRecord, draft.approved_scenario_id)
            if scenario is None or scenario.owner_id != owner_id:
                raise AuthoringConflict(
                    "Import the approved formal Scenario before its Scenario Draft provenance."
                )
        elif draft.approved_scenario_id is not None:
            raise AuthoringConflict(
                "Only an approved Scenario Draft may reference a formal Scenario."
            )

    @staticmethod
    def _validate_pack_approval(
        session: Session,
        owner_id: str,
        draft: TestPackDraftView,
    ) -> None:
        if draft.status == "approved":
            if draft.approved_test_pack_id is None:
                raise AuthoringConflict(
                    "Approved Test Pack Draft is missing its formal Test Pack reference."
                )
            pack = session.get(TestPackRecord, draft.approved_test_pack_id)
            if pack is None or pack.owner_id != owner_id:
                raise AuthoringConflict(
                    "Import the approved formal Test Pack before its Draft provenance."
                )
        elif draft.approved_test_pack_id is not None:
            raise AuthoringConflict(
                "Only an approved Test Pack Draft may reference a formal Test Pack."
            )

    @staticmethod
    def _validate_pack_item(
        session: Session,
        owner_id: str,
        scenario_id: str | None,
        scenario_draft_id: str | None,
    ) -> None:
        if scenario_id is not None:
            scenario = session.get(CustomScenarioRecord, scenario_id)
            if scenario is None or scenario.owner_id != owner_id:
                raise AuthoringConflict(
                    "Authoring archive references a Scenario outside this workspace."
                )
            return
        if scenario_draft_id is not None:
            draft = session.get(AuthoringScenarioDraftRecord, scenario_draft_id)
            if draft is None or draft.owner_id != owner_id:
                raise AuthoringConflict(
                    "Authoring archive references a Scenario Draft outside this workspace."
                )
            return
        raise AuthoringConflict("Authoring archive contains an empty Test Pack Draft item.")

    @staticmethod
    def _delete_owner_in_session(session: Session, owner_id: str) -> dict[str, int]:
        pack_ids = list(
            session.scalars(
                select(AuthoringTestPackDraftRecord.id).where(
                    AuthoringTestPackDraftRecord.owner_id == owner_id
                )
            )
        )
        item_count = 0
        if pack_ids:
            item_count = AuthoringArchiveService._rowcount(
                session.execute(
                    delete(AuthoringTestPackDraftItemRecord).where(
                        AuthoringTestPackDraftItemRecord.pack_draft_id.in_(pack_ids)
                    )
                )
            )
        pack_count = AuthoringArchiveService._rowcount(
            session.execute(
                delete(AuthoringTestPackDraftRecord).where(
                    AuthoringTestPackDraftRecord.owner_id == owner_id
                )
            )
        )
        scenario_count = AuthoringArchiveService._rowcount(
            session.execute(
                delete(AuthoringScenarioDraftRecord).where(
                    AuthoringScenarioDraftRecord.owner_id == owner_id
                )
            )
        )
        return {
            "authoring_scenario_drafts": scenario_count,
            "authoring_test_pack_drafts": pack_count,
            "authoring_test_pack_draft_items": item_count,
        }

    @staticmethod
    def _rowcount(result: CursorResult[tuple[object, ...]]) -> int:
        return max(0, int(result.rowcount or 0))
