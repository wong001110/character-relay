"""Persistence and deterministic retrieval for Character Relay RAG knowledge."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, cast
from uuid import uuid4

from sqlalchemy import delete, select, update
from sqlalchemy.engine import CursorResult

from echo_masque.knowledge_retrieval import (
    KnowledgeCandidate,
    KnowledgeResource,
    rank_knowledge_resources,
)
from echo_masque.persistence.database import Database
from echo_masque.persistence.knowledge_models import (
    KnowledgeBaseRecord,
    KnowledgeChunkRecord,
    KnowledgeDocumentRecord,
)
from echo_masque.persistence.models import CharacterCardRecord


@dataclass(frozen=True, slots=True)
class KnowledgeRetrievalResult:
    eligible_base_count: int
    candidate_chunk_count: int
    candidates: tuple[KnowledgeCandidate, ...]


def _cursor_rowcount(result: object) -> int:
    return cast(CursorResult[Any], result).rowcount or 0


def _normalize_content(value: str) -> str:
    return "\n".join(line.rstrip() for line in value.replace("\r\n", "\n").split("\n")).strip()


def chunk_document(
    content: str,
    *,
    max_chars: int = 900,
    overlap_chars: int = 120,
) -> list[str]:
    """Split text deterministically while retaining modest local overlap."""

    normalized = _normalize_content(content)
    if not normalized:
        return []
    max_chars = max(200, min(max_chars, 2000))
    overlap_chars = max(0, min(overlap_chars, max_chars // 3))

    paragraphs = [item.strip() for item in normalized.split("\n\n") if item.strip()]
    chunks: list[str] = []
    current = ""

    def flush() -> None:
        nonlocal current
        if current.strip():
            chunks.append(current.strip())
        current = ""

    for paragraph in paragraphs:
        if len(paragraph) > max_chars:
            flush()
            step = max_chars - overlap_chars
            for start in range(0, len(paragraph), step):
                piece = paragraph[start : start + max_chars].strip()
                if piece:
                    chunks.append(piece)
                if start + max_chars >= len(paragraph):
                    break
            continue
        candidate = paragraph if not current else f"{current}\n\n{paragraph}"
        if len(candidate) <= max_chars:
            current = candidate
            continue
        previous_tail = current[-overlap_chars:].strip() if overlap_chars else ""
        flush()
        current = f"{previous_tail}\n\n{paragraph}".strip() if previous_tail else paragraph
        if len(current) > max_chars:
            chunks.append(current[:max_chars].strip())
            current = current[max_chars - overlap_chars :].strip()
    flush()
    return list(dict.fromkeys(item for item in chunks if item))


class KnowledgeRepository:
    """Owner-scoped Knowledge Base CRUD plus RAG V1 sparse retrieval."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def _require_character(self, character_card_id: str, owner_id: str) -> None:
        if not character_card_id:
            return
        with self.database.session() as session:
            card = session.get(CharacterCardRecord, character_card_id)
            if card is None or card.owner_id != owner_id:
                raise KeyError("character")

    @staticmethod
    def _validate_scope(
        *,
        scope_type: str,
        connection_id: str,
        guild_id: str,
        channel_id: str,
        thread_id: str,
    ) -> None:
        if scope_type not in {"global", "server", "channel"}:
            raise ValueError("scope_type must be global, server, or channel.")
        if scope_type == "global":
            if any((connection_id, guild_id, channel_id, thread_id)):
                raise ValueError("Global knowledge cannot include Discord location filters.")
            return
        if not connection_id or not guild_id:
            raise ValueError("Server/channel knowledge requires connection_id and guild_id.")
        if scope_type == "server" and any((channel_id, thread_id)):
            raise ValueError("Server knowledge cannot include channel/thread filters.")
        if scope_type == "channel" and not channel_id:
            raise ValueError("Channel knowledge requires channel_id.")

    def create_base(
        self,
        *,
        owner_id: str,
        name: str,
        description: str,
        scope_type: str,
        connection_id: str = "",
        guild_id: str = "",
        channel_id: str = "",
        thread_id: str = "",
        character_card_id: str = "",
        enabled: bool = True,
    ) -> KnowledgeBaseRecord:
        values = {
            "name": name.strip(),
            "description": description.strip(),
            "scope_type": scope_type.strip(),
            "connection_id": connection_id.strip(),
            "guild_id": guild_id.strip(),
            "channel_id": channel_id.strip(),
            "thread_id": thread_id.strip(),
            "character_card_id": character_card_id.strip(),
        }
        if not values["name"]:
            raise ValueError("Knowledge Base name is required.")
        self._validate_scope(
            scope_type=values["scope_type"],
            connection_id=values["connection_id"],
            guild_id=values["guild_id"],
            channel_id=values["channel_id"],
            thread_id=values["thread_id"],
        )
        self._require_character(values["character_card_id"], owner_id)
        record = KnowledgeBaseRecord(
            id=str(uuid4()),
            owner_id=owner_id,
            enabled=enabled,
            **values,
        )
        with self.database.session() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def list_bases(self, owner_id: str) -> list[KnowledgeBaseRecord]:
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(KnowledgeBaseRecord)
                    .where(KnowledgeBaseRecord.owner_id == owner_id)
                    .order_by(KnowledgeBaseRecord.updated_at.desc())
                )
            )

    def get_base(self, base_id: str, owner_id: str) -> KnowledgeBaseRecord | None:
        with self.database.session() as session:
            record = session.get(KnowledgeBaseRecord, base_id)
            if record is None or record.owner_id != owner_id:
                return None
            return record

    def update_base(
        self,
        base_id: str,
        owner_id: str,
        *,
        name: str,
        description: str,
        scope_type: str,
        connection_id: str = "",
        guild_id: str = "",
        channel_id: str = "",
        thread_id: str = "",
        character_card_id: str = "",
        enabled: bool = True,
    ) -> KnowledgeBaseRecord:
        values = {
            "name": name.strip(),
            "description": description.strip(),
            "scope_type": scope_type.strip(),
            "connection_id": connection_id.strip(),
            "guild_id": guild_id.strip(),
            "channel_id": channel_id.strip(),
            "thread_id": thread_id.strip(),
            "character_card_id": character_card_id.strip(),
        }
        if not values["name"]:
            raise ValueError("Knowledge Base name is required.")
        self._validate_scope(
            scope_type=values["scope_type"],
            connection_id=values["connection_id"],
            guild_id=values["guild_id"],
            channel_id=values["channel_id"],
            thread_id=values["thread_id"],
        )
        self._require_character(values["character_card_id"], owner_id)
        with self.database.session() as session:
            record = session.get(KnowledgeBaseRecord, base_id)
            if record is None or record.owner_id != owner_id:
                raise KeyError("knowledge_base")
            for field, value in values.items():
                setattr(record, field, value)
            record.enabled = enabled
            session.commit()
            session.refresh(record)
            return record

    def delete_base(self, base_id: str, owner_id: str) -> bool:
        with self.database.session() as session:
            record = session.get(KnowledgeBaseRecord, base_id)
            if record is None or record.owner_id != owner_id:
                return False
            session.execute(
                delete(KnowledgeChunkRecord).where(
                    KnowledgeChunkRecord.owner_id == owner_id,
                    KnowledgeChunkRecord.knowledge_base_id == base_id,
                )
            )
            session.execute(
                delete(KnowledgeDocumentRecord).where(
                    KnowledgeDocumentRecord.owner_id == owner_id,
                    KnowledgeDocumentRecord.knowledge_base_id == base_id,
                )
            )
            session.delete(record)
            session.commit()
            return True

    def create_document(
        self,
        *,
        owner_id: str,
        knowledge_base_id: str,
        title: str,
        content: str,
    ) -> KnowledgeDocumentRecord:
        base = self.get_base(knowledge_base_id, owner_id)
        if base is None:
            raise KeyError("knowledge_base")
        normalized = _normalize_content(content)
        title = title.strip()
        if not title:
            raise ValueError("Document title is required.")
        if not normalized:
            raise ValueError("Document content is required.")
        if len(normalized) > 200_000:
            raise ValueError("Document content exceeds the RAG V1 200,000 character limit.")
        chunks = chunk_document(normalized)
        if not chunks:
            raise ValueError("Document did not produce any retrieval chunks.")
        record = KnowledgeDocumentRecord(
            id=str(uuid4()),
            owner_id=owner_id,
            knowledge_base_id=knowledge_base_id,
            title=title,
            content=normalized,
            content_sha256=hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
            chunk_count=len(chunks),
        )
        with self.database.session() as session:
            session.add(record)
            for index, chunk in enumerate(chunks):
                session.add(
                    KnowledgeChunkRecord(
                        id=str(uuid4()),
                        owner_id=owner_id,
                        knowledge_base_id=knowledge_base_id,
                        document_id=record.id,
                        document_title=title,
                        chunk_index=index,
                        content=chunk,
                        char_count=len(chunk),
                    )
                )
            session.commit()
            session.refresh(record)
            return record

    def list_documents(
        self,
        knowledge_base_id: str,
        owner_id: str,
    ) -> list[KnowledgeDocumentRecord]:
        if self.get_base(knowledge_base_id, owner_id) is None:
            raise KeyError("knowledge_base")
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(KnowledgeDocumentRecord)
                    .where(
                        KnowledgeDocumentRecord.owner_id == owner_id,
                        KnowledgeDocumentRecord.knowledge_base_id == knowledge_base_id,
                    )
                    .order_by(KnowledgeDocumentRecord.updated_at.desc())
                )
            )

    def delete_document(self, document_id: str, owner_id: str) -> bool:
        with self.database.session() as session:
            record = session.get(KnowledgeDocumentRecord, document_id)
            if record is None or record.owner_id != owner_id:
                return False
            session.execute(
                delete(KnowledgeChunkRecord).where(
                    KnowledgeChunkRecord.owner_id == owner_id,
                    KnowledgeChunkRecord.document_id == document_id,
                )
            )
            session.delete(record)
            session.commit()
            return True

    @staticmethod
    def _base_matches_turn(
        base: KnowledgeBaseRecord,
        *,
        connection_id: str,
        guild_id: str,
        channel_id: str,
        thread_id: str,
        character_card_id: str,
    ) -> bool:
        if not base.enabled:
            return False
        if base.character_card_id and base.character_card_id != character_card_id:
            return False
        if base.scope_type == "global":
            return True
        if base.connection_id != connection_id or base.guild_id != guild_id:
            return False
        if base.scope_type == "server":
            return True
        if base.channel_id != channel_id:
            return False
        return not base.thread_id or base.thread_id == thread_id

    def retrieve_for_turn(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        channel_id: str,
        thread_id: str,
        character_card_id: str,
        query: str,
        top_k: int = 4,
    ) -> KnowledgeRetrievalResult:
        if not query.strip():
            return KnowledgeRetrievalResult(0, 0, ())
        bases = self.list_bases(owner_id)
        eligible = [
            item
            for item in bases
            if self._base_matches_turn(
                item,
                connection_id=connection_id,
                guild_id=guild_id,
                channel_id=channel_id,
                thread_id=thread_id,
                character_card_id=character_card_id,
            )
        ]
        if not eligible:
            return KnowledgeRetrievalResult(0, 0, ())
        base_ids = [item.id for item in eligible]
        with self.database.session() as session:
            records = list(
                session.scalars(
                    select(KnowledgeChunkRecord)
                    .where(
                        KnowledgeChunkRecord.owner_id == owner_id,
                        KnowledgeChunkRecord.knowledge_base_id.in_(base_ids),
                    )
                    .order_by(
                        KnowledgeChunkRecord.document_id,
                        KnowledgeChunkRecord.chunk_index,
                    )
                    .limit(1000)
                )
            )
        resources = [
            KnowledgeResource(
                chunk_id=item.id,
                knowledge_base_id=item.knowledge_base_id,
                document_id=item.document_id,
                document_title=item.document_title,
                chunk_index=item.chunk_index,
                content=item.content,
            )
            for item in records
        ]
        ranked = rank_knowledge_resources(resources, query=query, top_k=top_k)
        return KnowledgeRetrievalResult(
            eligible_base_count=len(eligible),
            candidate_chunk_count=len(resources),
            candidates=tuple(ranked),
        )

    def delete_owner(self, owner_id: str) -> dict[str, int]:
        with self.database.session() as session:
            chunk_result = session.execute(
                delete(KnowledgeChunkRecord).where(KnowledgeChunkRecord.owner_id == owner_id)
            )
            document_result = session.execute(
                delete(KnowledgeDocumentRecord).where(KnowledgeDocumentRecord.owner_id == owner_id)
            )
            base_result = session.execute(
                delete(KnowledgeBaseRecord).where(KnowledgeBaseRecord.owner_id == owner_id)
            )
            session.commit()
            return {
                "knowledge_chunks": _cursor_rowcount(chunk_result),
                "knowledge_documents": _cursor_rowcount(document_result),
                "knowledge_bases": _cursor_rowcount(base_result),
            }

    def claim_owner(self, source_owner_id: str, target_owner_id: str) -> dict[str, int]:
        with self.database.session() as session:
            base_result = session.execute(
                update(KnowledgeBaseRecord)
                .where(KnowledgeBaseRecord.owner_id == source_owner_id)
                .values(owner_id=target_owner_id)
            )
            document_result = session.execute(
                update(KnowledgeDocumentRecord)
                .where(KnowledgeDocumentRecord.owner_id == source_owner_id)
                .values(owner_id=target_owner_id)
            )
            chunk_result = session.execute(
                update(KnowledgeChunkRecord)
                .where(KnowledgeChunkRecord.owner_id == source_owner_id)
                .values(owner_id=target_owner_id)
            )
            session.commit()
            return {
                "knowledge_bases": _cursor_rowcount(base_result),
                "knowledge_documents": _cursor_rowcount(document_result),
                "knowledge_chunks": _cursor_rowcount(chunk_result),
            }
