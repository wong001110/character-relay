"""Admin runtime configuration and credential resolution."""

from __future__ import annotations

import json
from typing import Literal

from pydantic import SecretStr

from echo_masque.admin_runtime import (
    AdminRuntimeConfig,
    AgentRuntimeStatus,
    RuntimeCredentialStore,
    RuntimeStatus,
)
from echo_masque.config import Settings
from echo_masque.persistence import Repository
from echo_masque.testers import AdaptiveTesterConfig

RuntimeKind = Literal["adaptive", "judge"]


class RuntimeService:
    def __init__(
        self,
        repository: Repository,
        settings: Settings,
        credential_store: RuntimeCredentialStore | None = None,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.credential_store = credential_store or RuntimeCredentialStore()

    def config(self) -> AdminRuntimeConfig:
        record = self.repository.get_admin_runtime()
        if record is None:
            return AdminRuntimeConfig()
        try:
            return AdminRuntimeConfig.model_validate(json.loads(record.config_json))
        except (json.JSONDecodeError, ValueError):
            return AdminRuntimeConfig()

    def save(self, config: AdminRuntimeConfig) -> AdminRuntimeConfig:
        self.repository.save_admin_runtime(config.model_dump(mode="json"))
        return config

    def set_credential(self, kind: RuntimeKind, value: SecretStr) -> None:
        self.credential_store.set(kind, value)

    def clear_credential(self, kind: RuntimeKind) -> None:
        self.credential_store.delete(kind)

    def credential(self, kind: RuntimeKind) -> tuple[SecretStr | None, str]:
        memory = self.credential_store.get(kind)
        if memory is not None:
            return memory, "memory"
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
            admin_available=(
                self.settings.admin_token is not None
                or self.settings.environment in {"development", "test"}
            ),
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
                credential_source=adaptive_source,  # type: ignore[arg-type]
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
                credential_source=judge_source,  # type: ignore[arg-type]
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
