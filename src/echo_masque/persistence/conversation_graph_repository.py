"""Bounded persistence operations for the derived Conversation Intelligence Graph."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, or_, select
from sqlalchemy.sql.elements import ColumnElement

from echo_masque.persistence.conversation_graph_models import (
    ConversationGraphEdgeRecord,
    ConversationGraphNodeRecord,
)
from echo_masque.persistence.database import Database

_MAX_PROVENANCE = 8
_MAX_PAYLOAD_CHARS = 8_000
_MAX_SUMMARY_CHARS = 2_000


@dataclass(frozen=True, slots=True)
class ConversationGraphScope:
    platform: str
    connection_id: str
    guild_id: str
    channel_id: str
    thread_id: str = ""
    scope_owner_id: str = ""


@dataclass(frozen=True, slots=True)
class ConversationGraphNeighbor:
    edge: ConversationGraphEdgeRecord
    node: ConversationGraphNodeRecord


def _compact(value: str, maximum: int) -> str:
    return " ".join(value.split())[:maximum]


def _canonical(value: str) -> str:
    return " ".join(value.casefold().split())[:240]


def _confidence(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _current(value: datetime | None) -> datetime:
    return _aware(value) if value is not None else datetime.now(UTC)


def _expires(now: datetime, ttl_seconds: int | None) -> datetime | None:
    if ttl_seconds is None:
        return None
    return now + timedelta(seconds=max(1, ttl_seconds))


def _json_object(value: dict[str, Any], maximum_chars: int) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if len(encoded) <= maximum_chars:
        return encoded
    return "{}"


def _provenance(value: str | None) -> list[dict[str, Any]]:
    if not value:
        return []
    try:
        decoded = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(decoded, list):
        return []
    return [item for item in decoded if isinstance(item, dict)][-_MAX_PROVENANCE:]


def _rowcount(result: object) -> int:
    value = getattr(result, "rowcount", 0)
    return value if isinstance(value, int) else 0


class ConversationGraphRepository:
    """Store rebuildable graph evidence without owning interpretation semantics."""

    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def _scope_filters(
        model: type[ConversationGraphNodeRecord] | type[ConversationGraphEdgeRecord],
        scope: ConversationGraphScope,
    ) -> tuple[ColumnElement[bool], ...]:
        return (
            model.scope_owner_id == scope.scope_owner_id,
            model.platform == scope.platform,
            model.connection_id == scope.connection_id,
            model.guild_id == scope.guild_id,
            model.channel_id == scope.channel_id,
            model.thread_id == scope.thread_id,
        )

    @staticmethod
    def _same_scope(record: ConversationGraphNodeRecord, scope: ConversationGraphScope) -> bool:
        return (
            record.scope_owner_id == scope.scope_owner_id
            and record.platform == scope.platform
            and record.connection_id == scope.connection_id
            and record.guild_id == scope.guild_id
            and record.channel_id == scope.channel_id
            and record.thread_id == scope.thread_id
        )

    def find_node(
        self,
        *,
        scope: ConversationGraphScope,
        node_type: str,
        canonical_key: str,
        now: datetime | None = None,
    ) -> ConversationGraphNodeRecord | None:
        """Return one active scoped node by canonical identity without creating it."""

        current = _current(now)
        kind = _compact(node_type, 40)
        key = _canonical(canonical_key)
        if not kind or not key:
            return None
        with self.database.session() as session:
            return session.scalar(
                select(ConversationGraphNodeRecord)
                .where(
                    *self._scope_filters(ConversationGraphNodeRecord, scope),
                    ConversationGraphNodeRecord.node_type == kind,
                    ConversationGraphNodeRecord.canonical_key == key,
                    or_(
                        ConversationGraphNodeRecord.expires_at.is_(None),
                        ConversationGraphNodeRecord.expires_at > current,
                    ),
                )
                .limit(1)
            )

    def upsert_node(
        self,
        *,
        scope: ConversationGraphScope,
        node_type: str,
        canonical_key: str,
        label: str = "",
        summary: str = "",
        payload: dict[str, Any] | None = None,
        ttl_seconds: int | None = None,
        now: datetime | None = None,
    ) -> ConversationGraphNodeRecord:
        current = _current(now)
        kind = _compact(node_type, 40)
        key = _canonical(canonical_key)
        if not kind or not key:
            raise ValueError("Conversation Graph nodes require node_type and canonical_key.")
        with self.database.session() as session:
            statement = select(ConversationGraphNodeRecord).where(
                *self._scope_filters(ConversationGraphNodeRecord, scope),
                ConversationGraphNodeRecord.node_type == kind,
                ConversationGraphNodeRecord.canonical_key == key,
            )
            record = session.scalar(statement)
            if record is None:
                record = ConversationGraphNodeRecord(
                    id=str(uuid4()),
                    scope_owner_id=scope.scope_owner_id,
                    platform=scope.platform,
                    connection_id=scope.connection_id,
                    guild_id=scope.guild_id,
                    channel_id=scope.channel_id,
                    thread_id=scope.thread_id,
                    node_type=kind,
                    canonical_key=key,
                )
                session.add(record)
            record.label = _compact(label, 240)
            record.summary = _compact(summary, _MAX_SUMMARY_CHARS)
            record.payload_json = _json_object(payload or {}, _MAX_PAYLOAD_CHARS)
            record.last_active_at = current
            record.expires_at = _expires(current, ttl_seconds)
            record.updated_at = current
            session.commit()
            session.refresh(record)
            return record

    def get_node(
        self,
        node_id: str,
        *,
        scope: ConversationGraphScope | None = None,
    ) -> ConversationGraphNodeRecord | None:
        with self.database.session() as session:
            record = session.get(ConversationGraphNodeRecord, node_id)
            if record is None:
                return None
            if scope is not None and not self._same_scope(record, scope):
                return None
            return record

    def upsert_edge(
        self,
        *,
        scope: ConversationGraphScope,
        source_node_id: str,
        relation: str,
        target_node_id: str,
        confidence: float,
        source_type: str = "message",
        source_message_id: str = "",
        source_burst_id: str = "",
        provenance: dict[str, Any] | None = None,
        negative_evidence: bool = False,
        ttl_seconds: int | None = None,
        now: datetime | None = None,
    ) -> ConversationGraphEdgeRecord:
        current = _current(now)
        relation_key = _compact(relation, 60)
        if not relation_key:
            raise ValueError("Conversation Graph edges require a relation.")
        with self.database.session() as session:
            source = session.get(ConversationGraphNodeRecord, source_node_id)
            target = session.get(ConversationGraphNodeRecord, target_node_id)
            if source is None or target is None:
                raise KeyError("conversation_graph_node")
            if not self._same_scope(source, scope) or not self._same_scope(target, scope):
                raise ValueError("Conversation Graph edges cannot cross graph scopes.")
            statement = select(ConversationGraphEdgeRecord).where(
                *self._scope_filters(ConversationGraphEdgeRecord, scope),
                ConversationGraphEdgeRecord.source_node_id == source_node_id,
                ConversationGraphEdgeRecord.relation == relation_key,
                ConversationGraphEdgeRecord.target_node_id == target_node_id,
            )
            record = session.scalar(statement)
            if record is None:
                record = ConversationGraphEdgeRecord(
                    id=str(uuid4()),
                    scope_owner_id=scope.scope_owner_id,
                    platform=scope.platform,
                    connection_id=scope.connection_id,
                    guild_id=scope.guild_id,
                    channel_id=scope.channel_id,
                    thread_id=scope.thread_id,
                    source_node_id=source_node_id,
                    relation=relation_key,
                    target_node_id=target_node_id,
                    evidence_count=0,
                    negative_evidence_count=0,
                    provenance_json="[]",
                )
                session.add(record)
            record.confidence = _confidence(confidence)
            if negative_evidence:
                record.negative_evidence_count += 1
            else:
                record.evidence_count += 1
            record.source_type = _compact(source_type, 40) or "message"
            record.source_message_id = _compact(source_message_id, 200)
            record.source_burst_id = _compact(source_burst_id, 80)
            values = _provenance(record.provenance_json)
            if provenance:
                bounded = dict(provenance)
                bounded["recorded_at"] = current.isoformat()
                values.append(bounded)
            record.provenance_json = json.dumps(
                values[-_MAX_PROVENANCE:],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            record.status = "active"
            record.last_active_at = current
            record.expires_at = _expires(current, ttl_seconds)
            record.updated_at = current
            source.last_active_at = current
            target.last_active_at = current
            session.commit()
            session.refresh(record)
            return record

    def neighbors(
        self,
        *,
        scope: ConversationGraphScope,
        node_id: str,
        relations: tuple[str, ...] = (),
        limit: int = 20,
        now: datetime | None = None,
    ) -> tuple[ConversationGraphNeighbor, ...]:
        current = _current(now)
        relation_keys = tuple(_compact(item, 60) for item in relations if _compact(item, 60))
        with self.database.session() as session:
            source = session.get(ConversationGraphNodeRecord, node_id)
            if source is None or not self._same_scope(source, scope):
                return ()
            statement = (
                select(ConversationGraphEdgeRecord)
                .where(
                    *self._scope_filters(ConversationGraphEdgeRecord, scope),
                    ConversationGraphEdgeRecord.source_node_id == node_id,
                    ConversationGraphEdgeRecord.status == "active",
                    or_(
                        ConversationGraphEdgeRecord.expires_at.is_(None),
                        ConversationGraphEdgeRecord.expires_at > current,
                    ),
                )
                .order_by(
                    ConversationGraphEdgeRecord.confidence.desc(),
                    ConversationGraphEdgeRecord.last_active_at.desc(),
                )
                .limit(max(1, min(limit, 100)))
            )
            if relation_keys:
                statement = statement.where(
                    ConversationGraphEdgeRecord.relation.in_(relation_keys)
                )
            edges = list(session.scalars(statement))
            values: list[ConversationGraphNeighbor] = []
            for edge in edges:
                target = session.get(ConversationGraphNodeRecord, edge.target_node_id)
                if target is None:
                    continue
                if target.expires_at is not None and _aware(target.expires_at) <= current:
                    continue
                values.append(ConversationGraphNeighbor(edge=edge, node=target))
            return tuple(values)

    def cleanup_expired(self, *, now: datetime | None = None) -> dict[str, int]:
        current = _current(now)
        with self.database.session() as session:
            edge_result = session.execute(
                delete(ConversationGraphEdgeRecord).where(
                    ConversationGraphEdgeRecord.expires_at.is_not(None),
                    ConversationGraphEdgeRecord.expires_at <= current,
                )
            )
            node_result = session.execute(
                delete(ConversationGraphNodeRecord).where(
                    ConversationGraphNodeRecord.expires_at.is_not(None),
                    ConversationGraphNodeRecord.expires_at <= current,
                )
            )
            session.commit()
            return {
                "edges": _rowcount(edge_result),
                "nodes": _rowcount(node_result),
            }

    def delete_scope(self, scope: ConversationGraphScope) -> dict[str, int]:
        with self.database.session() as session:
            edge_result = session.execute(
                delete(ConversationGraphEdgeRecord).where(
                    *self._scope_filters(ConversationGraphEdgeRecord, scope)
                )
            )
            node_result = session.execute(
                delete(ConversationGraphNodeRecord).where(
                    *self._scope_filters(ConversationGraphNodeRecord, scope)
                )
            )
            session.commit()
            return {
                "edges": _rowcount(edge_result),
                "nodes": _rowcount(node_result),
            }


__all__ = [
    "ConversationGraphNeighbor",
    "ConversationGraphRepository",
    "ConversationGraphScope",
]
