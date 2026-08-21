"""Repository for canonical/provisional Entities, evidence edges, and Knowledge Gaps."""

from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import or_, select

from echo_masque.persistence.database import Database
from echo_masque.persistence.entity_evidence_models import (
    EntityV3Record,
    EvidenceEdgeV3Record,
    KnowledgeGapRecord,
)


def _list(raw: str) -> tuple[str, ...]:
    try:
        value = json.loads(raw or "[]")
    except (json.JSONDecodeError, TypeError):
        return ()
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value if isinstance(item, str) and item)


def _list_json(values: tuple[str, ...] | list[str], *, limit: int = 64) -> str:
    return json.dumps(
        list(dict.fromkeys(str(item) for item in values if str(item)))[-limit:],
        ensure_ascii=False,
    )


def _dict(raw: str) -> dict[str, str]:
    try:
        value = json.loads(raw or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}
    if not isinstance(value, dict):
        return {}
    return {str(key): str(item) for key, item in value.items() if str(key)}


def _dict_json(value: dict[str, str]) -> str:
    return json.dumps(
        {str(key): str(item) for key, item in value.items()},
        ensure_ascii=False,
    )


def normalize_entity_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip().casefold()
    return " ".join(normalized.split())[:320]


@dataclass(frozen=True, slots=True)
class EntityV3View:
    id: str
    entity_type: str
    canonical_name: str
    aliases: tuple[str, ...]
    status: str
    merged_into_entity_id: str
    metadata: dict[str, str]
    source_refs: tuple[str, ...]
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class EvidenceEdgeV3View:
    id: str
    source_ref_type: str
    source_ref: str
    relation_type: str
    target_ref_type: str
    target_ref: str
    confidence: float
    authority_class: str
    source_kind: str
    evidence_refs: tuple[str, ...]
    status: str
    supersedes_edge_id: str
    producer: str
    source_model: str
    valid_from: datetime | None
    valid_to: datetime | None
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class KnowledgeGapView:
    id: str
    entity_id: str
    missing_fields: tuple[str, ...]
    triggered_by_ref: str
    importance: float
    resolution_state: str
    possible_sources: tuple[str, ...]
    discovery_requested: bool
    resolution_evidence_refs: tuple[str, ...]
    updated_at: datetime


class EntityEvidenceRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def _aware(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

    @classmethod
    def entity_view(cls, record: EntityV3Record) -> EntityV3View:
        return EntityV3View(
            id=record.id,
            entity_type=record.entity_type,
            canonical_name=record.canonical_name,
            aliases=_list(record.aliases_json),
            status=record.status,
            merged_into_entity_id=record.merged_into_entity_id,
            metadata=_dict(record.metadata_json),
            source_refs=_list(record.source_refs_json),
            updated_at=cls._aware(record.updated_at) or record.updated_at,
        )

    @classmethod
    def edge_view(cls, record: EvidenceEdgeV3Record) -> EvidenceEdgeV3View:
        return EvidenceEdgeV3View(
            id=record.id,
            source_ref_type=record.source_ref_type,
            source_ref=record.source_ref,
            relation_type=record.relation_type,
            target_ref_type=record.target_ref_type,
            target_ref=record.target_ref,
            confidence=record.confidence,
            authority_class=record.authority_class,
            source_kind=record.source_kind,
            evidence_refs=_list(record.evidence_refs_json),
            status=record.status,
            supersedes_edge_id=record.supersedes_edge_id,
            producer=record.producer,
            source_model=record.source_model,
            valid_from=cls._aware(record.valid_from),
            valid_to=cls._aware(record.valid_to),
            updated_at=cls._aware(record.updated_at) or record.updated_at,
        )

    @classmethod
    def gap_view(cls, record: KnowledgeGapRecord) -> KnowledgeGapView:
        return KnowledgeGapView(
            id=record.id,
            entity_id=record.entity_id,
            missing_fields=_list(record.missing_fields_json),
            triggered_by_ref=record.triggered_by_ref,
            importance=record.importance,
            resolution_state=record.resolution_state,
            possible_sources=_list(record.possible_sources_json),
            discovery_requested=record.discovery_requested,
            resolution_evidence_refs=_list(record.resolution_evidence_refs_json),
            updated_at=cls._aware(record.updated_at) or record.updated_at,
        )

    def find_entity(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        name: str,
        entity_type: str = "",
    ) -> EntityV3View | None:
        needle = normalize_entity_name(name)
        if not needle:
            return None
        with self.database.session() as session:
            statement = select(EntityV3Record).where(
                EntityV3Record.owner_id == owner_id,
                EntityV3Record.connection_id == connection_id,
                EntityV3Record.guild_id == guild_id,
                EntityV3Record.status.not_in(("rejected", "merged")),
            )
            if entity_type:
                statement = statement.where(EntityV3Record.entity_type == entity_type)
            records = list(session.scalars(statement))
        for record in records:
            names = {record.normalized_name}
            names.update(
                normalize_entity_name(item) for item in _list(record.aliases_json)
            )
            if needle in names:
                return self.entity_view(record)
        return None

    def ensure_entity(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        name: str,
        entity_type: str,
        status: str = "provisional",
        aliases: tuple[str, ...] = (),
        metadata: dict[str, str] | None = None,
        source_refs: tuple[str, ...] = (),
        now: datetime | None = None,
    ) -> EntityV3View:
        current = now or datetime.now(UTC)
        normalized = normalize_entity_name(name)
        if not normalized:
            raise ValueError("Entity name is required.")
        with self.database.session() as session:
            record = session.scalar(
                select(EntityV3Record).where(
                    EntityV3Record.owner_id == owner_id,
                    EntityV3Record.connection_id == connection_id,
                    EntityV3Record.guild_id == guild_id,
                    EntityV3Record.entity_type == entity_type,
                    EntityV3Record.normalized_name == normalized,
                )
            )
            if record is None:
                record = EntityV3Record(
                    id=str(uuid4()),
                    owner_id=owner_id,
                    connection_id=connection_id,
                    guild_id=guild_id,
                    entity_type=entity_type[:40],
                    canonical_name=" ".join(name.split())[:320],
                    normalized_name=normalized,
                    aliases_json=_list_json(list(aliases), limit=64),
                    status=status[:24],
                    metadata_json=_dict_json(metadata or {}),
                    source_refs_json=_list_json(list(source_refs), limit=64),
                    created_at=current,
                    updated_at=current,
                )
                session.add(record)
            else:
                combined_aliases = [*_list(record.aliases_json), *aliases]
                record.aliases_json = _list_json(combined_aliases, limit=64)
                combined_sources = [*_list(record.source_refs_json), *source_refs]
                record.source_refs_json = _list_json(combined_sources, limit=64)
                if metadata:
                    merged = _dict(record.metadata_json)
                    merged.update(metadata)
                    record.metadata_json = _dict_json(merged)
                if record.status == "provisional" and status == "canonical":
                    record.status = "canonical"
                record.updated_at = current
            session.commit()
            session.refresh(record)
            return self.entity_view(record)

    def confirm_entity(
        self,
        *,
        owner_id: str,
        entity_id: str,
        canonical_name: str = "",
        metadata: dict[str, str] | None = None,
        source_refs: tuple[str, ...] = (),
        now: datetime | None = None,
    ) -> EntityV3View:
        current = now or datetime.now(UTC)
        with self.database.session() as session:
            record = session.get(EntityV3Record, entity_id)
            if record is None or record.owner_id != owner_id:
                raise KeyError("Entity not found.")
            if record.status in {"rejected", "merged"}:
                raise ValueError("Rejected or merged Entity cannot be confirmed in place.")
            if canonical_name.strip():
                previous_name = record.canonical_name
                record.canonical_name = " ".join(canonical_name.split())[:320]
                record.normalized_name = normalize_entity_name(record.canonical_name)
                record.aliases_json = _list_json(
                    [*_list(record.aliases_json), previous_name],
                    limit=64,
                )
            if metadata:
                merged = _dict(record.metadata_json)
                merged.update(metadata)
                record.metadata_json = _dict_json(merged)
            record.source_refs_json = _list_json(
                [*_list(record.source_refs_json), *source_refs],
                limit=64,
            )
            record.status = "canonical"
            record.updated_at = current
            session.commit()
            session.refresh(record)
            return self.entity_view(record)

    def merge_entity(
        self,
        *,
        owner_id: str,
        source_entity_id: str,
        target_entity_id: str,
        now: datetime | None = None,
    ) -> EntityV3View:
        if source_entity_id == target_entity_id:
            raise ValueError("Entity cannot merge into itself.")
        current = now or datetime.now(UTC)
        with self.database.session() as session:
            source = session.get(EntityV3Record, source_entity_id)
            target = session.get(EntityV3Record, target_entity_id)
            if (
                source is None
                or target is None
                or source.owner_id != owner_id
                or target.owner_id != owner_id
            ):
                raise KeyError("Entity not found.")
            target.aliases_json = _list_json(
                [
                    *_list(target.aliases_json),
                    source.canonical_name,
                    *_list(source.aliases_json),
                ],
                limit=96,
            )
            target.source_refs_json = _list_json(
                [*_list(target.source_refs_json), *_list(source.source_refs_json)],
                limit=96,
            )
            target.updated_at = current
            source.status = "merged"
            source.merged_into_entity_id = target.id
            source.updated_at = current
            session.commit()
            session.refresh(source)
            return self.entity_view(source)

    def recent_entities(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        limit: int = 50,
    ) -> tuple[EntityV3View, ...]:
        with self.database.session() as session:
            records = list(
                session.scalars(
                    select(EntityV3Record)
                    .where(
                        EntityV3Record.owner_id == owner_id,
                        EntityV3Record.connection_id == connection_id,
                        EntityV3Record.guild_id == guild_id,
                        EntityV3Record.status.not_in(("rejected", "merged")),
                    )
                    .order_by(EntityV3Record.updated_at.desc())
                    .limit(max(1, min(limit, 200)))
                )
            )
        return tuple(self.entity_view(record) for record in records)

    def add_edge(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        source_ref_type: str,
        source_ref: str,
        relation_type: str,
        target_ref_type: str,
        target_ref: str,
        confidence: float,
        authority_class: str,
        source_kind: str,
        evidence_refs: tuple[str, ...],
        status: str = "active",
        producer: str = "",
        source_model: str = "",
        valid_from: datetime | None = None,
        valid_to: datetime | None = None,
        supersedes_edge_id: str = "",
        now: datetime | None = None,
    ) -> EvidenceEdgeV3View:
        current = now or datetime.now(UTC)
        allowed = {"active", "unresolved", "rejected", "superseded", "expired"}
        if status not in allowed:
            status = "unresolved"
        with self.database.session() as session:
            if supersedes_edge_id:
                previous = session.get(EvidenceEdgeV3Record, supersedes_edge_id)
                if previous is None or previous.owner_id != owner_id:
                    raise KeyError("Evidence edge to supersede not found.")
                if previous.status not in {"rejected", "superseded", "expired"}:
                    previous.status = "superseded"
                    previous.updated_at = current
            record = EvidenceEdgeV3Record(
                id=str(uuid4()),
                owner_id=owner_id,
                connection_id=connection_id,
                guild_id=guild_id,
                source_ref_type=source_ref_type[:40],
                source_ref=source_ref[:320],
                relation_type=relation_type[:80],
                target_ref_type=target_ref_type[:40],
                target_ref=target_ref[:320],
                confidence=max(0.0, min(float(confidence), 1.0)),
                authority_class=authority_class[:48],
                source_kind=source_kind[:48],
                evidence_refs_json=_list_json(list(evidence_refs), limit=64),
                status=status,
                supersedes_edge_id=supersedes_edge_id[:64],
                producer=producer[:120],
                source_model=source_model[:240],
                valid_from=valid_from,
                valid_to=valid_to,
                created_at=current,
                updated_at=current,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return self.edge_view(record)

    def reject_edge(
        self,
        *,
        owner_id: str,
        edge_id: str,
        now: datetime | None = None,
    ) -> EvidenceEdgeV3View:
        current = now or datetime.now(UTC)
        with self.database.session() as session:
            record = session.get(EvidenceEdgeV3Record, edge_id)
            if record is None or record.owner_id != owner_id:
                raise KeyError("Evidence edge not found.")
            if record.status == "superseded":
                raise ValueError("Superseded evidence history cannot be rejected in place.")
            record.status = "rejected"
            record.updated_at = current
            session.commit()
            session.refresh(record)
            return self.edge_view(record)

    def edges_for_ref(
        self,
        *,
        owner_id: str,
        ref_type: str,
        ref: str,
        active_only: bool = True,
        limit: int = 100,
    ) -> tuple[EvidenceEdgeV3View, ...]:
        with self.database.session() as session:
            statement = select(EvidenceEdgeV3Record).where(
                EvidenceEdgeV3Record.owner_id == owner_id,
                or_(
                    (
                        (EvidenceEdgeV3Record.source_ref_type == ref_type)
                        & (EvidenceEdgeV3Record.source_ref == ref)
                    ),
                    (
                        (EvidenceEdgeV3Record.target_ref_type == ref_type)
                        & (EvidenceEdgeV3Record.target_ref == ref)
                    ),
                ),
            )
            if active_only:
                statement = statement.where(
                    EvidenceEdgeV3Record.status.in_(("active", "unresolved"))
                )
            records = list(
                session.scalars(
                    statement.order_by(EvidenceEdgeV3Record.updated_at.desc()).limit(
                        max(1, min(limit, 500))
                    )
                )
            )
        return tuple(self.edge_view(record) for record in records)

    def create_gap(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        entity_id: str,
        missing_fields: tuple[str, ...],
        triggered_by_ref: str,
        importance: float,
        possible_sources: tuple[str, ...] = (),
        now: datetime | None = None,
    ) -> KnowledgeGapView:
        current = now or datetime.now(UTC)
        normalized_missing = tuple(
            dict.fromkeys(item for item in missing_fields if item)
        )
        if not normalized_missing:
            raise ValueError("Knowledge Gap requires at least one missing field.")
        with self.database.session() as session:
            open_records = list(
                session.scalars(
                    select(KnowledgeGapRecord).where(
                        KnowledgeGapRecord.owner_id == owner_id,
                        KnowledgeGapRecord.entity_id == entity_id,
                        KnowledgeGapRecord.resolution_state.in_(
                            ("unresolved", "searching")
                        ),
                    )
                )
            )
            wanted = set(normalized_missing)
            for record in open_records:
                if wanted == set(_list(record.missing_fields_json)):
                    record.importance = max(
                        record.importance,
                        max(0.0, min(importance, 1.0)),
                    )
                    record.updated_at = current
                    session.commit()
                    session.refresh(record)
                    return self.gap_view(record)
            record = KnowledgeGapRecord(
                id=str(uuid4()),
                owner_id=owner_id,
                connection_id=connection_id,
                guild_id=guild_id,
                entity_id=entity_id,
                missing_fields_json=_list_json(list(normalized_missing), limit=32),
                triggered_by_ref=triggered_by_ref[:320],
                importance=max(0.0, min(float(importance), 1.0)),
                possible_sources_json=_list_json(list(possible_sources), limit=24),
                resolution_state="unresolved",
                created_at=current,
                updated_at=current,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return self.gap_view(record)

    def unresolved_gaps(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        minimum_importance: float = 0.0,
        limit: int = 40,
    ) -> tuple[KnowledgeGapView, ...]:
        with self.database.session() as session:
            records = list(
                session.scalars(
                    select(KnowledgeGapRecord)
                    .where(
                        KnowledgeGapRecord.owner_id == owner_id,
                        KnowledgeGapRecord.connection_id == connection_id,
                        KnowledgeGapRecord.guild_id == guild_id,
                        KnowledgeGapRecord.resolution_state.in_(
                            ("unresolved", "searching")
                        ),
                        KnowledgeGapRecord.importance >= minimum_importance,
                    )
                    .order_by(
                        KnowledgeGapRecord.importance.desc(),
                        KnowledgeGapRecord.updated_at.desc(),
                    )
                    .limit(max(1, min(limit, 200)))
                )
            )
        return tuple(self.gap_view(record) for record in records)

    def mark_gap_searching(
        self,
        *,
        owner_id: str,
        gap_id: str,
        now: datetime | None = None,
    ) -> KnowledgeGapView:
        current = now or datetime.now(UTC)
        with self.database.session() as session:
            record = session.get(KnowledgeGapRecord, gap_id)
            if record is None or record.owner_id != owner_id:
                raise KeyError("Knowledge Gap not found.")
            record.resolution_state = "searching"
            record.discovery_requested = True
            record.updated_at = current
            session.commit()
            session.refresh(record)
            return self.gap_view(record)

    def resolve_gap(
        self,
        *,
        owner_id: str,
        gap_id: str,
        evidence_refs: tuple[str, ...],
        state: str = "resolved",
        now: datetime | None = None,
    ) -> KnowledgeGapView:
        current = now or datetime.now(UTC)
        allowed = {
            "resolved",
            "unresolved",
            "searching",
            "unresolvable",
            "dismissed",
        }
        if state not in allowed:
            state = "resolved"
        with self.database.session() as session:
            record = session.get(KnowledgeGapRecord, gap_id)
            if record is None or record.owner_id != owner_id:
                raise KeyError("Knowledge Gap not found.")
            record.resolution_state = state
            record.resolution_evidence_refs_json = _list_json(
                list(evidence_refs),
                limit=64,
            )
            record.updated_at = current
            session.commit()
            session.refresh(record)
            return self.gap_view(record)


__all__ = [
    "EntityEvidenceRepository",
    "EntityV3View",
    "EvidenceEdgeV3View",
    "KnowledgeGapView",
    "normalize_entity_name",
]
