"""Authentication, password hashing, and opaque session lifecycle."""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Literal, cast

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from pydantic import BaseModel

from echo_masque.config import Settings
from echo_masque.persistence.auth_repository import AuthRepository
from echo_masque.persistence.models import AuthSessionRecord, UserRecord

Role = Literal["user", "admin"]


class AuthenticationError(ValueError):
    """Raised when credentials or a session cannot be authenticated."""


class RegistrationClosedError(ValueError):
    """Raised when self-service registration is disabled."""


class DuplicateAccountError(ValueError):
    """Raised when an email address is already registered."""


class AuthenticatedUser(BaseModel):
    id: str
    email: str
    display_name: str
    role: Role
    is_active: bool

    @classmethod
    def from_record(cls, record: UserRecord) -> AuthenticatedUser:
        return cls(
            id=record.id,
            email=record.email,
            display_name=record.display_name,
            role=cast(Role, record.role),
            is_active=record.is_active,
        )


class AuthContext(BaseModel):
    user: AuthenticatedUser
    session_id: str | None
    expires_at: datetime | None


class IssuedSession(BaseModel):
    context: AuthContext
    token: str


class AuthService:
    """Create users and resolve revocable opaque session tokens."""

    def __init__(self, repository: AuthRepository, settings: Settings) -> None:
        self.repository = repository
        self.settings = settings
        self.passwords = PasswordHasher()
        self._dummy_hash = self.passwords.hash(secrets.token_urlsafe(32))

    def ensure_development_user(
        self,
        user_id: str = "local-user",
    ) -> AuthenticatedUser | None:
        if self.settings.environment == "production" or not self.settings.legacy_local_user_enabled:
            return None
        record = self.repository.get_user(user_id)
        if record is None:
            legacy_hash = self._digest(user_id)[:24]
            record = self.repository.create_user(
                user_id=user_id,
                email=f"legacy-{legacy_hash}@echo-masque.invalid",
                display_name="Local User" if user_id == "local-user" else user_id,
                password_hash=self.passwords.hash(secrets.token_urlsafe(32)),
                role="admin" if user_id == "local-user" else "user",
            )
        return AuthenticatedUser.from_record(record)

    def development_context(self, user_id: str = "local-user") -> AuthContext | None:
        user = self.ensure_development_user(user_id)
        if user is None:
            return None
        return AuthContext(user=user, session_id=None, expires_at=None)

    def register(self, *, email: str, display_name: str, password: str) -> AuthenticatedUser:
        normalized = self._normalize_email(email)
        if (
            self.settings.environment == "production"
            and not self.settings.public_registration_enabled
        ):
            raise RegistrationClosedError("Registration requires an invitation.")
        if self.repository.get_user_by_email(normalized) is not None:
            raise DuplicateAccountError("An account with this email already exists.")
        record = self.repository.create_user(
            email=normalized,
            display_name=display_name.strip(),
            password_hash=self.passwords.hash(password),
            role="user",
        )
        self.repository.audit(
            actor_user_id=record.id,
            action="account.registered",
            resource_type="user",
            resource_id=record.id,
        )
        return AuthenticatedUser.from_record(record)

    def login(self, *, email: str, password: str, user_agent: str | None) -> IssuedSession:
        normalized = self._normalize_email(email)
        record = self.repository.get_user_by_email(normalized)
        password_hash = record.password_hash if record is not None else self._dummy_hash
        try:
            valid = self.passwords.verify(password_hash, password)
        except VerificationError:
            valid = False
        if record is None or not valid or not record.is_active:
            self.repository.audit(
                action="session.login_failed",
                resource_type="session",
                metadata={"email_hash": self._digest(normalized)},
            )
            raise AuthenticationError("Invalid email or password.")

        token = secrets.token_urlsafe(48)
        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=self.settings.auth_session_ttl_seconds)
        session = self.repository.create_session(
            user_id=record.id,
            token_hash=self._digest(token),
            expires_at=expires_at,
            user_agent_hash=self._digest(user_agent) if user_agent else None,
        )
        self.repository.audit(
            actor_user_id=record.id,
            action="session.login_succeeded",
            resource_type="session",
            resource_id=session.id,
        )
        return IssuedSession(
            context=AuthContext(
                user=AuthenticatedUser.from_record(record),
                session_id=session.id,
                expires_at=expires_at,
            ),
            token=token,
        )

    def resolve(self, token: str) -> AuthContext | None:
        session = self.repository.get_session_by_token_hash(self._digest(token))
        if session is None or session.revoked_at is not None:
            return None
        now = datetime.now(UTC)
        if self._utc(session.expires_at) <= now:
            self.repository.revoke_session(session.id)
            return None
        user = self.repository.get_user(session.user_id)
        if user is None or not user.is_active:
            return None
        self.repository.touch_session(session.id, now=now)
        return AuthContext(
            user=AuthenticatedUser.from_record(user),
            session_id=session.id,
            expires_at=self._utc(session.expires_at),
        )

    def list_sessions(self, user_id: str) -> list[AuthSessionRecord]:
        return self.repository.list_sessions(user_id)

    def revoke_session(self, session_id: str, *, user_id: str) -> bool:
        revoked = self.repository.revoke_session(session_id, user_id=user_id)
        if revoked:
            self.repository.audit(
                actor_user_id=user_id,
                action="session.revoked",
                resource_type="session",
                resource_id=session_id,
            )
        return revoked

    @staticmethod
    def _normalize_email(value: str) -> str:
        normalized = value.casefold().strip()
        if (
            len(normalized) > 320
            or normalized.count("@") != 1
            or " " in normalized
            or normalized.startswith("@")
            or normalized.endswith("@")
        ):
            raise ValueError("Enter a valid email address.")
        return normalized

    @staticmethod
    def _digest(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
