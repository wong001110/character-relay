"""Provider credential storage with encrypted persistence for authenticated workspaces."""

from __future__ import annotations

import hashlib
from threading import RLock

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from pydantic import SecretStr

from echo_masque.config import Settings
from echo_masque.persistence.auth_repository import AuthRepository

_EPHEMERAL_DEVELOPMENT_KEY = Fernet.generate_key()


class CredentialVaultUnavailable(RuntimeError):
    """Raised when encrypted credential storage is unavailable."""


class CredentialStore:
    """Keep user-supplied provider keys in process memory only."""

    def __init__(self) -> None:
        self._values: dict[tuple[str, str], SecretStr] = {}
        self._lock = RLock()

    def set(self, owner_id: str, card_id: str, api_key: SecretStr) -> None:
        with self._lock:
            self._values[(owner_id, card_id)] = api_key

    def get(self, owner_id: str, card_id: str) -> SecretStr | None:
        with self._lock:
            return self._values.get((owner_id, card_id))

    def has(self, owner_id: str, card_id: str) -> bool:
        with self._lock:
            return (owner_id, card_id) in self._values

    def delete(self, owner_id: str, card_id: str) -> None:
        with self._lock:
            self._values.pop((owner_id, card_id), None)


class CredentialVault(CredentialStore):
    """Persist Subject credentials as authenticated ciphertext with rotation support."""

    scope_kind = "character_provider"

    def __init__(self, repository: AuthRepository, settings: Settings) -> None:
        super().__init__()
        self.repository = repository
        self.settings = settings
        configured = settings.credential_encryption_keys
        if configured is None:
            keys = (
                [_EPHEMERAL_DEVELOPMENT_KEY]
                if settings.environment != "production"
                else []
            )
        else:
            keys = [
                item.strip().encode("ascii")
                for item in configured.get_secret_value().split(",")
                if item.strip()
            ]
        self._keys = keys
        self._fernets = [Fernet(key) for key in keys]
        self._cipher = MultiFernet(self._fernets) if self._fernets else None
        self._primary_version = self._version(keys[0]) if keys else "unconfigured"

    @property
    def configured(self) -> bool:
        return self._cipher is not None

    def set(self, owner_id: str, card_id: str, api_key: SecretStr) -> None:
        cipher = self._require_cipher()
        encrypted = cipher.encrypt(api_key.get_secret_value().encode("utf-8")).decode("ascii")
        self.repository.save_credential(
            owner_id=owner_id,
            scope_kind=self.scope_kind,
            scope_id=card_id,
            encrypted_value=encrypted,
            key_version=self._primary_version,
        )
        self.repository.audit(
            actor_user_id=owner_id,
            action="credential.configured",
            resource_type="character_card",
            resource_id=card_id,
            metadata={"key_version": self._primary_version},
        )

    def get(self, owner_id: str, card_id: str) -> SecretStr | None:
        record = self.repository.get_credential(
            owner_id=owner_id,
            scope_kind=self.scope_kind,
            scope_id=card_id,
        )
        if record is None:
            return None
        cipher = self._require_cipher()
        try:
            value = cipher.decrypt(record.encrypted_value.encode("ascii")).decode("utf-8")
        except InvalidToken as exc:
            raise CredentialVaultUnavailable(
                "The credential cannot be decrypted with the configured key set."
            ) from exc
        return SecretStr(value)

    def has(self, owner_id: str, card_id: str) -> bool:
        if not self.configured:
            return False
        return (
            self.repository.get_credential(
                owner_id=owner_id,
                scope_kind=self.scope_kind,
                scope_id=card_id,
            )
            is not None
        )

    def delete(self, owner_id: str, card_id: str) -> None:
        self.repository.delete_credential(
            owner_id=owner_id,
            scope_kind=self.scope_kind,
            scope_id=card_id,
        )
        self.repository.audit(
            actor_user_id=owner_id,
            action="credential.deleted",
            resource_type="character_card",
            resource_id=card_id,
        )

    def rotate_all(self) -> int:
        cipher = self._require_cipher()
        rotated = 0
        for record in self.repository.list_credentials():
            try:
                encrypted = cipher.rotate(record.encrypted_value.encode("ascii")).decode("ascii")
            except InvalidToken as exc:
                raise CredentialVaultUnavailable(
                    f"Credential {record.id} cannot be rotated with the configured key set."
                ) from exc
            self.repository.save_credential(
                owner_id=record.owner_id,
                scope_kind=record.scope_kind,
                scope_id=record.scope_id,
                encrypted_value=encrypted,
                key_version=self._primary_version,
                rotated=True,
            )
            rotated += 1
        return rotated

    def _require_cipher(self) -> MultiFernet:
        if self._cipher is None:
            raise CredentialVaultUnavailable(
                "ECHO_MASQUE_CREDENTIAL_ENCRYPTION_KEYS is required in production."
            )
        return self._cipher

    @staticmethod
    def _version(key: bytes) -> str:
        return hashlib.sha256(key).hexdigest()[:16]
