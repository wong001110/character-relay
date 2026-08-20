"""Admin runtime configuration and encrypted credential resolution."""

from __future__ import annotations

import json
from typing import Literal

from pydantic import SecretStr
from sqlalchemy import func, select

from echo_masque.admin_runtime import (
    RUNTIME_DEFAULTS_VERSION,
    AdminRuntimeConfig,
    AgentRuntimeStatus,
    CredentialSource,
    RuntimeCredentialStore,
    RuntimeStatus,
    SemanticJudgeEndpoint,
    SemanticRoutingJudgeProfile,
)
from echo_masque.auth import SYSTEM_RUNTIME_USER_ID
from echo_masque.config import Settings
from echo_masque.credentials import CredentialVault
from echo_masque.persistence import AuthRepository, Repository
from echo_masque.persistence.models import UserRecord
from echo_masque.provider_capabilities import ProviderModelCapabilityRegistry
from echo_masque.provider_capability_persistence import ProviderCapabilityPersistence
from echo_masque.testers import AdaptiveTesterConfig

RuntimeKind = Literal[
    "adaptive",
    "judge",
    "semantic_primary",
    "semantic_availability",
    "semantic_quality",
]
SemanticCredentialKind = Literal[
    "semantic_primary",
    "semantic_availability",
    "semantic_quality",
]


