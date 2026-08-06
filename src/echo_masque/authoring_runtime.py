"""Admin-managed AI authoring runtime and encrypted credential resolution."""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from echo_masque.admin_runtime import CredentialSource, ProviderId
from echo_masque.auth import SYSTEM_RUNTIME_USER_ID
from echo_masque.config import Settings
from echo_masque.credentials import CredentialVault
from echo_masque.persistence import AuthRepository, Database
from echo_masque.persistence.authoring_models import AuthoringRuntimeRecord
from echo_masque.providers import OpenAICompatibleProvider

AUTHORING_DEFAULTS_VERSION = 2

DEFAULT_AUTHORING_PROMPT = (
    "You are Character Relay's AI authoring assistant. Draft structured, internally "
    "consistent, reviewable Character Cards, Expression definitions, and evaluation "
    "assets from the user's supplied brief. Return only one strict JSON object matching "
    "the requested schema. Never include credentials or treat generated content as approved "
    "ground truth. Every draft must require explicit human review before saving or running."
)


class AuthoringRuntimeConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    enabled: bool = True
    provider: ProviderId = "deepseek"
    base_url: str = Field(default="https://api.deepseek.com", min_length=1, max_length=500)
    model: str = Field(default="deepseek-v4-flash", min_length=1, max_length=200)
    system_prompt: str = Field(
        default=DEFAULT_AUTHORING_PROMPT,
        min_length=1,
        max_length=12000,
    )
    temperature: float = Field(default=0.35, ge=0.0, le=1.2)
    maximum_scenarios: int = Field(default=8, ge=1, le=12)
    defaults_version: int = AUTHORING_DEFAULTS_VERSION


class AuthoringRuntimeStatus(BaseModel):
    model_config = ConfigDict(frozen=True)

    enabled: bool
    configured: bool
    provider: str
    model: str
    credential_source: CredentialSource


class AuthoringRuntimeView(BaseModel):
    config: AuthoringRuntimeConfig
    status: AuthoringRuntimeStatus


class AuthoringCredentialConfigure(BaseModel):
    api_key: SecretStr


class AuthoringRuntimeService:
    credential_scope_id: Literal["authoring"] = "authoring"

    def __init__(
        self,
        database: Database,
        auth_repository: AuthRepository,
        credential_vault: CredentialVault,
        settings: Settings,
    ) -> None:
        self.database = database
        self.auth_repository = auth_repository
        self.credential_vault = credential_vault
        self.settings = settings

    def config(self) -> AuthoringRuntimeConfig:
        with self.database.session() as session:
            record = session.get(AuthoringRuntimeRecord, "default")
            if record is None:
                return AuthoringRuntimeConfig()
            try:
                raw = json.loads(record.config_json)
                if int(raw.get("defaults_version", 0)) < AUTHORING_DEFAULTS_VERSION:
                    raw["enabled"] = True
                    raw["defaults_version"] = AUTHORING_DEFAULTS_VERSION
                    config = AuthoringRuntimeConfig.model_validate(raw)
                    record.config_json = config.model_dump_json()
                    session.commit()
                    return config
                return AuthoringRuntimeConfig.model_validate(raw)
            except (json.JSONDecodeError, TypeError, ValueError):
                return AuthoringRuntimeConfig()

    def save(
        self,
        config: AuthoringRuntimeConfig,
        *,
        actor_user_id: str,
    ) -> AuthoringRuntimeConfig:
        with self.database.session() as session:
            record = session.get(AuthoringRuntimeRecord, "default")
            encoded = config.model_dump_json()
            if record is None:
                record = AuthoringRuntimeRecord(id="default", config_json=encoded)
                session.add(record)
            else:
                record.config_json = encoded
            session.commit()
        self.auth_repository.audit(
            actor_user_id=actor_user_id,
            action="authoring_runtime.updated",
            resource_type="authoring_runtime",
            resource_id="default",
        )
        return config

    def set_credential(self, value: SecretStr, *, actor_user_id: str) -> None:
        self.credential_vault.set_scope(
            owner_id=SYSTEM_RUNTIME_USER_ID,
            scope_kind=CredentialVault.runtime_scope_kind,
            scope_id=self.credential_scope_id,
            value=value,
            actor_user_id=actor_user_id,
            resource_type="authoring_runtime",
        )

    def clear_credential(self, *, actor_user_id: str) -> None:
        self.credential_vault.delete_scope(
            owner_id=SYSTEM_RUNTIME_USER_ID,
            scope_kind=CredentialVault.runtime_scope_kind,
            scope_id=self.credential_scope_id,
            actor_user_id=actor_user_id,
            resource_type="authoring_runtime",
        )

    def credential(self) -> tuple[SecretStr | None, CredentialSource]:
        if self.credential_vault.has_scope(
            owner_id=SYSTEM_RUNTIME_USER_ID,
            scope_kind=CredentialVault.runtime_scope_kind,
            scope_id=self.credential_scope_id,
        ):
            value = self.credential_vault.get_scope(
                owner_id=SYSTEM_RUNTIME_USER_ID,
                scope_kind=CredentialVault.runtime_scope_kind,
                scope_id=self.credential_scope_id,
            )
            if value is not None:
                return value, "vault"
        environment = self.settings.authoring_api_key
        if environment is not None and environment.get_secret_value():
            return environment, "environment"
        return None, "missing"

    def status(self) -> AuthoringRuntimeStatus:
        config = self.config()
        credential, source = self.credential()
        return AuthoringRuntimeStatus(
            enabled=config.enabled,
            configured=bool(
                config.enabled
                and config.base_url
                and config.model
                and config.system_prompt
                and credential is not None
            ),
            provider=config.provider,
            model=config.model,
            credential_source=source,
        )

    def view(self) -> AuthoringRuntimeView:
        return AuthoringRuntimeView(config=self.config(), status=self.status())

    def provider(self) -> OpenAICompatibleProvider | None:
        config = self.config()
        credential, _ = self.credential()
        if not config.enabled or credential is None:
            return None
        return OpenAICompatibleProvider(
            base_url=config.base_url,
            api_key=credential,
            timeout_seconds=45,
            max_retries=1,
        )
