"""Repository and cascade invalidation support for Intelligence Core v3 Beliefs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, select

from echo_masque.persistence.belief_models import (
    BeliefEvidenceDependencyRecord,
    BeliefRevisionEventRecord,
    BeliefV3Record,
)
from echo_masque.persistence.database import Database


def _decode(raw: str) -> tuple[str, ...]:
    try:
        value = json.loads(raw or "[]")
    except (json.JSONDecodeError, TypeError):
        return ()
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value if isinstance(item, str) and item)


def _encode(values: tuple[str, ...] | list[str], *, limit: int = 96) -> str:
    return json.dumps(
        list(dict.fromkeys(str(item) for item in values if str(item)))[-limit:],
        ensure_ascii=False,
    )


@dataclass(frozen=True, slots=True)
class BeliefV3View:
    id: str
    character_card_id: str
    subject_entity_id: str
    subject_ref: str
    predicate: str
    value_text: str
    scope: str
    authority_class: str
    authority_score: float
    origin: str
    confidence: float
    importance: float
    status: str
    supersedes_belief_id: str
    evidence_refs: tuple[str, ...]
    authored: bool
    valid_from: datetime | None
    valid_to: datetime | None
    last_confirmed_at: datetime | None
    stale_after: datetime | None
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class CascadeInvalidationResult:
    evidence_edge_id: str
    affected_belief_ids: tuple[str, ...]
    rejected_belief_ids: tuple[str, ...]
    provisional_belief_ids: tuple[str, ...]


class BeliefRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def _aware(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

    @classmethod
    def view(cls, record: BeliefV3Record) -> BeliefV3View:
        return BeliefV3View(
            id=record.id,
            character_card_id=record.character_card_id,
            subject_entity_id=record.subject_entity_id,
            subject_ref=record.subject_ref,
            predicate=record.predicate,
            value_text=record.value_text,
            scope=record.scope,
            authority_class=record.authority_class,
            authority_score=record.authority_score,
            origin=record.origin,
            confidence=record.confidence,
            importance=record.importance,
            status=record.status,
            supersedes_belief_id=record.supersedes_belief_id,
            evidence_refs=_decode(record.evidence_refs_json),
            authored=record.authored,
            valid_from=cls._aware(record.valid_from),
            valid_to=cls._aware(record.valid_to),
            last_confirmed_at=cls._aware(record.last_confirmed_at),
            stale_after=cls._aware(record.stale_after),
            updated_at=cls._aware(record.updated_at) or record.updated_at,
        )

    def create(
        self,
        *,
        owner_id: str,
        character_card_id: str,
        connection_id: str,
        guild_id: str,
        subject_entity_id: str,
        subject_ref: str,
        predicate: str,
        value_text: str,
        scope: str,
        authority_class: str,
        authority_score: float,
        origin: str,
        confidence: float,
        importance: float,
        status: str,
        evidence_refs: tuple[str, ...],
        authored: bool = False,
        supersedes_belief_id: str = "",
        dependency_edge_ids: tuple[str, ...] = (),
        valid_from: datetime | None = None,
        valid_to: datetime | None = None,
        stale_after: datetime | None = None,
        now: datetime | None = None,
    ) -> BeliefV3View:
        current = now or datetime.now(UTC)
        allowed = {
            "provisional",
            "active",
            "disputed",
            "superseded",
            "rejected",
            "expired",
        }
        normalized_status = status if status in allowed else "provisional"
        record = BeliefV3Record(
            id=str(uuid4()),
            owner_id=owner_id,
            character_card_id=character_card_id[:64],
            connection_id=connection_id[:64],
            guild_id=guild_id[:200],
            subject_entity_id=subject_entity_id[:64],
            subject_ref=subject_ref[:240],
            predicate=predicate[:160],
            value_text=value_text[:8000],
            scope=scope[:40],
            authority_class=authority_class[:64],
            authority_score=max(0.0, min(float(authority_score), 1.0)),
            origin=origin[:64],
            confidence=max(0.0, min(float(confidence), 1.0)),
            importance=max(0.0, min(float(importance), 1.0)),
            status=normalized_status,
            supersedes_belief_id=supersedes_belief_id[:64],
            evidence_refs_json=_encode(list(evidence_refs), limit=96),
            authored=authored,
            valid_from=valid_from or current,
            valid_to=valid_to,
            last_confirmed_at=current if normalized_status == "active" else None,
            stale_after=stale_after,
            created_at=current,
            updated_at=current,
        )
        with self.database.session() as session:
            if supersedes_belief_id:
                previous = session.get(BeliefV3Record, supersedes_belief_id)
                if previous is None or previous.owner_id != owner_id:
                    raise KeyError("Belief to supersede not found.")
                if previous.authored and not authored:
                    raise ValueError(
                        "Conversation-derived Belief cannot supersede authored Belief."
                    )
                if previous.status not in {"rejected", "expired", "superseded"}:
                    previous.status = "superseded"
                    previous.valid_to = current
                    previous.updated_at = current
            session.add(record)
            session.flush()
            for edge_id in dict.fromkeys(item for item in dependency_edge_ids if item):
                session.add(
                    BeliefEvidenceDependencyRecord(
                        id=str(uuid4()),
                        owner_id=owner_id,
                        belief_id=record.id,
                        evidence_edge_id=edge_id[:64],
                        status="active",
                        created_at=current,
                        updated_at=current,
                    )
                )
            session.commit()
            session.refresh(record)
            return self.view(record)

    def record_revision_event(
        self,
        *,
        owner_id: str,
        belief_id: str,
        previous_belief_id: str,
        subject_ref: str,
        predicate: str,
        action: str,
        reason: str,
        source_message_id: str = "",
        now: datetime | None = None,
    ) -> None:
        current = now or datetime.now(UTC)
        with self.database.session() as session:
            session.add(
                BeliefRevisionEventRecord(
                    id=str(uuid4()),
                    owner_id=owner_id,
                    belief_id=belief_id[:64],
                    previous_belief_id=previous_belief_id[:64],
                    subject_ref=subject_ref[:240],
                    predicate=predicate[:160],
                    action=action[:32],
                    reason=" ".join(reason.split())[:500],
                    source_message_id=source_message_id[:200],
                    created_at=current,
                )
            )
            session.commit()

    def active_for_claim(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        subject_entity_id: str = "",
        subject_ref: str = "",
        predicate: str,
        character_card_id: str = "",
    ) -> tuple[BeliefV3View, ...]:
        with self.database.session() as session:
            statement = select(BeliefV3Record).where(
                BeliefV3Record.owner_id == owner_id,
                BeliefV3Record.connection_id == connection_id,
                BeliefV3Record.guild_id == guild_id,
                BeliefV3Record.predicate == predicate,
                BeliefV3Record.status.in_(("active", "provisional", "disputed")),
            )
            if subject_entity_id:
                statement = statement.where(
                    BeliefV3Record.subject_entity_id == subject_entity_id
                )
            elif subject_ref:
                statement = statement.where(BeliefV3Record.subject_ref == subject_ref)
            if character_card_id:
                statement = statement.where(
                    (BeliefV3Record.character_card_id == "")
                    | (BeliefV3Record.character_card_id == character_card_id)
                )
            records = list(
                session.scalars(
                    statement.order_by(BeliefV3Record.updated_at.desc()).limit(50)
                )
            )
        return tuple(self.view(record) for record in records)

    def recall(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        character_card_id: str = "",
        subject_refs: tuple[str, ...] = (),
        limit: int = 60,
        now: datetime | None = None,
    ) -> tuple[BeliefV3View, ...]:
        current = now or datetime.now(UTC)
        with self.database.session() as session:
            statement = select(BeliefV3Record).where(
                BeliefV3Record.owner_id == owner_id,
                BeliefV3Record.connection_id == connection_id,
                BeliefV3Record.guild_id == guild_id,
                BeliefV3Record.status.in_(("active", "provisional", "disputed")),
            )
            if character_card_id:
                statement = statement.where(
                    (BeliefV3Record.character_card_id == "")
                    | (BeliefV3Record.character_card_id == character_card_id)
                )
            if subject_refs:
                statement = statement.where(BeliefV3Record.subject_ref.in_(subject_refs))
            records = list(
                session.scalars(
                    statement.order_by(
                        BeliefV3Record.importance.desc(),
                        BeliefV3Record.updated_at.desc(),
                    ).limit(max(1, min(limit, 200)))
                )
            )
            changed = False
            active: list[BeliefV3Record] = []
            for record in records:
                stale = self._aware(record.stale_after)
                valid_to = self._aware(record.valid_to)
                if valid_to is not None and valid_to <= current:
                    record.status = "expired"
                    record.updated_at = current
                    changed = True
                    continue
                if stale is not None and stale <= current and record.status == "active":
                    record.status = "provisional"
                    record.updated_at = current
                    changed = True
                active.append(record)
            if changed:
                session.commit()
        return tuple(self.view(record) for record in active)

    def reinforce(
        self,
        *,
        owner_id: str,
        belief_id: str,
        confidence: float,
        evidence_refs: tuple[str, ...],
        now: datetime | None = None,
    ) -> BeliefV3View:
        current = now or datetime.now(UTC)
        with self.database.session() as session:
            record = session.get(BeliefV3Record, belief_id)
            if record is None or record.owner_id != owner_id:
                raise KeyError("Belief not found.")
            if record.status in {"rejected", "expired", "superseded"}:
                raise ValueError("Inactive Belief cannot be reinforced.")
            record.confidence = max(
                record.confidence,
                max(0.0, min(float(confidence), 1.0)),
            )
            record.evidence_refs_json = _encode(
                list(_decode(record.evidence_refs_json)) + list(evidence_refs),
                limit=96,
            )
            if record.confidence >= 0.75 and record.status == "provisional":
                record.status = "active"
            record.last_confirmed_at = current
            record.updated_at = current
            session.commit()
            session.refresh(record)
            return self.view(record)

    def mark_disputed(
        self,
        *,
        owner_id: str,
        belief_ids: tuple[str, ...],
        now: datetime | None = None,
    ) -> tuple[BeliefV3View, ...]:
        current = now or datetime.now(UTC)
        values: list[BeliefV3View] = []
        with self.database.session() as session:
            for belief_id in dict.fromkeys(belief_ids):
                record = session.get(BeliefV3Record, belief_id)
                if record is None or record.owner_id != owner_id:
                    continue
                if record.status in {"active", "provisional"}:
                    record.status = "disputed"
                    record.updated_at = current
                values.append(self.view(record))
            session.commit()
        return tuple(values)

    def reject(
        self,
        *,
        owner_id: str,
        belief_id: str,
        now: datetime | None = None,
    ) -> BeliefV3View:
        current = now or datetime.now(UTC)
        with self.database.session() as session:
            record = session.get(BeliefV3Record, belief_id)
            if record is None or record.owner_id != owner_id:
                raise KeyError("Belief not found.")
            if record.authored:
                raise ValueError("Authored Belief cannot be auto-rejected.")
            record.status = "rejected"
            record.valid_to = current
            record.updated_at = current
            session.commit()
            session.refresh(record)
            return self.view(record)

    def invalidate_evidence_edge(
        self,
        *,
        owner_id: str,
        evidence_edge_id: str,
        now: datetime | None = None,
    ) -> CascadeInvalidationResult:
        current = now or datetime.now(UTC)
        affected: list[str] = []
        rejected: list[str] = []
        provisional: list[str] = []
        with self.database.session() as session:
            dependencies = list(
                session.scalars(
                    select(BeliefEvidenceDependencyRecord).where(
                        BeliefEvidenceDependencyRecord.owner_id == owner_id,
                        BeliefEvidenceDependencyRecord.evidence_edge_id
                        == evidence_edge_id,
                        BeliefEvidenceDependencyRecord.status == "active",
                    )
                )
            )
            for dependency in dependencies:
                dependency.status = "invalid"
                dependency.updated_at = current
                belief = session.get(BeliefV3Record, dependency.belief_id)
                if belief is None or belief.owner_id != owner_id:
                    continue
                affected.append(belief.id)
                active_count = session.scalar(
                    select(func.count(BeliefEvidenceDependencyRecord.id)).where(
                        BeliefEvidenceDependencyRecord.belief_id == belief.id,
                        BeliefEvidenceDependencyRecord.status == "active",
                    )
                )
                if int(active_count or 0) > 0 or belief.authored:
                    continue
                if belief.origin in {
                    "llm_inference",
                    "media_inference",
                    "visual_grounding",
                }:
                    belief.status = "rejected"
                    belief.valid_to = current
                    rejected.append(belief.id)
                elif belief.status not in {"superseded", "expired", "rejected"}:
                    belief.status = "provisional"
                    provisional.append(belief.id)
                belief.updated_at = current
            session.commit()
        return CascadeInvalidationResult(
            evidence_edge_id=evidence_edge_id,
            affected_belief_ids=tuple(dict.fromkeys(affected)),
            rejected_belief_ids=tuple(dict.fromkeys(rejected)),
            provisional_belief_ids=tuple(dict.fromkeys(provisional)),
        )


__all__ = [
    "BeliefRepository",
    "BeliefV3View",
    "CascadeInvalidationResult",
]
