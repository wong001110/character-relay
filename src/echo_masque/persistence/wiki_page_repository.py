"""Persistence for derived Knowledge Wiki pages."""

from __future__ import annotations

import json
from typing import Any, cast
from uuid import uuid4

from sqlalchemy import delete, select, update
from sqlalchemy.engine import CursorResult

from echo_masque.persistence.database import Database
from echo_masque.persistence.models import utcnow
from echo_masque.persistence.wiki_page_models import WikiPageRecord


def _cursor_rowcount(result: object) -> int:
    return cast(CursorResult[Any], result).rowcount or 0


class WikiPageRepository:
    """Owner-scoped storage for derived Wiki pages."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def get_page(
        self,
        *,
        owner_id: str,
        knowledge_base_id: str,
        page_key: str,
    ) -> WikiPageRecord | None:
        with self.database.session() as session:
            return session.scalar(
                select(WikiPageRecord).where(
                    WikiPageRecord.owner_id == owner_id,
                    WikiPageRecord.knowledge_base_id == knowledge_base_id,
                    WikiPageRecord.page_key == page_key.strip(),
                )
            )

    def list_pages(
        self,
        *,
        owner_id: str,
        knowledge_base_id: str,
        include_stale: bool = False,
    ) -> list[WikiPageRecord]:
        conditions = [
            WikiPageRecord.owner_id == owner_id,
            WikiPageRecord.knowledge_base_id == knowledge_base_id,
        ]
        if not include_stale:
            conditions.append(WikiPageRecord.stale.is_(False))
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(WikiPageRecord)
                    .where(*conditions)
                    .order_by(WikiPageRecord.updated_at.desc(), WikiPageRecord.page_key)
                )
            )

    def upsert_page(
        self,
        *,
        owner_id: str,
        knowledge_base_id: str,
        page_key: str,
        title: str,
        body: str,
        keywords: tuple[str, ...] | list[str],
        source_manifest: tuple[dict[str, str], ...] | list[dict[str, str]],
        source_hash: str,
        confidence: float,
    ) -> WikiPageRecord:
        page_key = page_key.strip()
        title = title.strip()
        body = body.strip()
        if not page_key:
            raise ValueError("Wiki page_key is required.")
        if not title:
            raise ValueError("Wiki title is required.")
        if not body:
            raise ValueError("Wiki body is required.")
        if len(source_hash) != 64:
            raise ValueError("Wiki source_hash must be a SHA-256 hex digest.")

        keywords_json = json.dumps(
            list(dict.fromkeys(item.strip() for item in keywords if item.strip()))[:24],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        source_manifest_json = json.dumps(
            list(source_manifest),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        with self.database.session() as session:
            record = session.scalar(
                select(WikiPageRecord).where(
                    WikiPageRecord.owner_id == owner_id,
                    WikiPageRecord.knowledge_base_id == knowledge_base_id,
                    WikiPageRecord.page_key == page_key,
                )
            )
            if record is None:
                record = WikiPageRecord(
                    id=str(uuid4()),
                    owner_id=owner_id,
                    knowledge_base_id=knowledge_base_id,
                    page_key=page_key,
                    title=title,
                    body=body,
                    keywords_json=keywords_json,
                    source_manifest_json=source_manifest_json,
                    source_hash=source_hash,
                    confidence=max(0.0, min(float(confidence), 1.0)),
                    stale=False,
                )
                session.add(record)
            else:
                record.title = title
                record.body = body
                record.keywords_json = keywords_json
                record.source_manifest_json = source_manifest_json
                record.source_hash = source_hash
                record.confidence = max(0.0, min(float(confidence), 1.0))
                record.stale = False
                record.updated_at = utcnow()
            session.commit()
            session.refresh(record)
            return record

    def mark_base_stale(self, *, owner_id: str, knowledge_base_id: str) -> int:
        with self.database.session() as session:
            result = session.execute(
                update(WikiPageRecord)
                .where(
                    WikiPageRecord.owner_id == owner_id,
                    WikiPageRecord.knowledge_base_id == knowledge_base_id,
                    WikiPageRecord.stale.is_(False),
                )
                .values(stale=True, updated_at=utcnow())
            )
            session.commit()
            return _cursor_rowcount(result)

    def delete_base(self, *, owner_id: str, knowledge_base_id: str) -> int:
        with self.database.session() as session:
            result = session.execute(
                delete(WikiPageRecord).where(
                    WikiPageRecord.owner_id == owner_id,
                    WikiPageRecord.knowledge_base_id == knowledge_base_id,
                )
            )
            session.commit()
            return _cursor_rowcount(result)

    def delete_owner(self, owner_id: str) -> int:
        with self.database.session() as session:
            result = session.execute(
                delete(WikiPageRecord).where(WikiPageRecord.owner_id == owner_id)
            )
            session.commit()
            return _cursor_rowcount(result)

    def claim_owner(self, source_owner_id: str, target_owner_id: str) -> int:
        with self.database.session() as session:
            result = session.execute(
                update(WikiPageRecord)
                .where(WikiPageRecord.owner_id == source_owner_id)
                .values(owner_id=target_owner_id, updated_at=utcnow())
            )
            session.commit()
            return _cursor_rowcount(result)


__all__ = ["WikiPageRepository"]
