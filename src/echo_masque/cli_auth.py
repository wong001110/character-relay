"""Database-backed public-client device grants; never ordinary AuthContexts."""

from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from echo_masque.cli_auth_policy import (
    CLI_CLIENT_ID,
    CLI_CLIENT_NAME,
    CLI_SCOPES,
    CLI_TOKEN_PREFIX,
)
from echo_masque.config import Settings
from echo_masque.persistence import Database
from echo_masque.persistence.cli_auth_models import CliDeviceRecord, CliGrantRecord
from echo_masque.persistence.models import AuditEventRecord, UserRecord
from echo_masque.persistence.web_room_repository import WebRoomRepository


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def normalized_code(code: str) -> str:
    return code.upper().replace("-", "").replace(" ", "")


class CliAuthError(Exception):
    def __init__(self, code: str, status: int = 400) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class CliPrincipal:
    user_id: str
    display_name: str
    grant_id: str
    scopes: frozenset[str]
    room_ids: tuple[str, ...]
    metadata: dict[str, object] = field(repr=False)


class CliAuthService:
    def __init__(self, database: Database, settings: Settings, rooms: WebRoomRepository) -> None:
        self.database = database
        self.settings = settings
        self.rooms = rooms

    def enabled(self) -> None:
        if not self.settings.cli_auth_enabled:
            raise CliAuthError("cli_auth_disabled", 404)

    def create_device(
        self, client_id: str, scopes: list[str], room_ids: list[str]
    ) -> dict[str, object]:
        self.enabled()
        if client_id != CLI_CLIENT_ID:
            raise CliAuthError("invalid_client")
        if not scopes or not set(scopes) <= CLI_SCOPES:
            raise CliAuthError("invalid_scope")
        if (
            not room_ids
            or len(room_ids) > 32
            or any(
                not room
                or len(room) > 64
                or not all(c.isascii() and (c.isalnum() or c in "_-") for c in room)
                for room in room_ids
            )
        ):
            raise CliAuthError("invalid_room_selection")
        now = datetime.now(UTC)
        device_code = secrets.token_urlsafe(32)
        code = "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(10))
        with self.database.session() as session:
            session.add(
                CliDeviceRecord(
                    id=uuid4().hex,
                    device_code_hash=digest(device_code),
                    user_code_hash=digest(code),
                    client_id=client_id,
                    scopes_json=json.dumps(sorted(set(scopes))),
                    room_ids_json=json.dumps(sorted(set(room_ids))),
                    status="pending",
                    expires_at=now + timedelta(seconds=self.settings.cli_device_ttl_seconds),
                    next_poll_at=now,
                    interval=5,
                    poll_version=0,
                )
            )
            session.commit()
        return {
            "device_code": device_code,
            "user_code": code[:5] + "-" + code[5:],
            "verification_uri": self.settings.cli_auth_public_origin + "/cli/authorize",
            "expires_in": self.settings.cli_device_ttl_seconds,
            "interval": 5,
        }

    def _device(self, session: Session, code: str) -> CliDeviceRecord:
        record = session.scalar(
            select(CliDeviceRecord).where(
                CliDeviceRecord.user_code_hash == digest(normalized_code(code))
            )
        )
        if record is None or aware(record.expires_at) <= datetime.now(UTC):
            raise CliAuthError("invalid_or_expired_code")
        return record

    def review(self, code: str, user_id: str) -> dict[str, object]:
        self.enabled()
        with self.database.session() as session:
            record = self._device(session, code)
            if record.status != "pending":
                raise CliAuthError("authorization_already_decided", 409)
            rooms = [
                self.rooms.require(room, user_id, fresh=True)
                for room in json.loads(record.room_ids_json)
            ]
            bound = session.execute(
                update(CliDeviceRecord)
                .execution_options(synchronize_session="fetch")
                .where(
                    CliDeviceRecord.id == record.id,
                    CliDeviceRecord.status == "pending",
                    or_(
                        CliDeviceRecord.reviewing_user_id.is_(None),
                        CliDeviceRecord.reviewing_user_id == user_id,
                    ),
                    CliDeviceRecord.expires_at > datetime.now(UTC),
                )
                .values(reviewing_user_id=user_id)
                .returning(CliDeviceRecord.id)
            ).scalar_one_or_none()
            if bound is None:
                raise CliAuthError("authorization_account_mismatch", 403)
            result: dict[str, object] = {
                "client_id": record.client_id,
                "client_name": CLI_CLIENT_NAME,
                "rooms": [{"id": room.id, "name": room.name} for room in rooms],
                "scopes": json.loads(record.scopes_json),
                "device_expires_at": aware(record.expires_at).isoformat(),
                "access_token_ttl_seconds": self.settings.cli_access_ttl_seconds,
            }
            session.commit()
            return result

    def decide(self, code: str, user_id: str, approve: bool) -> dict[str, object]:
        self.enabled()
        now = datetime.now(UTC)
        with self.database.session() as session:
            record = self._device(session, code)
            if record.reviewing_user_id != user_id:
                raise CliAuthError("authorization_account_mismatch", 403)
            if approve:
                for room in json.loads(record.room_ids_json):
                    self.rooms.require(room, user_id, fresh=True)
            changed = session.execute(
                update(CliDeviceRecord)
                .execution_options(synchronize_session="fetch")
                .where(
                    CliDeviceRecord.id == record.id,
                    CliDeviceRecord.status == "pending",
                    CliDeviceRecord.reviewing_user_id == user_id,
                    CliDeviceRecord.expires_at > now,
                )
                .values(status="approved" if approve else "denied")
                .returning(CliDeviceRecord.id)
            ).scalar_one_or_none()
            if changed is None:
                raise CliAuthError("authorization_already_decided", 409)
            result: dict[str, object] = {"status": "approved" if approve else "denied"}
            resource_id = record.id
            if approve:
                grant = CliGrantRecord(
                    id=uuid4().hex,
                    user_id=user_id,
                    client_id=record.client_id,
                    scopes_json=record.scopes_json,
                    room_ids_json=record.room_ids_json,
                    approved_at=now,
                    expires_at=now + timedelta(seconds=self.settings.cli_access_ttl_seconds),
                )
                session.add(grant)
                session.flush()
                record.grant_id = grant.id
                result["grant"] = self.metadata(grant)
                resource_id = grant.id
            self._audit(
                session,
                user_id,
                "cli_grant.approved" if approve else "cli_grant.denied",
                resource_id,
            )
            session.commit()
            return result

    def exchange(self, client_id: str, device_code: str) -> dict[str, object]:
        self.enabled()
        if client_id != CLI_CLIENT_ID:
            raise CliAuthError("invalid_client")
        now = datetime.now(UTC)
        with self.database.session() as session:
            record = session.scalar(
                select(CliDeviceRecord).where(
                    CliDeviceRecord.device_code_hash == digest(device_code),
                    CliDeviceRecord.client_id == client_id,
                )
            )
            if record is None or record.status == "redeemed":
                raise CliAuthError("invalid_grant")
            if aware(record.expires_at) <= now:
                raise CliAuthError("expired_token")
            if record.status == "denied":
                raise CliAuthError("access_denied")
            slow = aware(record.next_poll_at) > now
            interval = record.interval + 5 if slow else record.interval
            claimed = session.execute(
                update(CliDeviceRecord)
                .execution_options(synchronize_session="fetch")
                .where(
                    CliDeviceRecord.id == record.id,
                    CliDeviceRecord.poll_version == record.poll_version,
                    CliDeviceRecord.status == record.status,
                )
                .values(
                    poll_version=record.poll_version + 1,
                    interval=interval,
                    next_poll_at=now + timedelta(seconds=interval),
                )
                .returning(CliDeviceRecord.id)
            ).scalar_one_or_none()
            if claimed is None:
                raise CliAuthError("slow_down")
            if slow or record.status == "pending":
                session.commit()  # Penalties must survive the OAuth error response.
                raise CliAuthError("slow_down" if slow else "authorization_pending")
            grant = session.get(CliGrantRecord, record.grant_id)
            if grant is None or grant.revoked_at or aware(grant.expires_at) <= now:
                session.commit()
                raise CliAuthError("expired_token")
            user = session.get(UserRecord, grant.user_id)
            if user is None or not user.is_active:
                raise CliAuthError("access_denied")
            for room in json.loads(grant.room_ids_json):
                self.rooms.require(room, user.id, fresh=True)
            redeemed = session.execute(
                update(CliDeviceRecord)
                .execution_options(synchronize_session="fetch")
                .where(
                    CliDeviceRecord.id == record.id,
                    CliDeviceRecord.status == "approved",
                )
                .values(status="redeemed")
                .returning(CliDeviceRecord.id)
            ).scalar_one_or_none()
            if redeemed is None:
                raise CliAuthError("invalid_grant")
            token = CLI_TOKEN_PREFIX + secrets.token_urlsafe(32)
            issued = session.execute(
                update(CliGrantRecord)
                .execution_options(synchronize_session="fetch")
                .where(
                    CliGrantRecord.id == grant.id,
                    CliGrantRecord.revoked_at.is_(None),
                    CliGrantRecord.expires_at > datetime.now(UTC),
                    CliGrantRecord.token_hash.is_(None),
                )
                .values(token_hash=digest(token))
                .returning(CliGrantRecord.id)
            ).scalar_one_or_none()
            if issued is None:
                raise CliAuthError("expired_token")
            self._audit(session, user.id, "cli_grant.redeemed", grant.id)
            session.commit()
            return {
                "access_token": token,
                "token_type": "Bearer",
                "expires_in": max(0, int((aware(grant.expires_at) - now).total_seconds())),
                "scope": " ".join(json.loads(grant.scopes_json)),
            }

    @staticmethod
    def metadata(grant: CliGrantRecord) -> dict[str, object]:
        return {
            "grant_id": grant.id,
            "client_id": grant.client_id,
            "client_name": CLI_CLIENT_NAME,
            "scopes": json.loads(grant.scopes_json),
            "room_ids": json.loads(grant.room_ids_json),
            "approved_at": aware(grant.approved_at).isoformat(),
            "expires_at": aware(grant.expires_at).isoformat(),
            "revoked_at": aware(grant.revoked_at).isoformat() if grant.revoked_at else None,
        }

    def resolve(self, token: str, *, check_rooms: bool = True) -> CliPrincipal:
        self.enabled()
        if not token.startswith(CLI_TOKEN_PREFIX):
            raise CliAuthError("invalid_token", 401)
        with self.database.session() as session:
            grant = session.scalar(
                select(CliGrantRecord).where(CliGrantRecord.token_hash == digest(token))
            )
            if grant is None or grant.revoked_at or aware(grant.expires_at) <= datetime.now(UTC):
                raise CliAuthError("invalid_token", 401)
            user = session.get(UserRecord, grant.user_id)
            if user is None or not user.is_active:
                raise CliAuthError("invalid_token", 401)
            rooms = tuple(json.loads(grant.room_ids_json))
            if check_rooms:
                for room in rooms:
                    self.rooms.require(room, user.id, fresh=True)
            return CliPrincipal(
                user.id,
                user.display_name,
                grant.id,
                frozenset(json.loads(grant.scopes_json)),
                rooms,
                self.metadata(grant),
            )

    def list_grants(self, user_id: str) -> list[dict[str, object]]:
        self.enabled()
        with self.database.session() as session:
            records = session.scalars(
                select(CliGrantRecord)
                .where(CliGrantRecord.user_id == user_id)
                .order_by(CliGrantRecord.approved_at.desc())
                .limit(100)
            )
            return [self.metadata(record) for record in records]

    def revoke(self, grant_id: str, user_id: str) -> None:
        self.enabled()
        with self.database.session() as session:
            record = session.get(CliGrantRecord, grant_id)
            if record is None or record.user_id != user_id:
                raise CliAuthError("grant_not_found", 404)
            if record.revoked_at is None:
                record.revoked_at = datetime.now(UTC)
                self._audit(session, user_id, "cli_grant.revoked", record.id)
                session.commit()

    @staticmethod
    def _audit(session: Session, user_id: str, action: str, resource_id: str) -> None:
        session.add(
            AuditEventRecord(
                id=str(uuid4()),
                actor_user_id=user_id,
                action=action,
                resource_type="cli_grant",
                resource_id=resource_id,
                metadata_json=json.dumps({"client_id": CLI_CLIENT_ID}),
            )
        )
