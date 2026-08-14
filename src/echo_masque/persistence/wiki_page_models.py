from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    delete,
    event,
    update,
)
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapped, Mapper, mapped_column

from echo_masque.persistence.models import Base, utcnow


class WikiPageRecord(Base):
    __tablename__ = "knowledge_wiki_pages"
    __table_args__ = (
        UniqueConstraint(
            "knowledge_base_id",
            "page_key",
            name="uq_knowledge_wiki_base_page_key",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    knowledge_base_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    page_key: Mapped[str] = mapped_column(String(160), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    keywords_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    source_manifest_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.7, nullable=False)
    stale: Mapped[bool] = mapped_column(Boolean, default=False, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


def _mark_base_stale(
    connection: Connection,
    *,
    owner_id: str,
    knowledge_base_id: str,
) -> None:
    connection.execute(
        update(WikiPageRecord)
        .where(
            WikiPageRecord.owner_id == owner_id,
            WikiPageRecord.knowledge_base_id == knowledge_base_id,
            WikiPageRecord.stale.is_(False),
        )
        .values(stale=True, updated_at=utcnow())
    )


# Imported after WikiPageRecord is defined so the relationship can be registered in either
# module-import order without creating a circular class-definition dependency.
from echo_masque.persistence.knowledge_models import (  # noqa: E402
    KnowledgeBaseRecord,
    KnowledgeDocumentRecord,
)


@event.listens_for(KnowledgeDocumentRecord, "after_insert")
@event.listens_for(KnowledgeDocumentRecord, "after_update")
@event.listens_for(KnowledgeDocumentRecord, "after_delete")
def _stale_wiki_after_document_change(
    _mapper: Mapper[Any],
    connection: Connection,
    target: KnowledgeDocumentRecord,
) -> None:
    _mark_base_stale(
        connection,
        owner_id=target.owner_id,
        knowledge_base_id=target.knowledge_base_id,
    )


@event.listens_for(KnowledgeBaseRecord, "after_update")
def _stale_wiki_after_base_change(
    _mapper: Mapper[Any],
    connection: Connection,
    target: KnowledgeBaseRecord,
) -> None:
    _mark_base_stale(
        connection,
        owner_id=target.owner_id,
        knowledge_base_id=target.id,
    )


@event.listens_for(KnowledgeBaseRecord, "after_delete")
def _delete_wiki_after_base_delete(
    _mapper: Mapper[Any],
    connection: Connection,
    target: KnowledgeBaseRecord,
) -> None:
    connection.execute(
        delete(WikiPageRecord).where(
            WikiPageRecord.knowledge_base_id == target.id,
        )
    )


__all__ = ["WikiPageRecord"]
