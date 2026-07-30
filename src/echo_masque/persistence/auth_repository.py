"""Persistence operations for users, sessions, invitations, credentials, and audit events."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from sqlalchemy import func, select

from echo_masque.persistence.database import Database
from echo_masque.persistence.models import (
    AuditEventRecord,
    AuthSessionRecord,
    EncryptedCredentialRecord,
    InvitationRecord,
    UserRecord,
)

Role = Literal["user", "admin"]


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class AuthRepository:
    """Keep authentication and secret metadata behind one database boundary."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def create_user(
        self,
        *,
        email: str,
        display_name: str,
        password_hash: str,
        role: Role = "user",
        user_id: str | None = None,
    ) -> UserRecord:
        record = UserRecord(
            id=user_id or str(uuid4()),
            email=email.casefold().strip(),
            display_name=display_name.strip(),
            password_hash=password_hash,
            role=role,
            is_active=True,
        )
        with self.database.session() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def get_user(self, user_id: str) -> UserRecord | None:
        with self.database.session() as session:
            return session.get(UserRecord, user_id)

    def get_user_by_email(self, email: str) -> UserRecord | None:
        normalized = email.casefold().strip()
        with self.database.session() as session:
            return session.scalar(
                select(UserRecord).where(func.lower(UserRecord.email) == normalized)
            )

    def count_users(self) -> int:
        with self.database.session() as session:
            return int(session.scalar(select(func.count()).select_from(UserRecord)) or 0)

    def create_session(
        self,
        *,
        user_id: str,
        token_hash: str,
        expires_at: datetime,
        user_agent_hash: str | None,
    ) -> AuthSessionRecord:
        record = AuthSessionRecord(
            id=str(uuid4()),
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            user_agent_hash=user_agent_hash,
        )
        with self.database.session() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def get_session_by_token_hash(self, token_hash: str) -> AuthSessionRecord | None:
        with self.database.session() as session:
            return session.scalar(
                select(AuthSessionRecord).where(AuthSessionRecord.token_hash == token_hash)
            )

    def touch_session(self, session_id: str, *, now: datetime) -> None:
        with self.database.session() as session:
            record = session.get(AuthSessionRecord, session_id)
            if record is None or record.revoked_at is not None:
                return
            if (now - _utc(record.last_seen_at)).total_seconds() < 60:
                return
            record.last_seen_at = now
            session.commit()

    def list_sessions(self, user_id: str) -> list[AuthSessionRecord]:
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(AuthSessionRecord)
                    .where(AuthSessionRecord.user_id == user_id)
                    .order_by(AuthSessionRecord.created_at.desc())
                )
            )

    def get_session(self, session_id: str, user_id: str) -> AuthSessionRecord | None:
        with self.database.session() as session:
            return session.scalar(
                select(AuthSessionRecord).where(
                    AuthSessionRecord.id == session_id,
                    AuthSessionRecord.user_id == user_id,
                )
            )

    def revoke_session(self, session_id: str, *, user_id: str | None = None) -> bool:
        with self.database.session() as session:
            statement = select(AuthSessionRecord).where(AuthSessionRecord.id == session_id)
            if user_id is not None:
                statement = statement.where(AuthSessionRecord.user_id == user_id)
            record = session.scalar(statement)
            if record is None:
                return False
            if record.revoked_at is None:
                record.revoked_at = datetime.now(UTC)
                session.commit()
            return True

    def create_invitation(
        self,
        *,
        code_hash: str,
        expires_at: datetime,
        email: str | None = None,
        role: Role = "user",
        created_by: str | None = None,
    ) -> InvitationRecord:
        record = InvitationRecord(
            id=str(uuid4()),
            code_hash=code_hash,
            email=email.casefold().strip() if email else None,
            role=role,
            created_by=created_by,
            expires_at=expires_at,
        )
        with self.database.session() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def claim_invitation(
        self,
        *,
        code_hash: str,
        email: str,
        accepted_by: str,
    ) -> InvitationRecord | None:
        now = datetime.now(UTC)
        normalized = email.casefold().strip()
        with self.database.session() as session:
            record = session.scalar(
                select(InvitationRecord).where(InvitationRecord.code_hash == code_hash)
            )
            if record is None:
                return None
            if record.accepted_at is not None or record.revoked_at is not None:
                return None
            if _utc(record.expires_at) <= now:
                return None
            if record.email is not None and record.email != normalized:
                return None
            record.accepted_by = accepted_by
            record.accepted_at = now
            session.commit()
            session.refresh(record)
            return record

    def save_credential(
        self,
        *,
        owner_id: str,
        scope_kind: str,
        scope_id: str,
        encrypted_value: str,
        key_version: str,
        rotated: bool = False,
    ) -> EncryptedCredentialRecord:
        with self.database.session() as session:
            record = session.scalar(
                select(EncryptedCredentialRecord).where(
                    EncryptedCredentialRecord.owner_id == owner_id,
                    EncryptedCredentialRecord.scope_kind == scope_kind,
                    EncryptedCredentialRecord.scope_id == scope_id,
                )
            )
            if record is None:
                record = EncryptedCredentialRecord(
                    id=str(uuid4()),
                    owner_id=owner_id,
                    scope_kind=scope_kind,
                    scope_id=scope_id,
                    encrypted_value=encrypted_value,
                    key_version=key_version,
                )
                session.add(record)
            else:
                record.encrypted_value = encrypted_value
                record.key_version = key_version
                if rotated:
                    record.rotated_at = datetime.now(UTC)
            session.commit()
            session.refresh(record)
            return record

    def get_credential(
        self,
        *,
        owner_id: str,
        scope_kind: str,
        scope_id: str,
    ) -> EncryptedCredentialRecord | None:
        with self.database.session() as session:
            return session.scalar(
                select(EncryptedCredentialRecord).where(
                    EncryptedCredentialRecord.owner_id == owner_id,
                    EncryptedCredentialRecord.scope_kind == scope_kind,
                    EncryptedCredentialRecord.scope_id == scope_id,
                )
            )

    def list_credentials(self) -> list[EncryptedCredentialRecord]:
        with self.database.session() as session:
            return list(session.scalars(select(EncryptedCredentialRecord)))

    def delete_credential(self, *, owner_id: str, scope_kind: str, scope_id: str) -> None:
        with self.database.session() as session:
            record = session.scalar(
                select(EncryptedCredentialRecord).where(
                    EncryptedCredentialRecord.owner_id == owner_id,
                    EncryptedCredentialRecord.scope_kind == scope_kind,
                    EncryptedCredentialRecord.scope_id == scope_id,
                )
            )
            if record is None:
                return
            session.delete(record)
            session.commit()

    def audit(
        self,
        *,
        action: str,
        resource_type: str,
        actor_user_id: str | None = None,
        resource_id: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> AuditEventRecord:
        record = AuditEventRecord(
            id=str(uuid4()),
            actor_user_id=actor_user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            metadata_json=json.dumps(metadata or {}, sort_keys=True, separators=(",", ":")),
        )
        with self.database.session() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
            return record
