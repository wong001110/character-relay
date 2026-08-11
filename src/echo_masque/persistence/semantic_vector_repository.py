"""Owner-scoped cache for reusable semantic embeddings."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from uuid import uuid4

from sqlalchemy import delete, select

from echo_masque.persistence.database import Database
from echo_masque.persistence.semantic_vector_models import SemanticVectorRecord
from echo_masque.semantic_participation import _deserialize_vector, _serialize_vector


class SemanticVectorRepository:
    """Persist small runtime embeddings without requiring a vector database."""

    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def source_hash(text: str, model_name: str, dimension: int) -> str:
        payload = "\n".join((model_name, str(dimension), text))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def get(
        self,
        *,
        owner_id: str,
        namespace: str,
        resource_id: str,
        model_name: str,
        dimension: int,
        source_hash: str,
    ) -> list[float] | None:
        with self.database.session() as session:
            record = session.scalar(
                select(SemanticVectorRecord).where(
                    SemanticVectorRecord.owner_id == owner_id,
                    SemanticVectorRecord.namespace == namespace,
                    SemanticVectorRecord.resource_id == resource_id,
                )
            )
            if record is None:
                return None
            if (
                record.model_name != model_name
                or record.dimension != dimension
                or record.source_hash != source_hash
            ):
                return None
            try:
                return _deserialize_vector(record.embedding_blob, record.dimension)
            except ValueError:
                return None

    def upsert(
        self,
        *,
        owner_id: str,
        namespace: str,
        resource_id: str,
        semantic_text: str,
        model_name: str,
        dimension: int,
        vector: Sequence[float],
    ) -> None:
        source_hash = self.source_hash(semantic_text, model_name, dimension)
        with self.database.session() as session:
            record = session.scalar(
                select(SemanticVectorRecord).where(
                    SemanticVectorRecord.owner_id == owner_id,
                    SemanticVectorRecord.namespace == namespace,
                    SemanticVectorRecord.resource_id == resource_id,
                )
            )
            if record is None:
                record = SemanticVectorRecord(
                    id=str(uuid4()),
                    owner_id=owner_id,
                    namespace=namespace,
                    resource_id=resource_id,
                    source_hash=source_hash,
                    semantic_text=semantic_text,
                    model_name=model_name,
                    dimension=dimension,
                    embedding_blob=_serialize_vector(vector),
                )
                session.add(record)
            else:
                record.source_hash = source_hash
                record.semantic_text = semantic_text
                record.model_name = model_name
                record.dimension = dimension
                record.embedding_blob = _serialize_vector(vector)
            session.commit()

    def delete_resource(self, *, owner_id: str, namespace: str, resource_id: str) -> int:
        with self.database.session() as session:
            result = session.execute(
                delete(SemanticVectorRecord).where(
                    SemanticVectorRecord.owner_id == owner_id,
                    SemanticVectorRecord.namespace == namespace,
                    SemanticVectorRecord.resource_id == resource_id,
                )
            )
            session.commit()
            return int(getattr(result, "rowcount", 0) or 0)

    def delete_namespace(self, *, owner_id: str, namespace: str) -> int:
        with self.database.session() as session:
            result = session.execute(
                delete(SemanticVectorRecord).where(
                    SemanticVectorRecord.owner_id == owner_id,
                    SemanticVectorRecord.namespace == namespace,
                )
            )
            session.commit()
            return int(getattr(result, "rowcount", 0) or 0)

    def delete_owner(self, owner_id: str) -> int:
        with self.database.session() as session:
            result = session.execute(
                delete(SemanticVectorRecord).where(SemanticVectorRecord.owner_id == owner_id)
            )
            session.commit()
            return int(getattr(result, "rowcount", 0) or 0)
