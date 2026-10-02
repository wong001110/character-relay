"""Account lifecycle for the small room/notes runtime, without cognitive graph state."""

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from echo_masque.account_lifecycle import LifecycleConflict
from echo_masque.persistence.database import Database
from echo_masque.persistence.expression_models import ExpressionUsageRecord
from echo_masque.persistence.note_models import CharacterNoteRecord, NoteCreationReceiptRecord
from echo_masque.persistence.pending_action_models import PendingActionRecord
from echo_masque.persistence.room_models import (
    RoomDeliverySourceRecord,
    RoomRouteRecord,
    RoomSelectionRecord,
    RoomSourceRecord,
    RoomStateRecord,
)
from echo_masque.room_routing import RoomScope
from echo_masque.room_sources import scope_key


class ChatLifecycleRepository:
    """Delete only verified owner scopes. Legacy authoring claims cannot transfer effects."""

    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def _scope_ids(session: Session, owner_id: str) -> list[str]:
        result: list[str] = []
        for record in session.scalars(select(RoomStateRecord)):
            scope = RoomScope.model_validate_json(record.scope_json)
            if scope.owner_id == owner_id:
                if scope_key(scope) != record.id:
                    raise LifecycleConflict("Room scope integrity requires offline repair.")
                result.append(record.id)
        return result

    def delete_owner(self, owner_id: str) -> dict[str, int]:
        with self.database.session() as session:
            scopes = self._scope_ids(session, owner_id)
            counts: dict[str, int] = {}
            for model in (RoomSourceRecord, RoomSelectionRecord, RoomRouteRecord):
                rows = list(session.scalars(select(model).where(model.scope_id.in_(scopes))))
                counts[model.__tablename__] = len(rows)
                for row in rows:
                    session.delete(row)
            counts[RoomStateRecord.__tablename__] = len(scopes)
            session.execute(delete(RoomStateRecord).where(RoomStateRecord.id.in_(scopes)))
            for owned_model in (
                CharacterNoteRecord,
                NoteCreationReceiptRecord,
                PendingActionRecord,
                ExpressionUsageRecord,
                RoomDeliverySourceRecord,
            ):
                owned = list(
                    session.scalars(select(owned_model).where(owned_model.owner_id == owner_id))
                )
                counts[owned_model.__tablename__] = len(owned)
                for row in owned:
                    session.delete(row)
            session.commit()
            return counts

    def assert_claimable(self, owner_id: str) -> None:
        """Preflight before ANY account service mutates local workspace ownership."""
        with self.database.session() as session:
            if self._scope_ids(session, owner_id):
                raise LifecycleConflict(
                    "Scoped chat state cannot change owner. Export authored content and "
                    "perform an explicit offline chat reset before claiming the workspace."
                )
            if session.scalar(
                select(PendingActionRecord.id)
                .where(PendingActionRecord.owner_id == owner_id)
                .limit(1)
            ) or session.scalar(
                select(CharacterNoteRecord.id)
                .where(
                    CharacterNoteRecord.owner_id == owner_id,
                    (CharacterNoteRecord.scope_id != "")
                    | (CharacterNoteRecord.authored.is_(False)),
                )
                .limit(1)
            ):
                raise LifecycleConflict("Scoped notes or pending effects require an offline reset.")

    def claim_authored_notes(self, owner_id: str, new_owner_id: str) -> dict[str, int]:
        self.assert_claimable(owner_id)
        with self.database.session() as session:
            ids = list(
                session.scalars(
                    select(CharacterNoteRecord.id).where(
                        CharacterNoteRecord.owner_id == owner_id,
                        CharacterNoteRecord.scope_id == "",
                        CharacterNoteRecord.authored.is_(True),
                    )
                )
            )
            session.execute(
                update(CharacterNoteRecord)
                .where(CharacterNoteRecord.id.in_(ids))
                .values(owner_id=new_owner_id, actor_id=new_owner_id)
            )
            session.commit()
            return {"character_notes": len(ids)}
