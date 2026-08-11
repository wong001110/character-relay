"""Persistence and hybrid retrieval for Character Relay RAG knowledge."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, cast
from uuid import uuid4

from sqlalchemy import delete, select, update
from sqlalchemy.engine import CursorResult

from echo_masque.config import get_settings
from echo_masque.knowledge_retrieval import (
    KnowledgeCandidate,
    KnowledgeResource,
    rank_knowledge_resources,
    score_sparse_knowledge_resources,
)
from echo_masque.persistence.database import Database
from echo_masque.persistence.knowledge_models import (
    KnowledgeBaseRecord,
    KnowledgeChunkRecord,
    KnowledgeDocumentRecord,
)
from echo_masque.persistence.models import CharacterCardRecord
from echo_masque.persistence.semantic_vector_repository import SemanticVectorRepository
from echo_masque.semantic_participation import (
    FastEmbedSemanticEncoder,
    SemanticEmbeddingUnavailable,
    SemanticEncoder,
    _cosine as dense_cosine,
)

_KNOWLEDGE_VECTOR_NAMESPACE = "knowledge-chunk"
_DENSE_FLOOR = 0.35
_HYBRID_MINIMUM = 0.12


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
    """Owner-scoped Knowledge Base CRUD plus sparse+dense hybrid RAG retrieval."""

    def __init__(
        self,
        database: Database,
        *,
        semantic_encoder: SemanticEncoder | None = None,
        semantic_enabled: bool | None = None,
    ) -> None:
        self.database = database
        settings = get_settings()
        self._settings = settings
        self._semantic_encoder = semantic_encoder
        self._semantic_enabled = (
            semantic_enabled
            if semantic_enabled is not None
            else (
                settings.semantic_embedding_runtime_enabled
                and settings.knowledge_semantic_retrieval_enabled
            )
        )
        self._semantic_vectors = SemanticVectorRepository(database)

    def _encoder(self) -> SemanticEncoder:
        if self._semantic_encoder is None:
            if not self._semantic_enabled:
                raise SemanticEmbeddingUnavailable("Semantic Knowledge retrieval is disabled.")
            self._semantic_encoder = FastEmbedSemanticEncoder(
                model_name=self._settings.semantic_embedding_model,
                model_file=self._settings.semantic_embedding_model_file,
                cache_dir=self._settings.semantic_embedding_cache_dir,
                dimension=self._settings.semantic_embedding_dimension,
            )
        return self._semantic_encoder

    @staticmethod
    def _resource_semantic_text(resource: KnowledgeResource) -> str:
        return f"Title: {resource.document_title}\n{resource.content}"[:20_000]

    def _ensure_resource_vector(self, owner_id: str, resource: KnowledgeResource) -> list[float]:
        encoder = self._encoder()
        semantic_text = self._resource_semantic_text(resource)
        source_hash = self._semantic_vectors.source_hash(
            semantic_text,
            encoder.model_name,
            encoder.dimension,
        )
        cached = self._semantic_vectors.get(
            owner_id=owner_id,
            namespace=_KNOWLEDGE_VECTOR_NAMESPACE,
            resource_id=resource.chunk_id,
            model_name=encoder.model_name,
            dimension=encoder.dimension,
            source_hash=source_hash,
        )
        if cached is not None:
            return cached
        vector = encoder.embed_passage(semantic_text)
        self._semantic_vectors.upsert(
            owner_id=owner_id,
            namespace=_KNOWLEDGE_VECTOR_NAMESPACE,
            resource_id=resource.chunk_id,
            semantic_text=semantic_text,
            model_name=encoder.model_name,
            dimension=encoder.dimension,
            vector=vector,
        )
        return vector

    def _hybrid_rank(
        self,
        *,
        owner_id: str,
        resources: list[KnowledgeResource],
        query: str,
        top_k: int,
    ) -> list[KnowledgeCandidate]:
        if not self._semantic_enabled:
            return rank_knowledge_resources(resources, query=query, top_k=top_k)
        sparse = score_sparse_knowledge_resources(resources, query=query)
        if not sparse:
            return []
        try:
            encoder = self._encoder()
            query_vector = encoder.embed_query(query)
        except (SemanticEmbeddingUnavailable, ValueError, RuntimeError):
            return rank_knowledge_resources(resources, query=query, top_k=top_k)

        ranked: list[KnowledgeCandidate] = []
        dense_count = 0
        for candidate in sparse:
            try:
                vector = self._ensure_resource_vector(owner_id, candidate.resource)
            except (SemanticEmbeddingUnavailable, ValueError, RuntimeError):
                continue
            dense_raw = dense_cosine(query_vector, vector)
            dense_count += 1
            dense_normalized = max(
                0.0,
                min(1.0, (dense_raw - _DENSE_FLOOR) / (1.0 - _DENSE_FLOOR)),
            )
            exact = candidate.signals.get("exact", 0.0)
            hybrid = round(
                dense_normalized * 0.68 + candidate.score * 0.27 + exact * 0.05,
                6,
            )
            if hybrid < _HYBRID_MINIMUM:
                continue
            ranked.append(
                KnowledgeCandidate(
                    resource=candidate.resource,
                    score=hybrid,
                    signals={
                        **candidate.signals,
                        "sparse": candidate.score,
                        "dense": round(dense_raw, 6),
                        "dense_normalized": round(dense_normalized, 6),
                    },
                )
            )
        if dense_count == 0:
            return rank_knowledge_resources(resources, query=query, top_k=top_k)
        ranked.sort(
            key=lambda item: (
                -item.score,
                -item.signals.get("dense", 0.0),
                item.resource.document_title.casefold(),
                item.resource.chunk_index,
                item.resource.chunk_id,
            )
        )
        return ranked[: max(1, min(top_k, 8))]

    def _delete_chunk_vectors(self, owner_id: str, chunk_ids: list[str]) -> None:
        for chunk_id in chunk_ids:
            self._semantic_vectors.delete_resource(
                owner_id=owner_id,
                namespace=_KNOWLEDGE_VECTOR_NAMESPACE,
                resource_id=chunk_id,
            )

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
            chunk_ids = list(
                session.scalars(
                    select(KnowledgeChunkRecord.id).where(
                        KnowledgeChunkRecord.owner_id == owner_id,
                        KnowledgeChunkRecord.knowledge_base_id == base_id,
                    )
                )
            )
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
        self._delete_chunk_vectors(owner_id, chunk_ids)
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
            chunk_ids = list(
                session.scalars(
                    select(KnowledgeChunkRecord.id).where(
                        KnowledgeChunkRecord.owner_id == owner_id,
                        KnowledgeChunkRecord.document_id == document_id,
                    )
                )
            )
            session.execute(
                delete(KnowledgeChunkRecord).where(
                    KnowledgeChunkRecord.owner_id == owner_id,
                    KnowledgeChunkRecord.document_id == document_id,
                )
            )
            session.delete(record)
            session.commit()
        self._delete_chunk_vectors(owner_id, chunk_ids)
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
        ranked = self._hybrid_rank(
            owner_id=owner_id,
            resources=resources,
            query=query,
            top_k=top_k,
        )
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
            result = {
                "knowledge_chunks": _cursor_rowcount(chunk_result),
                "knowledge_documents": _cursor_rowcount(document_result),
                "knowledge_bases": _cursor_rowcount(base_result),
            }
        self._semantic_vectors.delete_namespace(
            owner_id=owner_id,
            namespace=_KNOWLEDGE_VECTOR_NAMESPACE,
        )
        return result

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
            result = {
                "knowledge_bases": _cursor_rowcount(base_result),
                "knowledge_documents": _cursor_rowcount(document_result),
                "knowledge_chunks": _cursor_rowcount(chunk_result),
            }
        # Vectors are a cache. Drop the old owner-scoped copies and lazily rebuild them for
        # the claimed owner rather than coupling account migration to vector persistence.
        self._semantic_vectors.delete_namespace(
            owner_id=source_owner_id,
            namespace=_KNOWLEDGE_VECTOR_NAMESPACE,
        )
        return result
