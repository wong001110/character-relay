"""Resolve reusable Key Group credentials for non-character capabilities."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import SecretStr

from echo_masque.credentials import CredentialVault
from echo_masque.persistence.key_group_repository import KeyGroupRepository


@dataclass(frozen=True)
class ResolvedProviderCredential:
    key_group_id: str
    provider: str
    base_url: str
    model: str
    api_key: SecretStr


class KeyGroupProviderCredentialResolver:
    """Resolve provider metadata + encrypted secret without exposing it through account APIs."""

    def __init__(
        self,
        repository: KeyGroupRepository,
        credential_vault: CredentialVault,
    ) -> None:
        self.repository = repository
        self.credential_vault = credential_vault

    def resolve(
        self,
        *,
        owner_id: str,
        character_card_id: str,
        capability: str,
    ) -> ResolvedProviderCredential | None:
        resolved = self.repository.resolve(
            owner_id=owner_id,
            character_card_id=character_card_id,
            capability=capability,
        )
        if resolved is None:
            return None
        api_key = self.credential_vault.get_scope(
            owner_id=owner_id,
            scope_kind=CredentialVault.key_group_scope_kind,
            scope_id=resolved.group.id,
        )
        if api_key is None:
            return None
        return ResolvedProviderCredential(
            key_group_id=resolved.group.id,
            provider=resolved.group.provider,
            base_url=resolved.group.base_url,
            model=resolved.model,
            api_key=api_key,
        )
