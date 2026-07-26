"""Persistence repository for targets, character cards, runtime config, and trials."""

import json
from uuid import uuid4

from sqlalchemy import delete, func, select

from echo_masque.domain import TrialStatus, TrialSuiteResult
from echo_masque.persistence.database import Database
from echo_masque.persistence.models import (
    AdminRuntimeRecord,
    CharacterCardRecord,
    CharacterTrialRecord,
    EvidenceRecord,
    TargetRecord,
    TrialEventRecord,
    TrialRunRecord,
    TurnRecord,
)
from echo_masque.security import redact

DEMO_CARD_IDS = ("card-stable-ann", "card-fragile-ann")


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

    def seed_demo_character_cards(self) -> None:
        """Compatibility shim: built-in cards were removed in Phase 12."""

        self.remove_demo_character_cards()

    def remove_demo_character_cards(self) -> None:
        """Remove user-facing demo cards without deleting their historical trial runs."""

        with self.database.session() as session:
            session.execute(
                delete(CharacterTrialRecord).where(
                    CharacterTrialRecord.character_card_id.in_(DEMO_CARD_IDS)
                )
            )
            session.execute(
                delete(CharacterCardRecord).where(CharacterCardRecord.id.in_(DEMO_CARD_IDS))
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

    def update_target(
        self,
        target_id: str,
        *,
        name: str,
        config: dict[str, object],
    ) -> TargetRecord | None:
        with self.database.session() as session:
            record = session.get(TargetRecord, target_id)
            if record is None:
                return None
            record.name = name
            record.config_json = json.dumps(redact(config))
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

    def create_character_card(
        self,
        *,
        owner_id: str,
        target_id: str,
        display_name: str,
        subtitle: str,
        subject_type: str,
        persona_summary: str,
        traits: list[str],
        tags: list[str],
        expected_tone: str | None,
        forbidden_behaviors: list[str],
        memory_summary: str | None,
        preferred_suites: list[str],
        portrait_variant: str,
    ) -> CharacterCardRecord:
        record = CharacterCardRecord(
            id=str(uuid4()),
            owner_id=owner_id,
            target_id=target_id,
            display_name=display_name,
            subtitle=subtitle,
            subject_type=subject_type,
            persona_summary=persona_summary,
            traits_json=json.dumps(traits),
            tags_json=json.dumps(tags),
            expected_tone=expected_tone,
            forbidden_behaviors_json=json.dumps(forbidden_behaviors),
            memory_summary=memory_summary,
            preferred_suites_json=json.dumps(preferred_suites),
            portrait_variant=portrait_variant,
        )
        with self.database.session() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
        return record

    def update_character_card(
        self,
        card_id: str,
        owner_id: str,
        *,
        display_name: str,
        subtitle: str,
        subject_type: str,
        persona_summary: str,
        traits: list[str],
        tags: list[str],
        expected_tone: str | None,
        forbidden_behaviors: list[str],
        memory_summary: str | None,
        preferred_suites: list[str],
        portrait_variant: str,
    ) -> CharacterCardRecord | None:
        with self.database.session() as session:
            record = session.get(CharacterCardRecord, card_id)
            if record is None or record.owner_id != owner_id or record.id in DEMO_CARD_IDS:
                return None
            record.display_name = display_name
            record.subtitle = subtitle
            record.subject_type = subject_type
            record.persona_summary = persona_summary
            record.traits_json = json.dumps(traits)
            record.tags_json = json.dumps(tags)
            record.expected_tone = expected_tone
            record.forbidden_behaviors_json = json.dumps(forbidden_behaviors)
            record.memory_summary = memory_summary
            record.preferred_suites_json = json.dumps(preferred_suites)
            record.portrait_variant = portrait_variant
            session.commit()
            session.refresh(record)
            return record

    def list_character_cards(self, owner_id: str) -> list[CharacterCardRecord]:
        with self.database.session() as session:
            query = (
                select(CharacterCardRecord)
                .where(
                    CharacterCardRecord.owner_id == owner_id,
                    CharacterCardRecord.id.not_in(DEMO_CARD_IDS),
                )
                .order_by(CharacterCardRecord.created_at.desc())
            )
            return list(session.scalars(query))

    def get_character_card(
        self, card_id: str, owner_id: str | None = None
    ) -> CharacterCardRecord | None:
        if card_id in DEMO_CARD_IDS:
            return None
        with self.database.session() as session:
            card = session.get(CharacterCardRecord, card_id)
            if card is None or (owner_id is not None and card.owner_id != owner_id):
                return None
            return card

    def character_for_run(self, run_id: str) -> CharacterCardRecord | None:
        with self.database.session() as session:
            card_id = session.scalar(
                select(CharacterTrialRecord.character_card_id).where(
                    CharacterTrialRecord.run_id == run_id
                )
            )
            if card_id is None:
                return None
            return session.get(CharacterCardRecord, card_id)

    def delete_character_card(self, card_id: str, owner_id: str) -> bool:
        with self.database.session() as session:
            card = session.get(CharacterCardRecord, card_id)
            if card is None or card.owner_id != owner_id or card.id in DEMO_CARD_IDS:
                return False
            session.execute(
                delete(CharacterTrialRecord).where(
                    CharacterTrialRecord.character_card_id == card_id
                )
            )
            session.delete(card)
            session.commit()
            return True

    def get_admin_runtime(self) -> AdminRuntimeRecord | None:
        with self.database.session() as session:
            return session.get(AdminRuntimeRecord, "default")

    def save_admin_runtime(self, config: dict[str, object]) -> AdminRuntimeRecord:
        safe_config = json.dumps(redact(config))
        with self.database.session() as session:
            record = session.get(AdminRuntimeRecord, "default")
            if record is None:
                record = AdminRuntimeRecord(id="default", config_json=safe_config)
                session.add(record)
            else:
                record.config_json = safe_config
            session.commit()
            session.refresh(record)
            return record

    def create_run(
        self, *, target_id: str, suite: list[str], character_card_id: str | None = None
    ) -> TrialRunRecord:
        run = TrialRunRecord(
            id=str(uuid4()),
            target_id=target_id,
            status=TrialStatus.PENDING.value,
            suite_json=json.dumps(suite),
        )
        with self.database.session() as session:
            session.add(run)
            if character_card_id is not None:
                session.add(
                    CharacterTrialRecord(run_id=run.id, character_card_id=character_card_id)
                )
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

    def clear_trial_events(self, run_id: str) -> None:
        with self.database.session() as session:
            session.execute(delete(TrialEventRecord).where(TrialEventRecord.run_id == run_id))
            session.commit()

    def append_trial_event(
        self,
        run_id: str,
        event_type: str,
        payload: dict[str, object],
        *,
        scenario_id: str | None = None,
        turn_index: int | None = None,
    ) -> TrialEventRecord:
        with self.database.session() as session:
            latest = session.scalar(
                select(func.max(TrialEventRecord.sequence)).where(
                    TrialEventRecord.run_id == run_id
                )
            )
            record = TrialEventRecord(
                run_id=run_id,
                sequence=(latest or 0) + 1,
                event_type=event_type,
                scenario_id=scenario_id,
                turn_index=turn_index,
                payload_json=json.dumps(redact(payload)),
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def list_trial_events(self, run_id: str, after: int = 0) -> list[TrialEventRecord]:
        with self.database.session() as session:
            query = (
                select(TrialEventRecord)
                .where(
                    TrialEventRecord.run_id == run_id,
                    TrialEventRecord.sequence > after,
                )
                .order_by(TrialEventRecord.sequence)
            )
            return list(session.scalars(query))

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
