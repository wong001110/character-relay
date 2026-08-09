"""Authentication helpers for Character Relay."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from echo_masque.config import Settings
from echo_masque.persistence.auth_models import AccountRecord, SessionRecord
from echo_masque.persistence.auth_repository import AuthRepository


@dataclass(frozen=True)
class AuthenticatedUser:
    """Authenticated account exposed to API/runtime services."""

    id: str
    email: str
    display_name: str
    role: str

    @classmethod
    def from_record(cls, record: AccountRecord) -> AuthenticatedUser:
        return cls(
            id=record.id,
            email=record.email,
            display_name=record.display_name,
            role=record.role,
        )


class PasswordService:
    """Argon2 password hashing and verification."""

    def __init__(self) -> None:
        self._hasher = PasswordHasher()

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, password_hash: str, password: str) -> bool:
        try:
            return self._hasher.verify(password_hash, password)
        except (VerifyMismatchError, InvalidHashError):
            return False

    def needs_rehash(self, password_hash: str) -> bool:
        try:
            return self._hasher.check_needs_rehash(password_hash)
        except InvalidHashError:
            return True


class AuthService:
    """Account/session lifecycle with production-safe bootstrap behavior."""

    def __init__(
        self,
        repository: AuthRepository,
        settings: Settings,
        *,
        passwords: PasswordService | None = None,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.passwords = passwords or PasswordService()

    def authenticate(self, email: str, password: str) -> AuthenticatedUser | None:
        normalized = self._normalize_email(email)
        record = self.repository.get_user_by_email(normalized)
        if record is None or record.status != "active":
            return None
        if not self.passwords.verify(record.password_hash, password):
            return None
        self.repository.record_login(record.id)
        if self.passwords.needs_rehash(record.password_hash):
            self.repository.update_password_hash(record.id, self.passwords.hash(password))
        refreshed = self.repository.get_user(record.id) or record
        return AuthenticatedUser.from_record(refreshed)

    def create_session(self, user_id: str) -> tuple[str, SessionRecord]:
        token = secrets.token_urlsafe(48)
        expires_at = datetime.now(UTC) + timedelta(seconds=self.settings.auth_session_ttl_seconds)
        return token, self.repository.create_session(user_id, token, expires_at)

    def resolve_session(self, token: str) -> AuthenticatedUser | None:
        record = self.repository.get_session(token)
        if record is None:
            return None
        user = self.repository.get_user(record.user_id)
        if user is None or user.status != "active":
            return None
        return AuthenticatedUser.from_record(user)

    def revoke_session(self, token: str) -> None:
        self.repository.revoke_session(token)

    def ensure_local_user(self) -> AuthenticatedUser | None:
        """Return/create the development local user when the compatibility mode is enabled."""

        if not self.settings.legacy_local_user_enabled:
            return None
        record = self.repository.get_user_by_email("local@character-relay.invalid")
        if record is None:
            record = self.repository.create_user(
                email="local@character-relay.invalid",
                display_name="Local User",
                password_hash=self.passwords.hash(secrets.token_urlsafe(64)),
                role="admin",
            )
        return AuthenticatedUser.from_record(record)

    def ensure_bootstrap_admin(self) -> AuthenticatedUser | None:
        """Create or promote the configured first production administrator."""

        email = self.settings.bootstrap_admin_email
        password_secret = self.settings.bootstrap_admin_password
        if email is None and password_secret is None:
            return None
        if email is None or password_secret is None:
            raise ValueError(
                "CHARACTER_RELAY_BOOTSTRAP_ADMIN_EMAIL and "
                "CHARACTER_RELAY_BOOTSTRAP_ADMIN_PASSWORD must be configured together."
            )
        normalized = self._normalize_email(email)
        record = self.repository.get_user_by_email(normalized)
        if record is None:
            password = password_secret.get_secret_value()
            if len(password) < 12:
                raise ValueError("Bootstrap Admin password must contain at least 12 characters.")
            record = self.repository.create_user(
                email=normalized,
                display_name=self.settings.bootstrap_admin_display_name,
                password_hash=self.passwords.hash(password),
                role="admin",
            )
        elif record.role != "admin":
            self.repository.update_role(record.id, "admin")
            record = self.repository.get_user(record.id) or record
        return AuthenticatedUser.from_record(record)

    @staticmethod
    def _normalize_email(email: str) -> str:
        return email.strip().lower()


__all__ = [
    "AuthenticatedUser",
    "AuthService",
    "PasswordService",
]
