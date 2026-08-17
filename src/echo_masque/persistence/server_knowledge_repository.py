"""Persistence for Discord-server Wiki pages, authority edges, and consolidation checkpoints."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import delete, select, update

from echo_masque.expression_retrieval import semantic_tokens
from echo_masque.persistence.database import Database
from echo_masque.persistence.server_knowledge_models import (
    ConversationAuthorityEdgeRecord,
    ConversationConsolidationCheckpointRecord,
    ServerWikiPageRecord,
)

_VALID_AUTHORITY_CLASSES = {"provenance", "temporal_fact", "derived_index"}


def _json_values(values: tuple[str, ...] | list[str], *, limit: int) -> str:
    bounded = list(dict.fromkeys(item.strip() for item in values if item.strip()))[-limit:]
    return json.dumps(bounded, ensure_ascii=False, separators=(",", ":"))


def _decode_list(value: str) -> list[str]:
    try:
        decoded = json.loads(value or "[]")
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(decoded, list):
        return []
    return [str(item) for item in decoded if isinstance(item, str) and item]


def _sparse_score(query: str, content: str) -> float:
    left = set(semantic_tokens(query))
    right = set(semantic_tokens(content))
    if not left or not right:
        return 0.0
    return len(left & right) / max(1, len(left | right))


class ServerWikiRepository:
    """Derived shared knowledge whose maximum visibility is one Discord guild."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def upsert_topic_page(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        topic_id: str,
        title: str,
        body: str,
        keywords: tuple[str, ...] | list[str],
        source_episode_ids: tuple[str, ...] | list[str],
        source_hash: str,
        confidence: float,
    ) -> ServerWikiPageRecord:
        page_key = f"topic:{topic_id}"[:180]
        now = datetime.now(UTC)
        with self.database.session() as session:
            record = session.scalar(
                select(ServerWikiPageRecord).where(
                    ServerWikiPageRecord.owner_id == owner_id,
                    ServerWikiPageRecord.connection_id == connection_id,
                    ServerWikiPageRecord.guild_id == guild_id,
                    ServerWikiPageRecord.page_key == page_key,
                )
            )
            if record is None:
                record = ServerWikiPageRecord(
                    id=str(uuid4()),
                    owner_id=owner_id,
                    connection_id=connection_id,
                    guild_id=guild_id,
                    page_key=page_key,
                    page_type="topic",
                    visibility_scope="server",
                    title="Conversation topic",
                    source_hash=source_hash[:64],
                )
                session.add(record)
            record.title = " ".join(title.split())[:240] or "Conversation topic"
            record.body = body.strip()[:12000]
            record.keywords_json = _json_values(tuple(keywords), limit=32)
            record.source_topic_ids_json = _json_values((topic_id,), limit=8)
            record.source_episode_ids_json = _json_values(tuple(source_episode_ids), limit=80)
            record.source_hash = source_hash[:64]
            record.confidence = max(0.0, min(1.0, confidence))
            record.stale = False
            record.updated_at = now
            session.commit()
            session.refresh(record)
            return record

    def mark_topic_stale(self, *, owner_id: str, topic_id: str) -> int:
        with self.database.session() as session:
            result = session.execute(
                update(ServerWikiPageRecord)
                .where(
                    ServerWikiPageRecord.owner_id == owner_id,
                    ServerWikiPageRecord.page_key == f"topic:{topic_id}",
                    ServerWikiPageRecord.stale.is_(False),
                )
                .values(stale=True, updated_at=datetime.now(UTC))
            )
            session.commit()
            return int(getattr(result, "rowcount", 0) or 0)

    def get_topic_page(self, *, owner_id: str, topic_id: str) -> ServerWikiPageRecord | None:
        with self.database.session() as session:
            return session.scalar(
                select(ServerWikiPageRecord).where(
                    ServerWikiPageRecord.owner_id == owner_id,
                    ServerWikiPageRecord.page_key == f"topic:{topic_id}",
                )
            )

    def lookup(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        query: str,
        limit: int,
    ) -> list[dict[str, object]]:
        bounded = max(1, min(limit, 8))
        with self.database.session() as session:
            records = list(
                session.scalars(
                    select(ServerWikiPageRecord)
                    .where(
                        ServerWikiPageRecord.owner_id == owner_id,
                        ServerWikiPageRecord.connection_id == connection_id,
                        ServerWikiPageRecord.guild_id == guild_id,
                        ServerWikiPageRecord.visibility_scope == "server",
                        ServerWikiPageRecord.stale.is_(False),
                    )
                    .order_by(ServerWikiPageRecord.updated_at.desc())
                    .limit(80)
                )
            )
        ranked = sorted(
            (
                (
                    _sparse_score(query, f"{item.title} {item.body} {item.keywords_json}"),
                    item,
                )
                for item in records
            ),
            key=lambda pair: (pair[0], pair[1].updated_at),
            reverse=True,
        )
        selected = [item for score, item in ranked if score > 0][:bounded]
        if not selected and not semantic_tokens(query):
            selected = records[:bounded]
        return [
            {
                "ref": item.id,
                "page_type": item.page_type,
                "title": item.title,
                "body": item.body[:3000],
                "keywords": _decode_list(item.keywords_json)[:16],
                "confidence": round(item.confidence, 3),
                "updated_at": item.updated_at.isoformat(),
            }
            for item in selected
        ]

    def delete_owner(self, owner_id: str) -> int:
        with self.database.session() as session:
            result = session.execute(
                delete(ServerWikiPageRecord).where(ServerWikiPageRecord.owner_id == owner_id)
            )
            session.commit()
            return int(getattr(result, "rowcount", 0) or 0)

    def claim_owner(self, source_owner_id: str, target_owner_id: str) -> int:
        with self.database.session() as session:
            result = session.execute(
                update(ServerWikiPageRecord)
                .where(ServerWikiPageRecord.owner_id == source_owner_id)
                .values(owner_id=target_owner_id)
            )
            session.commit()
            return int(getattr(result, "rowcount", 0) or 0)


