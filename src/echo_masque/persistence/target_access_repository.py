"""Owner-scoped access records for reusable target configurations."""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import exists, or_, select

from echo_masque.persistence.database import Database
from echo_masque.persistence.models import (
    CharacterCardRecord,
    TargetOwnershipRecord,
    TargetRecord,
)


class TargetAccessRepository:
    """Keep target configuration visibility aligned with workspace ownership."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def assign(self, *, owner_id: str, target_id: str) -> TargetOwnershipRecord:
        with self.database.session() as session:
            existing = session.scalar(
                select(TargetOwnershipRecord).where(
                    TargetOwnershipRecord.target_id == target_id,
                    TargetOwnershipRecord.owner_id == owner_id,
                )
            )
            if existing is not None:
                return existing
            record = TargetOwnershipRecord(
                id=str(uuid4()),
                target_id=target_id,
                owner_id=owner_id,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def can_access(self, *, owner_id: str, target_id: str) -> bool:
        if target_id.startswith("demo-"):
            return True
        with self.database.session() as session:
            owned = session.scalar(
                select(TargetOwnershipRecord.id).where(
                    TargetOwnershipRecord.target_id == target_id,
                    TargetOwnershipRecord.owner_id == owner_id,
                )
            )
            if owned is not None:
                return True
            legacy_card = session.scalar(
                select(CharacterCardRecord.id).where(
                    CharacterCardRecord.target_id == target_id,
                    CharacterCardRecord.owner_id == owner_id,
                )
            )
            return legacy_card is not None

    def list_visible(self, owner_id: str | None) -> list[TargetRecord]:
        if owner_id is None:
            with self.database.session() as session:
                query = (
                    select(TargetRecord)
                    .where(TargetRecord.id.like("demo-%"))
                    .order_by(TargetRecord.created_at)
                )
                return list(session.scalars(query))

        ownership = exists().where(
            TargetOwnershipRecord.target_id == TargetRecord.id,
            TargetOwnershipRecord.owner_id == owner_id,
        )
        legacy_card = exists().where(
            CharacterCardRecord.target_id == TargetRecord.id,
            CharacterCardRecord.owner_id == owner_id,
        )
        with self.database.session() as session:
            query = (
                select(TargetRecord)
                .where(
                    or_(
                        TargetRecord.id.like("demo-%"),
                        ownership,
                        legacy_card,
                    )
                )
                .order_by(TargetRecord.created_at)
            )
            return list(session.scalars(query))

    def remove(self, *, owner_id: str, target_id: str) -> None:
        with self.database.session() as session:
            record = session.scalar(
                select(TargetOwnershipRecord).where(
                    TargetOwnershipRecord.target_id == target_id,
                    TargetOwnershipRecord.owner_id == owner_id,
                )
            )
            if record is None:
                return
            session.delete(record)
            session.commit()