class RuntimeService:
    def __init__(
        self,
        repository: Repository,
        settings: Settings,
        credential_vault: CredentialVault | None = None,
        legacy_store: RuntimeCredentialStore | None = None,
    ) -> None:
        self.repository = repository
        self.settings = settings
        ProviderModelCapabilityRegistry.configure_persistence(
            ProviderCapabilityPersistence(repository.database)
        )
        self.credential_vault = credential_vault or CredentialVault(
            AuthRepository(repository.database),
            settings,
        )
        self.legacy_store = legacy_store or RuntimeCredentialStore()

    def config(self) -> AdminRuntimeConfig:
        record = self.repository.get_admin_runtime()
        if record is None:
            return AdminRuntimeConfig()
        try:
            raw = json.loads(record.config_json)
            if int(raw.get("defaults_version", 0)) < RUNTIME_DEFAULTS_VERSION:
                adaptive = dict(raw.get("adaptive") or {})
                judge = dict(raw.get("judge") or {})
                adaptive["enabled"] = True
                judge["enabled"] = True
                raw["adaptive"] = adaptive
                raw["judge"] = judge
                raw["default_judge_mode"] = "hybrid"
                raw["defaults_version"] = RUNTIME_DEFAULTS_VERSION
                config = AdminRuntimeConfig.model_validate(raw)
                self.repository.save_admin_runtime(config.model_dump(mode="json"))
                return config
            return AdminRuntimeConfig.model_validate(raw)
        except (json.JSONDecodeError, TypeError, ValueError):
            return AdminRuntimeConfig()

    def save(
        self,
        config: AdminRuntimeConfig,
        *,
        actor_user_id: str | None = None,
    ) -> AdminRuntimeConfig:
        self.repository.save_admin_runtime(config.model_dump(mode="json"))
        if actor_user_id is not None:
            self.credential_vault.repository.audit(
                actor_user_id=actor_user_id,
                action="admin_runtime.updated",
                resource_type="admin_runtime",
                resource_id="default",
            )
        return config

    def set_credential(
        self,
        kind: RuntimeKind,
        value: SecretStr,
        *,
        actor_user_id: str,
        legacy: bool = False,
    ) -> None:
        if legacy and self._legacy_allowed:
            self.legacy_store.set(kind, value)
            return
        self.credential_vault.set_scope(
            owner_id=SYSTEM_RUNTIME_USER_ID,
            scope_kind=CredentialVault.runtime_scope_kind,
            scope_id=kind,
            value=value,
            actor_user_id=actor_user_id,
            resource_type="admin_runtime",
        )

    def clear_credential(
        self,
        kind: RuntimeKind,
        *,
        actor_user_id: str,
        legacy: bool = False,
    ) -> None:
        if legacy and self._legacy_allowed:
            self.legacy_store.delete(kind)
            return
        self.credential_vault.delete_scope(
            owner_id=SYSTEM_RUNTIME_USER_ID,
            scope_kind=CredentialVault.runtime_scope_kind,
            scope_id=kind,
            actor_user_id=actor_user_id,
            resource_type="admin_runtime",
        )

    def rotate_credentials(self, *, actor_user_id: str) -> int:
        return self.credential_vault.rotate_all(actor_user_id=actor_user_id)

    def credential(
        self,
        kind: RuntimeKind,
    ) -> tuple[SecretStr | None, CredentialSource]:
        legacy = self.legacy_store.get(kind)
        if legacy is not None and self._legacy_allowed:
            return legacy, "memory"
        if self.credential_vault.has_scope(
            owner_id=SYSTEM_RUNTIME_USER_ID,
            scope_kind=CredentialVault.runtime_scope_kind,
            scope_id=kind,
        ):
            value = self.credential_vault.get_scope(
                owner_id=SYSTEM_RUNTIME_USER_ID,
                scope_kind=CredentialVault.runtime_scope_kind,
                scope_id=kind,
            )
            if value is not None:
                return value, "vault"
        environment: SecretStr | None = None
        if kind == "adaptive":
            environment = self.settings.adaptive_api_key
        elif kind == "judge":
            environment = self.settings.judge_api_key
        if environment is not None and environment.get_secret_value():
            return environment, "environment"
        return None, "missing"

    def semantic_credential(
        self,
        kind: SemanticCredentialKind,
    ) -> tuple[SecretStr | None, CredentialSource]:
        value, source = self.credential(kind)
        if value is not None:
            return value, source
        if kind != "semantic_primary":
            value, source = self.credential("semantic_primary")
            if value is not None:
                return value, source
        return self.credential("judge")

    @staticmethod
    def _endpoint_status(
        *,
        enabled: bool,
        endpoint: SemanticJudgeEndpoint,
        credential: SecretStr | None,
        source: CredentialSource,
    ) -> AgentRuntimeStatus:
        return AgentRuntimeStatus(
            enabled=enabled,
            configured=bool(
                enabled
                and endpoint.base_url
                and endpoint.model
                and credential is not None
            ),
            provider=endpoint.provider,
            model=endpoint.model,
            credential_source=source,
        )

    def status(self) -> RuntimeStatus:
        config = self.config()
        adaptive_key, adaptive_source = self.credential("adaptive")
        judge_key, judge_source = self.credential("judge")
        primary_key, primary_source = self.semantic_credential("semantic_primary")
        availability_key, availability_source = self.semantic_credential(
            "semantic_availability"
        )
        quality_key, quality_source = self.semantic_credential("semantic_quality")
        semantic_enabled = (
            config.semantic_routing.enabled and config.semantic_routing.rag_enabled
        )
        return RuntimeStatus(
            admin_available=self._has_interactive_admin(),
            adaptive=AgentRuntimeStatus(
                enabled=config.adaptive.enabled,
                configured=bool(
                    config.adaptive.enabled
                    and config.adaptive.base_url
                    and config.adaptive.model
                    and config.adaptive.system_prompt
                    and adaptive_key is not None
                ),
                provider=config.adaptive.provider,
                model=config.adaptive.model,
                credential_source=adaptive_source,
            ),
            judge=AgentRuntimeStatus(
                enabled=config.judge.enabled,
                configured=bool(
                    config.judge.enabled
                    and config.judge.base_url
                    and config.judge.model
                    and config.judge.system_prompt
                    and judge_key is not None
                ),
                provider=config.judge.provider,
                model=config.judge.model,
                credential_source=judge_source,
            ),
            semantic_primary=self._endpoint_status(
                enabled=semantic_enabled,
                endpoint=config.semantic_routing.primary,
                credential=primary_key,
                source=primary_source,
            ),
            semantic_availability=self._endpoint_status(
                enabled=semantic_enabled,
                endpoint=config.semantic_routing.availability_fallback,
                credential=availability_key,
                source=availability_source,
            ),
            semantic_quality=self._endpoint_status(
                enabled=semantic_enabled,
                endpoint=config.semantic_routing.quality_escalation,
                credential=quality_key,
                source=quality_source,
            ),
            default_judge_mode=config.default_judge_mode,
        )

    def semantic_routing_config(self) -> SemanticRoutingJudgeProfile:
        return self.config().semantic_routing

    def adaptive_config(self) -> AdaptiveTesterConfig | None:
        config = self.config().adaptive
        key, _ = self.credential("adaptive")
        if not config.enabled or key is None:
            return None
        return AdaptiveTesterConfig(
            provider=config.provider,
            base_url=config.base_url,
            model=config.model,
            system_prompt=config.system_prompt,
            temperature=config.temperature,
            max_turns=config.max_turns,
            api_key=key,
        )

    @property
    def _legacy_allowed(self) -> bool:
        return (
            self.settings.environment != "production"
            and self.settings.legacy_local_user_enabled
        )

    def _has_interactive_admin(self) -> bool:
        with self.repository.database.session() as session:
            count = session.scalar(
                select(func.count())
                .select_from(UserRecord)
                .where(
                    UserRecord.role == "admin",
                    UserRecord.is_active.is_(True),
                    UserRecord.id != SYSTEM_RUNTIME_USER_ID,
                )
            )
            return bool(count)