class ConversationAuthorityGraphRepository:
    """Typed Graph interpretation with explicit authority classes and provenance."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def upsert_edge(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        source_ref: str,
        relation: str,
        target_ref: str,
        authority_class: str,
        confidence: float = 1.0,
        evidence_refs: tuple[str, ...] | list[str] = (),
        valid_from: datetime | None = None,
        valid_to: datetime | None = None,
        model_version: str = "",
        status: str = "active",
    ) -> ConversationAuthorityEdgeRecord:
        if authority_class not in _VALID_AUTHORITY_CLASSES:
            raise ValueError("Unsupported Graph authority class.")
        if status not in {"active", "superseded", "expired"}:
            raise ValueError("Unsupported Graph edge status.")
        if not source_ref.strip() or not relation.strip() or not target_ref.strip():
            raise ValueError("Graph edge requires source, relation, and target refs.")
        now = datetime.now(UTC)
        with self.database.session() as session:
            record = session.scalar(
                select(ConversationAuthorityEdgeRecord).where(
                    ConversationAuthorityEdgeRecord.owner_id == owner_id,
                    ConversationAuthorityEdgeRecord.connection_id == connection_id,
                    ConversationAuthorityEdgeRecord.guild_id == guild_id,
                    ConversationAuthorityEdgeRecord.source_ref == source_ref[:280],
                    ConversationAuthorityEdgeRecord.relation == relation[:80],
                    ConversationAuthorityEdgeRecord.target_ref == target_ref[:280],
                    ConversationAuthorityEdgeRecord.authority_class == authority_class,
                )
            )
            if record is None:
                record = ConversationAuthorityEdgeRecord(
                    id=str(uuid4()),
                    owner_id=owner_id,
                    connection_id=connection_id,
                    guild_id=guild_id,
                    source_ref=source_ref[:280],
                    relation=relation[:80],
                    target_ref=target_ref[:280],
                    authority_class=authority_class,
                )
                session.add(record)
            record.confidence = max(0.0, min(1.0, confidence))
            record.evidence_refs_json = _json_values(tuple(evidence_refs), limit=80)
            record.valid_from = valid_from
            record.valid_to = valid_to
            record.model_version = model_version[:80]
            record.status = status
            record.updated_at = now
            session.commit()
            session.refresh(record)
            return record

    def delete_derived_for_source(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        source_ref: str,
    ) -> int:
        with self.database.session() as session:
            result = session.execute(
                delete(ConversationAuthorityEdgeRecord).where(
                    ConversationAuthorityEdgeRecord.owner_id == owner_id,
                    ConversationAuthorityEdgeRecord.connection_id == connection_id,
                    ConversationAuthorityEdgeRecord.guild_id == guild_id,
                    ConversationAuthorityEdgeRecord.source_ref == source_ref,
                    ConversationAuthorityEdgeRecord.authority_class == "derived_index",
                )
            )
            session.commit()
            return int(getattr(result, "rowcount", 0) or 0)

    def list_scope(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        authority_class: str | None = None,
        limit: int = 200,
    ) -> list[ConversationAuthorityEdgeRecord]:
        with self.database.session() as session:
            query = select(ConversationAuthorityEdgeRecord).where(
                ConversationAuthorityEdgeRecord.owner_id == owner_id,
                ConversationAuthorityEdgeRecord.connection_id == connection_id,
                ConversationAuthorityEdgeRecord.guild_id == guild_id,
            )
            if authority_class is not None:
                query = query.where(
                    ConversationAuthorityEdgeRecord.authority_class == authority_class
                )
            return list(
                session.scalars(
                    query.order_by(ConversationAuthorityEdgeRecord.updated_at.desc()).limit(
                        max(1, min(limit, 500))
                    )
                )
            )

    def delete_owner(self, owner_id: str) -> int:
        with self.database.session() as session:
            result = session.execute(
                delete(ConversationAuthorityEdgeRecord).where(
                    ConversationAuthorityEdgeRecord.owner_id == owner_id
                )
            )
            session.commit()
            return int(getattr(result, "rowcount", 0) or 0)

    def claim_owner(self, source_owner_id: str, target_owner_id: str) -> int:
        with self.database.session() as session:
            result = session.execute(
                update(ConversationAuthorityEdgeRecord)
                .where(ConversationAuthorityEdgeRecord.owner_id == source_owner_id)
                .values(owner_id=target_owner_id)
            )
            session.commit()
            return int(getattr(result, "rowcount", 0) or 0)


class ConsolidationCheckpointRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def get(
        self,
        *,
        owner_id: str,
        topic_id: str,
    ) -> ConversationConsolidationCheckpointRecord | None:
        with self.database.session() as session:
            return session.scalar(
                select(ConversationConsolidationCheckpointRecord).where(
                    ConversationConsolidationCheckpointRecord.owner_id == owner_id,
                    ConversationConsolidationCheckpointRecord.topic_id == topic_id,
                )
            )

    def save(
        self,
        *,
        owner_id: str,
        topic_id: str,
        connection_id: str,
        guild_id: str,
        source_hash: str,
        status: str,
        reason: str,
        episode_count: int,
        memory_count: int,
        wiki_page_id: str,
        graph_edge_count: int,
        utility_status: str,
        last_error: str = "",
    ) -> ConversationConsolidationCheckpointRecord:
        if status not in {"pending", "completed", "partial", "failed"}:
            raise ValueError("Unsupported consolidation checkpoint status.")
        now = datetime.now(UTC)
        with self.database.session() as session:
            record = session.scalar(
                select(ConversationConsolidationCheckpointRecord).where(
                    ConversationConsolidationCheckpointRecord.owner_id == owner_id,
                    ConversationConsolidationCheckpointRecord.topic_id == topic_id,
                )
            )
            if record is None:
                record = ConversationConsolidationCheckpointRecord(
                    id=str(uuid4()),
                    owner_id=owner_id,
                    topic_id=topic_id,
                    connection_id=connection_id,
                    guild_id=guild_id,
                )
                session.add(record)
            record.source_hash = source_hash[:64]
            record.status = status
            record.reason = reason[:80]
            record.episode_count = max(0, episode_count)
            record.memory_count = max(0, memory_count)
            record.wiki_page_id = wiki_page_id[:36]
            record.graph_edge_count = max(0, graph_edge_count)
            record.utility_status = utility_status[:40]
            record.last_error = last_error[:1000]
            record.updated_at = now
            record.completed_at = now if status == "completed" else None
            session.commit()
            session.refresh(record)
            return record

    def delete_owner(self, owner_id: str) -> int:
        with self.database.session() as session:
            result = session.execute(
                delete(ConversationConsolidationCheckpointRecord).where(
                    ConversationConsolidationCheckpointRecord.owner_id == owner_id
                )
            )
            session.commit()
            return int(getattr(result, "rowcount", 0) or 0)

    def claim_owner(self, source_owner_id: str, target_owner_id: str) -> int:
        with self.database.session() as session:
            result = session.execute(
                update(ConversationConsolidationCheckpointRecord)
                .where(ConversationConsolidationCheckpointRecord.owner_id == source_owner_id)
                .values(owner_id=target_owner_id)
            )
            session.commit()
            return int(getattr(result, "rowcount", 0) or 0)


__all__ = [
    "ConsolidationCheckpointRepository",
    "ConversationAuthorityGraphRepository",
    "ServerWikiRepository",
]
