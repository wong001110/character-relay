"""Admin runtime configuration and encrypted credential resolution."""

from __future__ import annotations

import json
from typing import Literal, cast

from pydantic import SecretStr
from sqlalchemy import func, select

from echo_masque.admin_runtime import (
    AdminRuntimeConfig,
    AgentRuntimeStatus,
    CredentialSource,
    RuntimeStatus,
)
from echo_masque.auth import SYSTEM_RUNTIME_USER_ID
from echo_masque.config import Settings
from echo_masque.credentials import CredentialVault
from echo_masque.persistence import Repository
from echo_masque.persistence.models import UserRecord
from echo_masque.testers import AdaptiveTesterConfig

RuntimeKind = Literal["adaptive", "judge"]


class RuntimeService:
    def __init__(
        self,
        repository: Repository,
        settings: Settings,
        credential_vault: CredentialVault,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.credential_vault = credential_vault

    def config(self) -> AdminRuntimeConfig:
        record = self.repository.get_admin_runtime()
        if record is None:
            return AdminRuntimeConfig()
        try:
            return AdminRuntimeConfig.model_validate(json.loads(record.config_json))
        except (json.JSONDecodeError, ValueError):
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
    ) -> None:
        self.credential_vault.set_scope(
            owner_id=SYSTEM_RUNTIME_USER_ID,
            scope_kind=CredentialVault.runtime_scope_kind,
            scope_id=kind,
            value=value,
            actor_user_id=actor_user_id,
            resource_type="admin_runtime",
        )

    def clear_credential(self, kind: RuntimeKind, *, actor_user_id: str) -> None:
        self.credential_vault.delete_scope(
            owner_id=SYSTEM_RUNTIME_USER_ID,
            scope_kind=CredentialVault.runtime_scope_kind,
            scope_id=kind,
            actor_user_id=actor_user_id,
            resource_type="admin_runtime",
        )

    def rotate_credentials(self, *, actor_user_id: str) -> int:
        return self.credential_vault.rotate_all(actor_user_id=actor_user_id)

    def credential(self, kind: RuntimeKind) -> tuple[SecretStr | None, CredentialSource]:
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
        environment = (
            self.settings.adaptive_api_key
            if kind == "adaptive"
            else self.settings.judge_api_key
        )
        if environment is not None and environment.get_secret_value():
            return environment, "environment"
        return None, "missing"

    def status(self) -> RuntimeStatus:
        config = self.config()
        adaptive_key, adaptive_source = self.credential("adaptive")
        judge_key, judge_source = self.credential("judge")
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
                credential_source=cast(CredentialSource, adaptive_source),
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
                credential_source=cast(CredentialSource, judge_source),
            ),
            default_judge_mode=config.default_judge_mode,
        )

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
