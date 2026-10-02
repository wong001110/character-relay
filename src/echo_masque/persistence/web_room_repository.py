"""Web transport authorization and delivery transactions, using existing room evidence."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from threading import RLock
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from echo_masque.persistence.database import Database
from echo_masque.persistence.deployment_models import (
    DiscordServerCatalogRecord,
    PlatformConnectionRecord,
)
from echo_masque.persistence.models import UserRecord
from echo_masque.persistence.expression_models import DiscordExpressionSemanticRecord
from echo_masque.persistence.room_repository import RoomRepository
from echo_masque.persistence.server_access_models import DiscordServerAccessRecord
from echo_masque.persistence.web_room_models import (
    WebOutboxRecord,
    WebProfileRecord,
    WebReactionRecord,
    WebRoomMemberRecord,
    WebRoomRecord,
)
from echo_masque.web_rooms import (
    ProfileInput,
    ProfileView,
    WebDeliveryView,
    WebExpressionView,
    WebReactionInput,
    WebRoomDelivery,
    WebRoomError,
    WebRoomInput,
    WebRoomView,
    WebSend,
    room_scope,
)

# SQLite's dev/test writer is serialized; PostgreSQL also locks the destination row in SQL.
_LOCKS: dict[object, RLock] = {}
_GUARD = RLock()


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _profile(record: WebProfileRecord) -> ProfileView:
    return ProfileView(
        id=record.id,
        display_name=record.display_name,
        avatar_url=record.avatar_url,
        version=record.version,
    )


def delivery_view(record: WebOutboxRecord) -> WebDeliveryView:
    payload = json.loads(record.payload_json)
    return WebDeliveryView.model_validate(
        {
            **payload,
            "id": record.id,
            "client_message_id": record.client_message_id,
            "profile_id": record.profile_id,
            "status": record.status,
            "discord_message_id": record.discord_message_id,
            "reason": record.reason,
            "created_at": _aware(record.created_at),
            "routing_status": record.routing_status,
        }
    )


def _expression(
    session: Session,
    room: WebRoomRecord,
    resource_key: str,
    *,
    resource_type: str | None = None,
) -> DiscordExpressionSemanticRecord | None:
    kind, separator, resource_id = resource_key.partition(":")
    if not separator or kind not in {"emoji", "sticker"} or not resource_id:
        return None
    if resource_type is not None and kind != resource_type:
        return None
    return session.scalar(
        select(DiscordExpressionSemanticRecord).where(
            DiscordExpressionSemanticRecord.owner_id == room.owner_id,
            DiscordExpressionSemanticRecord.connection_id == room.connection_id,
            DiscordExpressionSemanticRecord.guild_id == room.guild_id,
            DiscordExpressionSemanticRecord.resource_type == kind,
            DiscordExpressionSemanticRecord.resource_id == resource_id,
            DiscordExpressionSemanticRecord.available.is_(True),
            DiscordExpressionSemanticRecord.enabled.is_(True),
        )
    )


class WebRoomRepository:
    def __init__(self, database: Database) -> None:
        self.database = database
        self.sources = RoomRepository(database)
        with _GUARD:
            self.lock = _LOCKS.setdefault(database.engine, RLock())

    @staticmethod
    def _server_access(session: Session, room: WebRoomRecord, user_id: str) -> bool:
        user = session.get(UserRecord, user_id)
        connection = session.get(PlatformConnectionRecord, room.connection_id)
        if (
            user is None
            or not user.is_active
            or connection is None
            or connection.owner_id != room.owner_id
        ):
            return False
        return (
            room.owner_id == user_id
            or session.scalar(
                select(DiscordServerAccessRecord.id).where(
                    DiscordServerAccessRecord.user_id == user_id,
                    DiscordServerAccessRecord.connection_id == room.connection_id,
                    DiscordServerAccessRecord.guild_id == room.guild_id,
                )
            )
            is not None
        )

    @classmethod
    def _access(
        cls, session: Session, room: WebRoomRecord, user_id: str, *, post: bool = False
    ) -> bool:
        if not room.enabled or not cls._server_access(session, room, user_id):
            return False
        if room.owner_id == user_id:
            return True
        member = session.get(WebRoomMemberRecord, _hash([room.id, user_id]))
        return member is not None and (not post or member.can_post)

    def require(
        self, room_id: str, user_id: str, *, post: bool = False, fresh: bool = False
    ) -> WebRoomRecord:
        with self.database.session() as session:
            room = session.get(WebRoomRecord, room_id)
            if room is None or not self._access(session, room, user_id, post=post):
                raise WebRoomError("room_unavailable", 404)
        if fresh and not self.sources.can_read(room_scope(room), max_age_seconds=90):
            raise WebRoomError("room_connection_unavailable", 503)
        return room

    def list_rooms(self, user_id: str) -> list[WebRoomView]:
        with self.database.session() as session:
            rows = session.scalars(
                select(WebRoomRecord)
                .where(
                    (WebRoomRecord.owner_id == user_id)
                    | WebRoomRecord.id.in_(
                        select(WebRoomMemberRecord.room_id).where(
                            WebRoomMemberRecord.user_id == user_id
                        )
                    )
                )
                .order_by(WebRoomRecord.name)
                .limit(256)
            ).all()
            return [
                WebRoomView(
                    id=row.id,
                    name=row.name,
                    connection_id=row.connection_id,
                    guild_id=row.guild_id,
                    channel_id=row.channel_id,
                    thread_id=row.thread_id,
                    enabled=row.enabled,
                    can_manage=row.owner_id == user_id,
                    can_post=self._access(session, row, user_id, post=True),
                )
                for row in rows
                if self._access(session, row, user_id)
                or (row.owner_id == user_id and self._server_access(session, row, user_id))
            ]

    def publish(self, user_id: str, payload: WebRoomInput) -> str:
        with self.lock, self.database.session() as session:
            connection = session.scalar(
                select(PlatformConnectionRecord)
                .where(PlatformConnectionRecord.id == payload.connection_id)
                .with_for_update()
            )
            if (
                connection is None
                or connection.owner_id != user_id
                or connection.platform != "discord"
            ):
                raise WebRoomError("connection_unavailable", 404)
            catalog = session.scalar(
                select(DiscordServerCatalogRecord).where(
                    DiscordServerCatalogRecord.connection_id == connection.id,
                    DiscordServerCatalogRecord.guild_id == payload.guild_id,
                    DiscordServerCatalogRecord.owner_id == user_id,
                )
            )
            if catalog is None or not any(
                c.get("id") == payload.channel_id for c in json.loads(catalog.channels_json)
            ):
                raise WebRoomError("channel_not_in_catalog", 422)
            room_id = _hash(
                [payload.connection_id, payload.guild_id, payload.channel_id, payload.thread_id]
            )
            existing = session.get(WebRoomRecord, room_id)
            if existing is not None:
                if existing.owner_id != user_id:
                    raise WebRoomError("room_unavailable", 404)
                return existing.id
            if (
                session.scalar(
                    select(func.count())
                    .select_from(WebRoomRecord)
                    .where(WebRoomRecord.connection_id == connection.id)
                )
                or 0
            ) >= 16:
                raise WebRoomError("published_room_limit", 429)
            session.add(WebRoomRecord(id=room_id, owner_id=user_id, **payload.model_dump()))
            session.commit()
            return room_id

    def configure(self, room_id: str, owner_id: str, enabled: bool) -> None:
        with self.lock, self.database.session() as session:
            room = session.scalar(
                select(WebRoomRecord).where(WebRoomRecord.id == room_id).with_for_update()
            )
            if room is None or room.owner_id != owner_id:
                raise WebRoomError("room_unavailable", 404)
            room.enabled = enabled
            if not enabled:
                session.execute(
                    update(WebOutboxRecord)
                    .where(WebOutboxRecord.room_id == room_id, WebOutboxRecord.status == "pending")
                    .values(status="cancelled", reason="room_disabled")
                )
            session.commit()

    def members(self, room_id: str, owner_id: str) -> list[dict[str, object]]:
        with self.database.session() as session:
            room = session.get(WebRoomRecord, room_id)
            if room is None or room.owner_id != owner_id:
                raise WebRoomError("room_unavailable", 404)
            return [
                {"user_id": row.user_id, "can_post": row.can_post}
                for row in session.scalars(
                    select(WebRoomMemberRecord)
                    .where(WebRoomMemberRecord.room_id == room_id)
                    .limit(200)
                )
            ]

    def member(self, room_id: str, owner_id: str, user_id: str, can_post: bool | None) -> None:
        with self.lock, self.database.session() as session:
            room = session.scalar(
                select(WebRoomRecord).where(WebRoomRecord.id == room_id).with_for_update()
            )
            if room is None or room.owner_id != owner_id:
                raise WebRoomError("room_unavailable", 404)
            member_id = _hash([room_id, user_id])
            member = session.get(WebRoomMemberRecord, member_id)
            if can_post is None:
                if member is not None:
                    session.delete(member)
                session.execute(
                    update(WebOutboxRecord)
                    .where(
                        WebOutboxRecord.room_id == room_id,
                        WebOutboxRecord.owner_id == user_id,
                        WebOutboxRecord.status == "pending",
                    )
                    .values(status="cancelled", reason="membership_revoked")
                )
            else:
                if not self._server_access(session, room, user_id):
                    raise WebRoomError("server_access_required", 403)
                if member is None:
                    if (
                        session.scalar(
                            select(func.count())
                            .select_from(WebRoomMemberRecord)
                            .where(WebRoomMemberRecord.room_id == room_id)
                        )
                        or 0
                    ) >= 200:
                        raise WebRoomError("room_member_limit", 429)
                    member = WebRoomMemberRecord(id=member_id, room_id=room_id, user_id=user_id)
                    session.add(member)
                member.can_post = can_post
            session.commit()

    def profiles(self, user_id: str) -> list[ProfileView]:
        with self.database.session() as session:
            return [
                _profile(row)
                for row in session.scalars(
                    select(WebProfileRecord)
                    .where(WebProfileRecord.owner_id == user_id)
                    .order_by(WebProfileRecord.id)
                    .limit(8)
                )
            ]

    def save_profile(
        self, user_id: str, payload: ProfileInput, profile_id: str = "", expected_version: int = 0
    ) -> ProfileView:
        with self.lock, self.database.session() as session:
            # Parent row lock serializes the profile count in production.
            if (
                session.scalar(select(UserRecord).where(UserRecord.id == user_id).with_for_update())
                is None
            ):
                raise WebRoomError("account_unavailable", 404)
            if profile_id:
                row = session.scalar(
                    select(WebProfileRecord)
                    .where(WebProfileRecord.id == profile_id)
                    .with_for_update()
                )
                if row is None or row.owner_id != user_id:
                    raise WebRoomError("profile_unavailable", 404)
                if row.version != expected_version:
                    raise WebRoomError("profile_version_conflict")
                row.version += 1
            else:
                if (
                    session.scalar(
                        select(func.count())
                        .select_from(WebProfileRecord)
                        .where(WebProfileRecord.owner_id == user_id)
                    )
                    or 0
                ) >= 8:
                    raise WebRoomError("profile_limit", 429)
                row = WebProfileRecord(id=str(uuid4()), owner_id=user_id, version=1)
                session.add(row)
            row.display_name, row.avatar_url = payload.display_name, payload.avatar_url
            session.commit()
            return _profile(row)

    def enqueue(self, user_id: str, room_id: str, payload: WebSend) -> WebDeliveryView:
        self.require(room_id, user_id, post=True, fresh=True)
        request_hash = _hash([room_id, payload.model_dump()])
        record_id = _hash([user_id, payload.client_message_id])
        now = datetime.now(UTC)
        with self.lock, self.database.session() as session:
            room = session.scalar(
                select(WebRoomRecord).where(WebRoomRecord.id == room_id).with_for_update()
            )
            if room is None or not self._access(session, room, user_id, post=True):
                raise WebRoomError("room_unavailable", 404)
            session.scalar(select(UserRecord).where(UserRecord.id == user_id).with_for_update())
            existing = session.get(WebOutboxRecord, record_id)
            if existing is not None:
                if existing.payload_hash != request_hash:
                    raise WebRoomError("client_message_id_conflict")
                return delivery_view(existing)
            profile = session.get(WebProfileRecord, payload.profile_id)
            if profile is None or profile.owner_id != user_id:
                raise WebRoomError("profile_unavailable", 404)
            if payload.reply_to_message_id:
                target = self.sources.get(room_scope(room), payload.reply_to_message_id)
                if target is None or target.message.deleted or not target.message.content_available:
                    raise WebRoomError("reply_source_unavailable", 422)
            for condition, limit in [
                (WebOutboxRecord.owner_id == user_id, 10),
                (WebOutboxRecord.room_id == room_id, 30),
            ]:
                count = (
                    session.scalar(
                        select(func.count())
                        .select_from(WebOutboxRecord)
                        .where(condition, WebOutboxRecord.created_at >= now - timedelta(seconds=60))
                    )
                    or 0
                )
                if count >= limit:
                    raise WebRoomError("web_send_rate_limit", 429)
            if (
                session.scalar(
                    select(func.count())
                    .select_from(WebOutboxRecord)
                    .where(
                        WebOutboxRecord.room_id == room_id,
                        WebOutboxRecord.status.in_(["pending", "claimed"]),
                    )
                )
                or 0
            ) >= 32:
                raise WebRoomError("web_send_capacity", 429)
            row = WebOutboxRecord(
                id=record_id,
                room_id=room_id,
                owner_id=user_id,
                profile_id=profile.id,
                client_message_id=payload.client_message_id,
                payload_hash=request_hash,
                status="pending",
                routing_status="pending",
                payload_json=json.dumps(
                    {
                        "display_name": profile.display_name,
                        "avatar_url": profile.avatar_url,
                        "text": payload.text,
                        "reply_to_message_id": payload.reply_to_message_id,
                    },
                    ensure_ascii=False,
                ),
                discord_message_id="",
                reason="",
                created_at=now,
            )
            session.add(row)
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise WebRoomError("client_message_id_conflict") from exc
            return delivery_view(row)

    def outbox(self, room_id: str, user_id: str) -> list[WebDeliveryView]:
        self.require(room_id, user_id)
        with self.database.session() as session:
            return [
                delivery_view(row)
                for row in session.scalars(
                    select(WebOutboxRecord)
                    .where(WebOutboxRecord.room_id == room_id, WebOutboxRecord.owner_id == user_id)
                    .order_by(WebOutboxRecord.created_at.desc())
                    .limit(32)
                )
            ]

    def connector_rooms(self, connection_id: str) -> list[WebRoomRecord]:
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(WebRoomRecord)
                    .where(
                        WebRoomRecord.connection_id == connection_id,
                        WebRoomRecord.enabled.is_(True),
                    )
                    .limit(16)
                )
            )

    def register_webhook(self, connection_id: str, room_id: str, webhook_id: str) -> None:
        with self.lock, self.database.session() as session:
            room = session.get(WebRoomRecord, room_id)
            if room is None or room.connection_id != connection_id or not room.enabled:
                raise WebRoomError("room_unavailable", 404)
            room.webhook_id = webhook_id
            session.commit()

    def claim(self, connection_id: str, room_id: str, nonce: str) -> WebRoomDelivery | None:
        now = datetime.now(UTC)
        with self.lock, self.database.session() as session:
            room = session.scalar(
                select(WebRoomRecord).where(WebRoomRecord.id == room_id).with_for_update()
            )
            if room is None or room.connection_id != connection_id:
                raise WebRoomError("room_unavailable", 404)
            if not room.enabled or not room.webhook_id:
                return None
            if not self.sources.can_read(room_scope(room), max_age_seconds=90):
                return None
            # A crashed send has an unknown remote effect; never lease-expire it back to pending.
            session.execute(
                update(WebOutboxRecord)
                .where(
                    WebOutboxRecord.room_id == room_id,
                    WebOutboxRecord.status == "claimed",
                    WebOutboxRecord.claimed_at < now - timedelta(minutes=2),
                )
                .values(status="uncertain", reason="claim_expired_no_receipt")
            )
            rows = session.scalars(
                select(WebOutboxRecord)
                .where(WebOutboxRecord.room_id == room_id, WebOutboxRecord.status == "pending")
                .order_by(WebOutboxRecord.created_at)
                .limit(32)
            ).all()
            for row in rows:
                if not self._access(session, room, row.owner_id, post=True):
                    row.status, row.reason = "cancelled", "access_revoked"
                    continue
                if _aware(row.created_at) < now - timedelta(minutes=5):
                    row.status, row.reason = "failed", "queue_expired"
                    continue
                row.status, row.claim_nonce, row.claimed_at = "claimed", nonce, now
                row.webhook_id = room.webhook_id
                session.commit()
                return WebRoomDelivery(
                    **delivery_view(row).model_dump(),
                    room_id=room.id,
                    claim_nonce=nonce,
                    guild_id=room.guild_id,
                    channel_id=room.channel_id,
                    thread_id=room.thread_id,
                    webhook_id=room.webhook_id,
                    actor_id=f"web:{row.profile_id}",
                )
            session.commit()
            return None

    def preflight(self, connection_id: str, record_id: str, nonce: str) -> bool:
        with self.database.session() as session:
            row = session.get(WebOutboxRecord, record_id)
            room = session.get(WebRoomRecord, row.room_id) if row else None
            if row and room:
                target_id = json.loads(row.payload_json)["reply_to_message_id"]
                if target_id:
                    target = self.sources.get(room_scope(room), target_id)
                    if (
                        target is None
                        or target.message.deleted
                        or not target.message.content_available
                    ):
                        return False
            return bool(
                row
                and room
                and room.connection_id == connection_id
                and row.status == "claimed"
                and row.claim_nonce == nonce
                and self._access(session, room, row.owner_id, post=True)
                and self.sources.can_read(room_scope(room), max_age_seconds=90)
            )

    def acknowledge(
        self,
        connection_id: str,
        record_id: str,
        nonce: str,
        *,
        status: str,
        message_id: str = "",
        created_at: datetime | None = None,
        webhook_id: str = "",
        reason: str = "",
    ) -> WebDeliveryView:
        if status not in {"delivered", "failed", "uncertain", "cancelled"}:
            raise WebRoomError("invalid_delivery_status", 422)
        if status == "delivered" and (not message_id or not created_at or not webhook_id):
            raise WebRoomError("delivery_receipt_required", 422)
        with self.lock, self.database.session() as session:
            row = session.scalar(
                select(WebOutboxRecord).where(WebOutboxRecord.id == record_id).with_for_update()
            )
            room = session.get(WebRoomRecord, row.room_id) if row else None
            if (
                row is None
                or room is None
                or room.connection_id != connection_id
                or row.claim_nonce != nonce
            ):
                raise WebRoomError("delivery_claim_mismatch", 409)
            if row.status == "delivered":
                if (
                    status == "delivered"
                    and row.discord_message_id == message_id
                    and row.webhook_id == webhook_id
                ):
                    return delivery_view(row)
                raise WebRoomError("delivery_receipt_conflict")
            if row.status not in {"claimed", "uncertain"}:
                if row.status == status and not message_id and not row.discord_message_id:
                    return delivery_view(row)
                raise WebRoomError("delivery_terminal")
            if status == "delivered":
                if webhook_id != row.webhook_id:
                    raise WebRoomError("webhook_receipt_mismatch")
                existing = session.scalar(
                    select(WebOutboxRecord.id).where(
                        WebOutboxRecord.discord_message_id == message_id,
                        WebOutboxRecord.id != row.id,
                    )
                )
                if existing:
                    raise WebRoomError("discord_receipt_reused")
            # Revocation suppresses future reads/sends, not already observed remote receipts.
            row.status, row.discord_message_id = status, message_id
            row.discord_created_at, row.reason = created_at, reason[:80]
            session.commit()
            return delivery_view(row)

    def delivered(
        self, connection_id: str, guild_id: str, channel_id: str, thread_id: str, message_id: str
    ) -> WebOutboxRecord | None:
        with self.database.session() as session:
            return session.scalar(
                select(WebOutboxRecord)
                .join(WebRoomRecord, WebRoomRecord.id == WebOutboxRecord.room_id)
                .where(
                    WebRoomRecord.connection_id == connection_id,
                    WebRoomRecord.guild_id == guild_id,
                    WebRoomRecord.channel_id == channel_id,
                    WebRoomRecord.thread_id == thread_id,
                    WebOutboxRecord.discord_message_id == message_id,
                    WebOutboxRecord.status == "delivered",
                )
            )

    def source_delivery(self, connection_id: str, message_id: str) -> WebRoomDelivery | None:
        with self.database.session() as session:
            result = session.execute(
                select(WebOutboxRecord, WebRoomRecord)
                .join(WebRoomRecord, WebRoomRecord.id == WebOutboxRecord.room_id)
                .where(
                    WebRoomRecord.connection_id == connection_id,
                    WebOutboxRecord.discord_message_id == message_id,
                    WebOutboxRecord.status == "delivered",
                )
            ).first()
            if result is None:
                return None
            row, room = result
            if not self._access(session, room, row.owner_id, post=True):
                return None
            return WebRoomDelivery(
                **delivery_view(row).model_dump(),
                room_id=room.id,
                claim_nonce=row.claim_nonce,
                guild_id=room.guild_id,
                channel_id=room.channel_id,
                thread_id=room.thread_id,
                webhook_id=row.webhook_id,
                actor_id=f"web:{row.profile_id}",
            )

    def pending_dispatch(self, connection_id: str) -> list[WebRoomDelivery]:
        with self.database.session() as session:
            rows = session.execute(
                select(WebOutboxRecord, WebRoomRecord)
                .join(WebRoomRecord, WebRoomRecord.id == WebOutboxRecord.room_id)
                .where(
                    WebRoomRecord.connection_id == connection_id,
                    WebRoomRecord.enabled.is_(True),
                    WebOutboxRecord.status == "delivered",
                    WebOutboxRecord.routing_status == "pending",
                )
                .order_by(WebOutboxRecord.created_at)
                .limit(32)
            ).all()
            return [
                WebRoomDelivery(
                    **delivery_view(row).model_dump(),
                    room_id=room.id,
                    claim_nonce=row.claim_nonce,
                    guild_id=room.guild_id,
                    channel_id=room.channel_id,
                    thread_id=room.thread_id,
                    webhook_id=row.webhook_id,
                    actor_id=f"web:{row.profile_id}",
                )
                for row, room in rows
                if self._access(session, room, row.owner_id, post=True)
            ]

    def finish_dispatch(
        self, connection_id: str, record_id: str, nonce: str, outcome: str = "processed"
    ) -> None:
        if outcome not in {"processed", "failed"}:
            raise WebRoomError("invalid_dispatch_outcome", 422)
        with self.lock, self.database.session() as session:
            row = session.get(WebOutboxRecord, record_id)
            room = session.get(WebRoomRecord, row.room_id) if row else None
            if (
                not row
                or not room
                or room.connection_id != connection_id
                or row.claim_nonce != nonce
            ):
                raise WebRoomError("dispatch_claim_mismatch")
            if row.status != "delivered":
                raise WebRoomError("dispatch_requires_receipt")
            row.routing_status = outcome
            session.commit()
