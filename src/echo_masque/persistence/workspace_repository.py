"""Persistence operations for custom scenarios, packs, snapshots, and workspace data."""

import json
import math
from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

from sqlalchemy import delete, func, select

from echo_masque.domain import TrialSuiteResult
from echo_masque.persistence.database import Database
from echo_masque.persistence.models import (
    AdminRuntimeRecord,
    CharacterCardRecord,
    CharacterTrialRecord,
    CustomScenarioRecord,
    EvidenceRecord,
    PersistenceProbeRecord,
    RunSnapshotRecord,
    TargetRecord,
    TestPackItemRecord,
    TestPackRecord,
    TrialEventRecord,
    TrialRunRecord,
    TurnRecord,
)
from echo_masque.persistence.trial_request import decode_trial_metadata
from echo_masque.security import redact
from echo_masque.workspace import (
    ExperimentHistoryItem,
    ExperimentHistoryPage,
    PackItemInput,
    PackScenarioView,
    PersistenceProbeView,
    RunSnapshotView,
    ScenarioCreate,
    ScenarioUpdate,
    ScenarioView,
    TestPackCreate,
    TestPackUpdate,
    TestPackView,
    WorkspaceArchive,
    WorkspaceImportResult,
)


class WorkspaceRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    # Scenarios
    def list_scenarios(self, owner_id: str) -> list[ScenarioView]:
        with self.database.session() as session:
            records = session.scalars(
                select(CustomScenarioRecord)
                .where(CustomScenarioRecord.owner_id == owner_id)
                .order_by(CustomScenarioRecord.updated_at.desc())
            )
            return [self._scenario_view(record) for record in records]

    def get_scenario(self, scenario_id: str, owner_id: str) -> ScenarioView | None:
        with self.database.session() as session:
            record = session.get(CustomScenarioRecord, scenario_id)
            if record is None or record.owner_id != owner_id:
                return None
            return self._scenario_view(record)

    def create_scenario(self, owner_id: str, payload: ScenarioCreate) -> ScenarioView:
        record = CustomScenarioRecord(
            id=str(uuid4()),
            owner_id=owner_id,
            **self._scenario_columns(payload),
        )
        with self.database.session() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
            return self._scenario_view(record)

    def update_scenario(
        self, scenario_id: str, owner_id: str, payload: ScenarioUpdate
    ) -> ScenarioView | None:
        with self.database.session() as session:
            record = session.get(CustomScenarioRecord, scenario_id)
            if record is None or record.owner_id != owner_id:
                return None
            for key, value in self._scenario_columns(payload).items():
                setattr(record, key, value)
            record.updated_at = datetime.now(UTC)
            session.commit()
            session.refresh(record)
            return self._scenario_view(record)

    def duplicate_scenario(self, scenario_id: str, owner_id: str) -> ScenarioView | None:
        source = self.get_scenario(scenario_id, owner_id)
        if source is None:
            return None
        payload = ScenarioCreate(
            **source.model_dump(
                exclude={"id", "owner_id", "created_at", "updated_at"}
            )
        )
        payload.name = f"{payload.name} Copy"
        return self.create_scenario(owner_id, payload)

    def delete_scenario(self, scenario_id: str, owner_id: str) -> bool:
        with self.database.session() as session:
            record = session.get(CustomScenarioRecord, scenario_id)
            if record is None or record.owner_id != owner_id:
                return False
            session.execute(
                delete(TestPackItemRecord).where(
                    TestPackItemRecord.scenario_id == scenario_id
                )
            )
            session.delete(record)
            session.commit()
            return True

    # Test packs
    def list_packs(self, owner_id: str) -> list[TestPackView]:
        with self.database.session() as session:
            records = session.scalars(
                select(TestPackRecord)
                .where(TestPackRecord.owner_id == owner_id)
                .order_by(TestPackRecord.updated_at.desc())
            )
            return [self._pack_view(session, record) for record in records]

    def get_pack(self, pack_id: str, owner_id: str) -> TestPackView | None:
        with self.database.session() as session:
            record = session.get(TestPackRecord, pack_id)
            if record is None or record.owner_id != owner_id:
                return None
            return self._pack_view(session, record)

    def create_pack(self, owner_id: str, payload: TestPackCreate) -> TestPackView:
        with self.database.session() as session:
            self._validate_pack_items(session, owner_id, payload.items)
            record = TestPackRecord(
                id=str(uuid4()),
                owner_id=owner_id,
                name=payload.name,
                description=payload.description,
                version=1,
            )
            session.add(record)
            session.flush()
            self._replace_pack_items(session, record.id, payload.items)
            session.commit()
            session.refresh(record)
            return self._pack_view(session, record)

    def update_pack(
        self, pack_id: str, owner_id: str, payload: TestPackUpdate
    ) -> TestPackView | None:
        with self.database.session() as session:
            record = session.get(TestPackRecord, pack_id)
            if record is None or record.owner_id != owner_id:
                return None
            self._validate_pack_items(session, owner_id, payload.items)
            record.name = payload.name
            record.description = payload.description
            record.version += 1
            record.updated_at = datetime.now(UTC)
            self._replace_pack_items(session, pack_id, payload.items)
            session.commit()
            session.refresh(record)
            return self._pack_view(session, record)

    def duplicate_pack(self, pack_id: str, owner_id: str) -> TestPackView | None:
        source = self.get_pack(pack_id, owner_id)
        if source is None:
            return None
        payload = TestPackCreate(
            name=f"{source.name} Copy",
            description=source.description,
            items=[
                PackItemInput(
                    scenario_id=item.scenario.id,
                    enabled=item.enabled,
                )
                for item in sorted(source.items, key=lambda value: value.position)
            ],
        )
        return self.create_pack(owner_id, payload)

    def delete_pack(self, pack_id: str, owner_id: str) -> bool:
        with self.database.session() as session:
            record = session.get(TestPackRecord, pack_id)
            if record is None or record.owner_id != owner_id:
                return False
            session.execute(
                delete(TestPackItemRecord).where(TestPackItemRecord.pack_id == pack_id)
            )
            session.delete(record)
            session.commit()
            return True

    # Run snapshots and experiment history
    def save_run_snapshot(
        self,
        *,
        run_id: str,
        owner_id: str,
        character_card_id: str | None,
        test_pack_id: str | None,
        character: dict[str, object],
        target: dict[str, object],
        test_pack: dict[str, object],
        scenarios: list[dict[str, object]],
        rerun_of: str | None = None,
    ) -> RunSnapshotView:
        record = RunSnapshotRecord(
            run_id=run_id,
            owner_id=owner_id,
            character_card_id=character_card_id,
            test_pack_id=test_pack_id,
            character_json=json.dumps(redact(character), ensure_ascii=False),
            target_json=json.dumps(redact(target), ensure_ascii=False),
            pack_json=json.dumps(redact(test_pack), ensure_ascii=False),
            scenarios_json=json.dumps(redact(scenarios), ensure_ascii=False),
            rerun_of=rerun_of,
            is_baseline=False,
        )
        with self.database.session() as session:
            existing = session.get(RunSnapshotRecord, run_id)
            if existing is not None:
                session.delete(existing)
                session.flush()
            session.add(record)
            session.commit()
            session.refresh(record)
            return self._snapshot_view(record)

    def get_run_snapshot(self, run_id: str, owner_id: str | None = None) -> RunSnapshotView | None:
        with self.database.session() as session:
            record = session.get(RunSnapshotRecord, run_id)
            if record is None or (owner_id is not None and record.owner_id != owner_id):
                return None
            return self._snapshot_view(record)

    def set_baseline(self, run_id: str, owner_id: str, value: bool) -> RunSnapshotView | None:
        with self.database.session() as session:
            record = session.get(RunSnapshotRecord, run_id)
            if record is None or record.owner_id != owner_id:
                return None
            if value:
                session.execute(
                    RunSnapshotRecord.__table__.update()
                    .where(
                        RunSnapshotRecord.owner_id == owner_id,
                        RunSnapshotRecord.character_card_id == record.character_card_id,
                        RunSnapshotRecord.test_pack_id == record.test_pack_id,
                    )
                    .values(is_baseline=False)
                )
            record.is_baseline = value
            session.commit()
            session.refresh(record)
            return self._snapshot_view(record)

    def history(
        self,
        owner_id: str,
        *,
        page: int = 1,
        page_size: int = 20,
        character_card_id: str | None = None,
        test_pack_id: str | None = None,
        language: str | None = None,
        tester_mode: str | None = None,
        judge_mode: str | None = None,
        status: str | None = None,
    ) -> ExperimentHistoryPage:
        with self.database.session() as session:
            snapshots = list(
                session.scalars(
                    select(RunSnapshotRecord)
                    .where(RunSnapshotRecord.owner_id == owner_id)
                    .order_by(RunSnapshotRecord.created_at.desc())
                )
            )
            items: list[ExperimentHistoryItem] = []
            for snapshot in snapshots:
                run = session.get(TrialRunRecord, snapshot.run_id)
                if run is None:
                    continue
                metadata = decode_trial_metadata(run.suite_json)
                if character_card_id and snapshot.character_card_id != character_card_id:
                    continue
                if test_pack_id and snapshot.test_pack_id != test_pack_id:
                    continue
                if language and metadata.test_language.value != language:
                    continue
                if tester_mode and metadata.tester_mode != tester_mode:
                    continue
                if judge_mode and metadata.judge_mode.value != judge_mode:
                    continue
                if status and run.status != status:
                    continue
                result = (
                    TrialSuiteResult.model_validate_json(run.result_json)
                    if run.result_json
                    else None
                )
                character = _dict(snapshot.character_json)
                pack = _dict(snapshot.pack_json)
                items.append(
                    ExperimentHistoryItem(
                        run_id=run.id,
                        status=run.status,
                        character_card_id=snapshot.character_card_id,
                        character_name=str(character.get("display_name", "Unknown character")),
                        test_pack_id=snapshot.test_pack_id,
                        test_pack_name=(str(pack.get("name")) if pack.get("name") else None),
                        test_language=metadata.test_language,
                        tester_mode=metadata.tester_mode,
                        judge_mode=metadata.judge_mode,
                        score=result.average_score if result else None,
                        passed=result.passed if result else None,
                        review_required=result.review_required if result else False,
                        is_baseline=snapshot.is_baseline,
                        rerun_of=snapshot.rerun_of,
                        created_at=run.created_at,
                        updated_at=run.updated_at,
                    )
                )
            total = len(items)
            pages = max(1, math.ceil(total / page_size))
            safe_page = min(max(1, page), pages)
            start = (safe_page - 1) * page_size
            return ExperimentHistoryPage(
                items=items[start : start + page_size],
                page=safe_page,
                page_size=page_size,
                total=total,
                pages=pages,
            )

    def delete_run(self, run_id: str, owner_id: str) -> bool:
        with self.database.session() as session:
            snapshot = session.get(RunSnapshotRecord, run_id)
            if snapshot is None or snapshot.owner_id != owner_id:
                return False
            for model in (EvidenceRecord, TrialEventRecord, TurnRecord, CharacterTrialRecord):
                session.execute(delete(model).where(model.run_id == run_id))
            session.delete(snapshot)
            run = session.get(TrialRunRecord, run_id)
            if run is not None:
                session.delete(run)
            session.commit()
            return True

    # Persistence probes and diagnostics data
    def create_probe(self, owner_id: str, marker: str) -> PersistenceProbeView:
        record = PersistenceProbeRecord(
            id=str(uuid4()), owner_id=owner_id, marker=marker
        )
        with self.database.session() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
            return PersistenceProbeView(
                id=record.id, marker=record.marker, created_at=record.created_at
            )

    def get_probe(self, probe_id: str, owner_id: str) -> PersistenceProbeView | None:
        with self.database.session() as session:
            record = session.get(PersistenceProbeRecord, probe_id)
            if record is None or record.owner_id != owner_id:
                return None
            return PersistenceProbeView(
                id=record.id, marker=record.marker, created_at=record.created_at
            )

    def delete_probe(self, probe_id: str, owner_id: str) -> bool:
        with self.database.session() as session:
            record = session.get(PersistenceProbeRecord, probe_id)
            if record is None or record.owner_id != owner_id:
                return False
            session.delete(record)
            session.commit()
            return True

    def counts(self, owner_id: str) -> dict[str, int]:
        with self.database.session() as session:
            return {
                "characters": int(
                    session.scalar(
                        select(func.count()).select_from(CharacterCardRecord).where(
                            CharacterCardRecord.owner_id == owner_id
                        )
                    )
                    or 0
                ),
                "scenarios": int(
                    session.scalar(
                        select(func.count()).select_from(CustomScenarioRecord).where(
                            CustomScenarioRecord.owner_id == owner_id
                        )
                    )
                    or 0
                ),
                "packs": int(
                    session.scalar(
                        select(func.count()).select_from(TestPackRecord).where(
                            TestPackRecord.owner_id == owner_id
                        )
                    )
                    or 0
                ),
                "runs": int(
                    session.scalar(
                        select(func.count()).select_from(RunSnapshotRecord).where(
                            RunSnapshotRecord.owner_id == owner_id
                        )
                    )
                    or 0
                ),
            }

    def last_write_at(self, owner_id: str) -> datetime | None:
        with self.database.session() as session:
            values = [
                session.scalar(
                    select(func.max(CharacterCardRecord.created_at)).where(
                        CharacterCardRecord.owner_id == owner_id
                    )
                ),
                session.scalar(
                    select(func.max(CustomScenarioRecord.updated_at)).where(
                        CustomScenarioRecord.owner_id == owner_id
                    )
                ),
                session.scalar(
                    select(func.max(TestPackRecord.updated_at)).where(
                        TestPackRecord.owner_id == owner_id
                    )
                ),
                session.scalar(
                    select(func.max(RunSnapshotRecord.created_at)).where(
                        RunSnapshotRecord.owner_id == owner_id
                    )
                ),
            ]
            present = [value for value in values if value is not None]
            return max(present) if present else None

    # Workspace backup and restore
    def export_workspace(self, owner_id: str) -> WorkspaceArchive:
        with self.database.session() as session:
            cards = list(
                session.scalars(
                    select(CharacterCardRecord).where(CharacterCardRecord.owner_id == owner_id)
                )
            )
            target_ids = {card.target_id for card in cards}
            targets = [
                record
                for record in session.scalars(select(TargetRecord))
                if record.id in target_ids and not record.id.startswith("demo-")
            ]
            scenarios = list(
                session.scalars(
                    select(CustomScenarioRecord).where(
                        CustomScenarioRecord.owner_id == owner_id
                    )
                )
            )
            packs = list(
                session.scalars(
                    select(TestPackRecord).where(TestPackRecord.owner_id == owner_id)
                )
            )
            pack_ids = {record.id for record in packs}
            pack_items = [
                record
                for record in session.scalars(select(TestPackItemRecord))
                if record.pack_id in pack_ids
            ]
            snapshots = list(
                session.scalars(
                    select(RunSnapshotRecord).where(RunSnapshotRecord.owner_id == owner_id)
                )
            )
            run_ids = {record.run_id for record in snapshots}
            runs = [record for record in session.scalars(select(TrialRunRecord)) if record.id in run_ids]
            links = [
                record
                for record in session.scalars(select(CharacterTrialRecord))
                if record.run_id in run_ids
            ]
            turns = [record for record in session.scalars(select(TurnRecord)) if record.run_id in run_ids]
            events = [
                record for record in session.scalars(select(TrialEventRecord)) if record.run_id in run_ids
            ]
            evidence = [
                record for record in session.scalars(select(EvidenceRecord)) if record.run_id in run_ids
            ]
            runtime = session.get(AdminRuntimeRecord, "default")
            pack_payload = [
                {
                    **_record(record),
                    "items": [
                        _record(item) for item in pack_items if item.pack_id == record.id
                    ],
                }
                for record in packs
            ]
            return WorkspaceArchive(
                exported_at=datetime.now(UTC),
                owner_id=owner_id,
                targets=[_record(record) for record in targets],
                character_cards=[_record(record) for record in cards],
                scenarios=[_record(record) for record in scenarios],
                test_packs=pack_payload,
                trial_runs=[_record(record) for record in runs],
                character_trials=[_record(record) for record in links],
                run_snapshots=[_record(record) for record in snapshots],
                turns=[_record(record) for record in turns],
                events=[_record(record) for record in events],
                evidence=[_record(record) for record in evidence],
                admin_runtime=(_record(runtime) if runtime is not None else None),
            )

    def import_workspace(
        self, owner_id: str, archive: WorkspaceArchive, mode: str
    ) -> WorkspaceImportResult:
        imported: dict[str, int] = {}
        skipped: dict[str, int] = {}
        with self.database.session() as session:
            if mode == "replace":
                self._delete_owner_workspace(session, owner_id)
            self._import_records(session, TargetRecord, archive.targets, imported, skipped, "targets")
            cards = [dict(item, owner_id=owner_id) for item in archive.character_cards]
            self._import_records(
                session, CharacterCardRecord, cards, imported, skipped, "character_cards"
            )
            scenarios = [dict(item, owner_id=owner_id) for item in archive.scenarios]
            self._import_records(
                session, CustomScenarioRecord, scenarios, imported, skipped, "scenarios"
            )
            pack_items: list[dict[str, object]] = []
            pack_records: list[dict[str, object]] = []
            for raw in archive.test_packs:
                pack = dict(raw)
                items = pack.pop("items", [])
                pack["owner_id"] = owner_id
                pack_records.append(pack)
                if isinstance(items, list):
                    pack_items.extend(cast(list[dict[str, object]], items))
            self._import_records(
                session, TestPackRecord, pack_records, imported, skipped, "test_packs"
            )
            self._import_records(
                session, TestPackItemRecord, pack_items, imported, skipped, "test_pack_items"
            )
            self._import_records(
                session, TrialRunRecord, archive.trial_runs, imported, skipped, "trial_runs"
            )
            self._import_records(
                session,
                CharacterTrialRecord,
                archive.character_trials,
                imported,
                skipped,
                "character_trials",
            )
            snapshots = [dict(item, owner_id=owner_id) for item in archive.run_snapshots]
            self._import_records(
                session, RunSnapshotRecord, snapshots, imported, skipped, "run_snapshots"
            )
            self._import_records(session, TurnRecord, archive.turns, imported, skipped, "turns")
            self._import_records(
                session, TrialEventRecord, archive.events, imported, skipped, "events"
            )
            self._import_records(
                session, EvidenceRecord, archive.evidence, imported, skipped, "evidence"
            )
            if archive.admin_runtime is not None and session.get(AdminRuntimeRecord, "default") is None:
                session.add(AdminRuntimeRecord(**_decode_dates(archive.admin_runtime)))
                imported["admin_runtime"] = 1
            session.commit()
        return WorkspaceImportResult(imported=imported, skipped=skipped)

    @staticmethod
    def _scenario_columns(payload: ScenarioCreate | ScenarioUpdate) -> dict[str, object]:
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
        }

    @staticmethod
    def _scenario_view(record: CustomScenarioRecord) -> ScenarioView:
        return ScenarioView(
            id=record.id,
            owner_id=record.owner_id,
            name=record.name,
            category=record.category,
            description=record.description,
            language=record.language,
            messages=_list(record.messages_json),
            expected_behavior=record.expected_behavior,
            forbidden_phrases=_list(record.forbidden_phrases_json),
            required_phrases=_list(record.required_phrases_json),
            severity=record.severity,
            max_turns=record.max_turns,
            recommended_tester_mode=record.recommended_tester_mode,
            recommended_judge_mode=record.recommended_judge_mode,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    def _pack_view(self, session: Any, record: TestPackRecord) -> TestPackView:
        links = list(
            session.scalars(
                select(TestPackItemRecord)
                .where(TestPackItemRecord.pack_id == record.id)
                .order_by(TestPackItemRecord.position)
            )
        )
        items: list[PackScenarioView] = []
        for link in links:
            scenario = session.get(CustomScenarioRecord, link.scenario_id)
            if scenario is not None:
                items.append(
                    PackScenarioView(
                        scenario=self._scenario_view(scenario),
                        position=link.position,
                        enabled=link.enabled,
                    )
                )
        return TestPackView(
            id=record.id,
            owner_id=record.owner_id,
            name=record.name,
            description=record.description,
            version=record.version,
            items=items,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    @staticmethod
    def _snapshot_view(record: RunSnapshotRecord) -> RunSnapshotView:
        return RunSnapshotView(
            run_id=record.run_id,
            owner_id=record.owner_id,
            character_card_id=record.character_card_id,
            test_pack_id=record.test_pack_id,
            character=_dict(record.character_json),
            target=_dict(record.target_json),
            test_pack=_dict(record.pack_json),
            scenarios=cast(list[dict[str, object]], json.loads(record.scenarios_json)),
            rerun_of=record.rerun_of,
            is_baseline=record.is_baseline,
            created_at=record.created_at,
        )

    @staticmethod
    def _validate_pack_items(session: Any, owner_id: str, items: list[PackItemInput]) -> None:
        for item in items:
            scenario = session.get(CustomScenarioRecord, item.scenario_id)
            if scenario is None or scenario.owner_id != owner_id:
                raise ValueError(f"Scenario {item.scenario_id} is unavailable.")

    @staticmethod
    def _replace_pack_items(session: Any, pack_id: str, items: list[PackItemInput]) -> None:
        session.execute(delete(TestPackItemRecord).where(TestPackItemRecord.pack_id == pack_id))
        for position, item in enumerate(items):
            session.add(
                TestPackItemRecord(
                    pack_id=pack_id,
                    scenario_id=item.scenario_id,
                    position=position,
                    enabled=item.enabled,
                )
            )

    @staticmethod
    def _import_records(
        session: Any,
        model: type[Any],
        rows: list[dict[str, object]],
        imported: dict[str, int],
        skipped: dict[str, int],
        key: str,
    ) -> None:
        for raw in rows:
            values = _decode_dates(raw)
            identity = _identity_value(model, values)
            if identity is not None and session.get(model, identity) is not None:
                skipped[key] = skipped.get(key, 0) + 1
                continue
            values.pop("id", None) if model in {TurnRecord, TrialEventRecord, EvidenceRecord, TestPackItemRecord} else None
            session.add(model(**values))
            imported[key] = imported.get(key, 0) + 1

    @staticmethod
    def _delete_owner_workspace(session: Any, owner_id: str) -> None:
        snapshot_ids = list(
            session.scalars(
                select(RunSnapshotRecord.run_id).where(RunSnapshotRecord.owner_id == owner_id)
            )
        )
        for run_id in snapshot_ids:
            for model in (EvidenceRecord, TrialEventRecord, TurnRecord, CharacterTrialRecord):
                session.execute(delete(model).where(model.run_id == run_id))
            session.execute(delete(RunSnapshotRecord).where(RunSnapshotRecord.run_id == run_id))
            session.execute(delete(TrialRunRecord).where(TrialRunRecord.id == run_id))
        pack_ids = list(
            session.scalars(select(TestPackRecord.id).where(TestPackRecord.owner_id == owner_id))
        )
        if pack_ids:
            session.execute(delete(TestPackItemRecord).where(TestPackItemRecord.pack_id.in_(pack_ids)))
        session.execute(delete(TestPackRecord).where(TestPackRecord.owner_id == owner_id))
        session.execute(delete(CustomScenarioRecord).where(CustomScenarioRecord.owner_id == owner_id))
        session.execute(delete(CharacterCardRecord).where(CharacterCardRecord.owner_id == owner_id))
        session.execute(delete(PersistenceProbeRecord).where(PersistenceProbeRecord.owner_id == owner_id))


def _list(raw: str) -> list[str]:
    value = json.loads(raw)
    return [str(item) for item in value] if isinstance(value, list) else []


def _dict(raw: str) -> dict[str, object]:
    value = json.loads(raw)
    return cast(dict[str, object], value) if isinstance(value, dict) else {}


def _record(record: Any) -> dict[str, object]:
    result: dict[str, object] = {}
    for column in record.__table__.columns:
        value = getattr(record, column.name)
        result[column.name] = value.isoformat() if isinstance(value, datetime) else value
    return cast(dict[str, object], redact(result))


def _decode_dates(raw: dict[str, object]) -> dict[str, object]:
    result = dict(raw)
    for key in ("created_at", "updated_at", "exported_at"):
        value = result.get(key)
        if isinstance(value, str):
            try:
                result[key] = datetime.fromisoformat(value)
            except ValueError:
                result.pop(key, None)
    return result


def _identity_value(model: type[Any], values: dict[str, object]) -> object | None:
    primary = list(model.__table__.primary_key.columns)
    if len(primary) != 1:
        return None
    return values.get(primary[0].name)
