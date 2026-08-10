"""Encrypted provider and Admin Runtime credential persistence."""

from __future__ import annotations

import hashlib
from threading import RLock

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from pydantic import SecretStr

from echo_masque.config import Settings
from echo_masque.persistence.auth_repository import AuthRepository
from echo_masque.persistence.key_group_repository import KeyGroupRepository

_EPHEMERAL_DEVELOPMENT_KEY = Fernet.generate_key()


class CredentialVaultUnavailable(RuntimeError):
    """Raised when encrypted credential storage is unavailable."""


class CredentialStore:
    """Compatibility interface for provider credential resolution."""

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
    """Persist credentials as authenticated ciphertext with key rotation support."""

    character_scope_kind = "character_provider"
    key_group_scope_kind = "provider_key_group"
    runtime_scope_kind = "admin_runtime"

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

    @property
    def primary_version(self) -> str:
        return self._primary_version

    def set(self, owner_id: str, card_id: str, api_key: SecretStr) -> None:
        self.set_scope(
            owner_id=owner_id,
            scope_kind=self.character_scope_kind,
            scope_id=card_id,
            value=api_key,
            actor_user_id=owner_id,
            resource_type="character_card",
        )

    def get(self, owner_id: str, card_id: str) -> SecretStr | None:
        direct = self.get_scope(
            owner_id=owner_id,
            scope_kind=self.character_scope_kind,
            scope_id=card_id,
        )
        if direct is not None:
            return direct
        resolved = KeyGroupRepository(self.repository.database).resolve(
            owner_id=owner_id,
            character_card_id=card_id,
            capability="character",
        )
        if resolved is None:
            return None
        return self.get_scope(
            owner_id=owner_id,
            scope_kind=self.key_group_scope_kind,
            scope_id=resolved.group.id,
        )

    def has(self, owner_id: str, card_id: str) -> bool:
        if self.has_scope(
            owner_id=owner_id,
            scope_kind=self.character_scope_kind,
            scope_id=card_id,
        ):
            return True
        resolved = KeyGroupRepository(self.repository.database).resolve(
            owner_id=owner_id,
            character_card_id=card_id,
            capability="character",
        )
        return bool(
            resolved
            and self.has_scope(
                owner_id=owner_id,
                scope_kind=self.key_group_scope_kind,
                scope_id=resolved.group.id,
            )
        )

    def delete(self, owner_id: str, card_id: str) -> None:
        """Delete only the per-card override; a Key Group assignment remains reusable."""

        self.delete_scope(
            owner_id=owner_id,
            scope_kind=self.character_scope_kind,
            scope_id=card_id,
            actor_user_id=owner_id,
            resource_type="character_card",
        )

    def set_scope(
        self,
        *,
        owner_id: str,
        scope_kind: str,
        scope_id: str,
        value: SecretStr,
        actor_user_id: str,
        resource_type: str,
    ) -> None:
        cipher = self._require_cipher()
        encrypted = cipher.encrypt(value.get_secret_value().encode("utf-8")).decode("ascii")
        self.repository.save_credential(
            owner_id=owner_id,
            scope_kind=scope_kind,
            scope_id=scope_id,
            encrypted_value=encrypted,
            key_version=self._primary_version,
        )
        self.repository.audit(
            actor_user_id=actor_user_id,
            action="credential.configured",
            resource_type=resource_type,
            resource_id=scope_id,
            metadata={
                "scope_kind": scope_kind,
                "key_version": self._primary_version,
            },
        )

    def get_scope(
        self,
        *,
        owner_id: str,
        scope_kind: str,
        scope_id: str,
    ) -> SecretStr | None:
        record = self.repository.get_credential(
            owner_id=owner_id,
            scope_kind=scope_kind,
            scope_id=scope_id,
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

    def has_scope(
        self,
        *,
        owner_id: str,
        scope_kind: str,
        scope_id: str,
    ) -> bool:
        if not self.configured:
            return False
        return (
            self.repository.get_credential(
                owner_id=owner_id,
                scope_kind=scope_kind,
                scope_id=scope_id,
            )
            is not None
        )

    def delete_scope(
        self,
        *,
        owner_id: str,
        scope_kind: str,
        scope_id: str,
        actor_user_id: str,
        resource_type: str,
    ) -> None:
        self.repository.delete_credential(
            owner_id=owner_id,
            scope_kind=scope_kind,
            scope_id=scope_id,
        )
        self.repository.audit(
            actor_user_id=actor_user_id,
            action="credential.deleted",
            resource_type=resource_type,
            resource_id=scope_id,
            metadata={"scope_kind": scope_kind},
        )

    def rotate_all(self, *, actor_user_id: str | None = None) -> int:
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
        if actor_user_id is not None:
            self.repository.audit(
                actor_user_id=actor_user_id,
                action="credential.rotation_completed",
                resource_type="credential_vault",
                metadata={
                    "rotated_count": rotated,
                    "key_version": self._primary_version,
                },
            )
        return rotated

    def _require_cipher(self) -> MultiFernet:
        if self._cipher is None:
            raise CredentialVaultUnavailable(
                "CHARACTER_RELAY_CREDENTIAL_ENCRYPTION_KEYS is required in production."
            )
        return self._cipher

    @staticmethod
    def _version(key: bytes) -> str:
        return hashlib.sha256(key).hexdigest()[:16]
