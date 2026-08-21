"""Topic-free server Wiki and knowledge consolidation persistence."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import delete, select

from echo_masque.expression_retrieval import semantic_tokens
from echo_masque.persistence.database import Database
from echo_masque.persistence.server_knowledge_v3_models import (
    KnowledgeConsolidationCheckpointV3Record,
    ServerWikiPageV3Record,
)


def _encode(values: tuple[str, ...] | list[str], *, limit: int) -> str:
    clean = list(dict.fromkeys(str(item).strip() for item in values if str(item).strip()))[-limit:]
    return json.dumps(clean, ensure_ascii=False, separators=(",", ":"))


def _decode(value: str) -> tuple[str, ...]:
    try:
        decoded = json.loads(value or "[]")
    except (json.JSONDecodeError, TypeError):
        return ()
    if not isinstance(decoded, list):
        return ()
    return tuple(str(item) for item in decoded if isinstance(item, str) and item)


def _score(query: str, text: str) -> float:
    left = set(semantic_tokens(query))
    right = set(semantic_tokens(text))
    if not left or not right:
        return 0.0
    return len(left & right) / max(1, len(left | right))


class ServerWikiV3Repository:
    """Knowledge projection keyed by Entity/Concept/Event/Project, never conversation Topic."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def upsert_page(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        page_type: str,
        subject_ref: str,
        title: str,
        body: str,
        keywords: tuple[str, ...] = (),
        source_episode_ids: tuple[str, ...] = (),
        source_entity_ids: tuple[str, ...] = (),
        source_belief_ids: tuple[str, ...] = (),
        source_evidence_edge_ids: tuple[str, ...] = (),
        source_hash: str,
        confidence: float,
        now: datetime | None = None,
    ) -> ServerWikiPageV3Record:
        current = now or datetime.now(UTC)
        normalized_type = page_type.strip().casefold()
        if normalized_type not in {"entity", "concept", "event", "project", "organization", "place"}:
            raise ValueError("Unsupported Wiki v3 page type.")
        compact_ref = " ".join(subject_ref.split())[:320]
        if not compact_ref:
            raise ValueError("Wiki v3 subject_ref is required.")
        page_key = f"{normalized_type}:{compact_ref}"[:220]
        with self.database.session() as session:
            record = session.scalar(
                select(ServerWikiPageV3Record).where(
                    ServerWikiPageV3Record.owner_id == owner_id,
                    ServerWikiPageV3Record.connection_id == connection_id,
                    ServerWikiPageV3Record.guild_id == guild_id,
                    ServerWikiPageV3Record.page_key == page_key,
                )
            )
            if record is None:
                record = ServerWikiPageV3Record(
                    id=str(uuid4()),
                    owner_id=owner_id,
                    connection_id=connection_id,
                    guild_id=guild_id,
                    page_key=page_key,
                    page_type=normalized_type,
                    subject_ref=compact_ref,
                    visibility_scope="server",
                    title=" ".join(title.split())[:320] or compact_ref,
                    body=body.strip()[:16000],
                    source_hash=source_hash[:64],
                    confidence=max(0.0, min(float(confidence), 1.0)),
                    created_at=current,
                    updated_at=current,
                )
                session.add(record)
            else:
                record.title = " ".join(title.split())[:320] or compact_ref
                record.body = body.strip()[:16000]
                record.source_hash = source_hash[:64]
                record.confidence = max(0.0, min(float(confidence), 1.0))
                record.stale = False
                record.updated_at = current
            record.keywords_json = _encode(keywords, limit=40)
            record.source_episode_ids_json = _encode(source_episode_ids, limit=120)
            record.source_entity_ids_json = _encode(source_entity_ids, limit=80)
            record.source_belief_ids_json = _encode(source_belief_ids, limit=120)
            record.source_evidence_edge_ids_json = _encode(source_evidence_edge_ids, limit=160)
            session.commit()
            session.refresh(record)
            return record

    def mark_subject_stale(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        page_type: str,
        subject_ref: str,
        now: datetime | None = None,
    ) -> int:
        current = now or datetime.now(UTC)
        page_key = f"{page_type.strip().casefold()}:{' '.join(subject_ref.split())[:320]}"[:220]
        with self.database.session() as session:
            record = session.scalar(
                select(ServerWikiPageV3Record).where(
                    ServerWikiPageV3Record.owner_id == owner_id,
                    ServerWikiPageV3Record.connection_id == connection_id,
                    ServerWikiPageV3Record.guild_id == guild_id,
                    ServerWikiPageV3Record.page_key == page_key,
                )
            )
            if record is None:
                return 0
            record.stale = True
            record.updated_at = current
            session.commit()
            return 1

    def lookup(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        query: str,
        limit: int = 6,
    ) -> tuple[dict[str, object], ...]:
        bounded = max(1, min(limit, 12))
        with self.database.session() as session:
            records = list(
                session.scalars(
                    select(ServerWikiPageV3Record)
                    .where(
                        ServerWikiPageV3Record.owner_id == owner_id,
                        ServerWikiPageV3Record.connection_id == connection_id,
                        ServerWikiPageV3Record.guild_id == guild_id,
                        ServerWikiPageV3Record.visibility_scope == "server",
                        ServerWikiPageV3Record.stale.is_(False),
                    )
                    .order_by(ServerWikiPageV3Record.updated_at.desc())
                    .limit(120)
                )
            )
        ranked = sorted(
            (
                (
                    _score(query, f"{item.title} {item.body} {item.keywords_json}"),
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
        return tuple(
            {
                "ref": item.id,
                "page_type": item.page_type,
                "subject_ref": item.subject_ref,
                "title": item.title,
                "body": item.body[:4000],
                "keywords": _decode(item.keywords_json)[:20],
                "confidence": round(item.confidence, 3),
                "source_episode_ids": _decode(item.source_episode_ids_json),
                "source_entity_ids": _decode(item.source_entity_ids_json),
                "source_belief_ids": _decode(item.source_belief_ids_json),
                "source_evidence_edge_ids": _decode(item.source_evidence_edge_ids_json),
                "updated_at": item.updated_at.isoformat(),
            }
            for item in selected
        )

    def delete_owner(self, owner_id: str) -> int:
        with self.database.session() as session:
            result = session.execute(
                delete(ServerWikiPageV3Record).where(ServerWikiPageV3Record.owner_id == owner_id)
            )
            session.commit()
            return int(getattr(result, "rowcount", 0) or 0)


class KnowledgeConsolidationCheckpointV3Repository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def save(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        source_ref_type: str,
        source_ref: str,
        source_hash: str,
        status: str,
        reason: str,
        source_count: int,
        wiki_page_id: str,
        utility_status: str,
        last_error: str = "",
        now: datetime | None = None,
    ) -> KnowledgeConsolidationCheckpointV3Record:
        if status not in {"pending", "completed", "partial", "failed"}:
            raise ValueError("Unsupported knowledge consolidation status.")
        current = now or datetime.now(UTC)
        with self.database.session() as session:
            record = session.scalar(
                select(KnowledgeConsolidationCheckpointV3Record).where(
                    KnowledgeConsolidationCheckpointV3Record.owner_id == owner_id,
                    KnowledgeConsolidationCheckpointV3Record.connection_id == connection_id,
                    KnowledgeConsolidationCheckpointV3Record.guild_id == guild_id,
                    KnowledgeConsolidationCheckpointV3Record.source_ref_type == source_ref_type,
                    KnowledgeConsolidationCheckpointV3Record.source_ref == source_ref,
                )
            )
            if record is None:
                record = KnowledgeConsolidationCheckpointV3Record(
                    id=str(uuid4()),
                    owner_id=owner_id,
                    connection_id=connection_id,
                    guild_id=guild_id,
                    source_ref_type=source_ref_type[:32],
                    source_ref=source_ref[:320],
                    created_at=current,
                )
                session.add(record)
            record.source_hash = source_hash[:64]
            record.status = status
            record.reason = reason[:120]
            record.source_count = max(0, source_count)
            record.wiki_page_id = wiki_page_id[:64]
            record.utility_status = utility_status[:48]
            record.last_error = last_error[:1200]
            record.updated_at = current
            record.completed_at = current if status == "completed" else None
            session.commit()
            session.refresh(record)
            return record


__all__ = ["KnowledgeConsolidationCheckpointV3Repository", "ServerWikiV3Repository"]
