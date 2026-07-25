"""Persistence repository for targets and trial runs."""

import json
from uuid import uuid4

from sqlalchemy import delete, select

from echo_masque.domain import TrialStatus, TrialSuiteResult
from echo_masque.persistence.database import Database
from echo_masque.persistence.models import (
    EvidenceRecord,
    TargetRecord,
    TrialRunRecord,
    TurnRecord,
)
from echo_masque.security import redact


class Repository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def seed_demo_targets(self) -> None:
        with self.database.session() as session:
            for target_id, name, kind in (
                ("demo-stable", "Stable Ann", "stable"),
                ("demo-fragile", "Fragile Ann", "fragile"),
            ):
                if session.get(TargetRecord, target_id) is None:
                    session.add(
                        TargetRecord(
                            id=target_id,
                            name=name,
                            target_kind=kind,
                            config_json="{}",
                        )
                    )
            session.commit()

    def create_target(
        self, *, name: str, target_kind: str, config: dict[str, object]
    ) -> TargetRecord:
        record = TargetRecord(
            id=str(uuid4()),
            name=name,
            target_kind=target_kind,
            config_json=json.dumps(redact(config)),
        )
        with self.database.session() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
        return record

    def list_targets(self) -> list[TargetRecord]:
        with self.database.session() as session:
            return list(session.scalars(select(TargetRecord).order_by(TargetRecord.created_at)))

    def get_target(self, target_id: str) -> TargetRecord | None:
        with self.database.session() as session:
            return session.get(TargetRecord, target_id)

    def delete_target(self, target_id: str) -> bool:
        if target_id.startswith("demo-"):
            return False
        with self.database.session() as session:
            record = session.get(TargetRecord, target_id)
            if record is None:
                return False
            session.delete(record)
            session.commit()
            return True

    def create_run(self, *, target_id: str, suite: list[str]) -> TrialRunRecord:
        run = TrialRunRecord(
            id=str(uuid4()),
            target_id=target_id,
            status=TrialStatus.PENDING.value,
            suite_json=json.dumps(suite),
        )
        with self.database.session() as session:
            session.add(run)
            session.commit()
            session.refresh(run)
        return run

    def get_run(self, run_id: str) -> TrialRunRecord | None:
        with self.database.session() as session:
            return session.get(TrialRunRecord, run_id)

    def set_run_status(
        self,
        run_id: str,
        status: TrialStatus,
        *,
        error: str | None = None,
    ) -> None:
        with self.database.session() as session:
            run = session.get(TrialRunRecord, run_id)
            if run is None:
                raise KeyError(run_id)
            run.status = status.value
            run.error = error
            session.commit()

    def save_result(self, run_id: str, result: TrialSuiteResult) -> None:
        with self.database.session() as session:
            run = session.get(TrialRunRecord, run_id)
            if run is None:
                raise KeyError(run_id)
            session.execute(delete(TurnRecord).where(TurnRecord.run_id == run_id))
            session.execute(delete(EvidenceRecord).where(EvidenceRecord.run_id == run_id))
            for item in result.results:
                for turn in item.turns:
                    session.add(
                        TurnRecord(
                            run_id=run_id,
                            scenario_id=item.scenario.id,
                            turn_index=turn.index,
                            tester_message=turn.tester_message,
                            target_response=turn.target_response,
                            latency_ms=turn.latency_ms,
                            trace_json=json.dumps(turn.trace),
                        )
                    )
                for evidence in item.verdict.evidence:
                    session.add(
                        EvidenceRecord(
                            run_id=run_id,
                            scenario_id=item.scenario.id,
                            code=evidence.code,
                            message=evidence.message,
                            turn_index=evidence.turn_index,
                            excerpt=evidence.excerpt,
                            severity=evidence.severity.value,
                        )
                    )
            run.result_json = result.model_dump_json()
            run.status = TrialStatus.COMPLETED.value
            run.error = None
            session.commit()

    def result_for(self, run_id: str) -> TrialSuiteResult | None:
        run = self.get_run(run_id)
        if run is None or run.result_json is None:
            return None
        return TrialSuiteResult.model_validate_json(run.result_json)

    def replay(self, run_id: str) -> list[TurnRecord]:
        with self.database.session() as session:
            query = (
                select(TurnRecord)
                .where(TurnRecord.run_id == run_id)
                .order_by(TurnRecord.scenario_id, TurnRecord.turn_index)
            )
            return list(session.scalars(query))
