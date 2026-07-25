"""Application service for persisted trial execution."""

import asyncio
import os
from collections.abc import Callable
from typing import Literal

from pydantic import SecretStr

from echo_masque.credentials import CredentialStore
from echo_masque.domain import TestKind, TestLanguage, TrialStatus
from echo_masque.persistence import (
    Repository,
    decode_trial_request,
    encode_trial_request,
)
from echo_masque.providers import (
    ChatProvider,
    OpenAICompatibleProvider,
    ProviderError,
)
from echo_masque.suites import scenarios_for
from echo_masque.targets import (
    HttpTarget,
    HttpTargetConfig,
    PromptModelConfig,
    PromptModelTarget,
    fragile_target,
    stable_target,
)
from echo_masque.targets.base import TargetAdapter
from echo_masque.testers import AdaptiveTester, AdaptiveTesterConfig
from echo_masque.trials import FAST_PACING, WATCH_PACING, TrialRunner

type ProviderFactory = Callable[[str, SecretStr], ChatProvider]


def default_provider_factory(base_url: str, api_key: SecretStr) -> ChatProvider:
    return OpenAICompatibleProvider(base_url=base_url, api_key=api_key)


class TrialService:
    def __init__(
        self,
        repository: Repository,
        credential_store: CredentialStore | None = None,
        provider_factory: ProviderFactory = default_provider_factory,
    ) -> None:
        self.repository = repository
        self.credential_store = credential_store or CredentialStore()
        self.provider_factory = provider_factory
        self.runner = TrialRunner()
        self._modes: dict[str, Literal["watch", "fast"]] = {}
        self._tester_modes: dict[str, Literal["benchmark", "adaptive"]] = {}
        self._adaptive_configs: dict[str, AdaptiveTesterConfig] = {}
        self._run_credentials: dict[str, SecretStr] = {}

    def start(
        self,
        *,
        suite: list[TestKind],
        target_id: str | None = None,
        character_card_id: str | None = None,
        owner_id: str = "local-user",
        mode: Literal["watch", "fast"] = "fast",
        tester_mode: Literal["benchmark", "adaptive"] = "benchmark",
        adaptive_tester: AdaptiveTesterConfig | None = None,
        test_language: TestLanguage = TestLanguage.ENGLISH,
    ) -> str:
        card_id = character_card_id
        if card_id is not None:
            card = self.repository.get_character_card(card_id, owner_id)
            if card is None:
                raise KeyError(card_id)
            target_id = card.target_id
        if target_id is None:
            raise KeyError("missing-target")

        target_record = self.repository.get_target(target_id)
        if target_record is None:
            raise KeyError(target_id)
        if tester_mode == "adaptive" and adaptive_tester is None:
            raise ValueError("Adaptive Tester configuration is required.")

        credential: SecretStr | None = None
        if target_record.target_kind == "prompt_model":
            config = PromptModelConfig.model_validate_json(target_record.config_json)
            if card_id is not None:
                credential = self.credential_store.get(owner_id, card_id)
            if credential is None:
                environment_key = os.getenv(config.api_key_env)
                if environment_key:
                    credential = SecretStr(environment_key)
            if credential is None:
                raise ValueError(
                    "This prompt-model Character Card needs an API key before testing."
                )

        persisted_suite = encode_trial_request(
            [item.value for item in suite],
            test_language,
        )
        run = self.repository.create_run(
            target_id=target_id,
            suite=persisted_suite,
            character_card_id=card_id,
        )
        self._modes[run.id] = mode
        self._tester_modes[run.id] = tester_mode
        if adaptive_tester is not None:
            self._adaptive_configs[run.id] = adaptive_tester
        if credential is not None:
            self._run_credentials[run.id] = credential
        return run.id

    async def execute(self, run_id: str) -> None:
        mode = self._modes.pop(run_id, "fast")
        tester_mode = self._tester_modes.pop(run_id, "benchmark")
        adaptive_config = self._adaptive_configs.pop(run_id, None)
        credential = self._run_credentials.pop(run_id, None)
        run = self.repository.get_run(run_id)
        if run is None or run.status == TrialStatus.CANCELLED.value:
            return
        target_record = self.repository.get_target(run.target_id)
        if target_record is None:
            self.repository.set_run_status(
                run_id,
                TrialStatus.FAILED,
                error="Target no longer exists.",
            )
            return

        async def observe(event_type: str, payload: dict[str, object]) -> None:
            scenario = payload.get("scenario_id")
            turn = payload.get("turn_index")
            await asyncio.to_thread(
                self.repository.append_trial_event,
                run_id,
                event_type,
                payload,
                scenario_id=scenario if isinstance(scenario, str) else None,
                turn_index=turn if isinstance(turn, int) else None,
            )

        try:
            self.repository.clear_trial_events(run_id)
            self.repository.set_run_status(run_id, TrialStatus.RUNNING)
            target = self._target(
                target_record.target_kind,
                target_record.name,
                target_record.config_json,
                credential,
            )
            adaptive = None
            if tester_mode == "adaptive":
                if adaptive_config is None:
                    raise ValueError("Adaptive Tester configuration is no longer available.")
                adaptive = AdaptiveTester(
                    config=adaptive_config,
                    provider=self.provider_factory(
                        adaptive_config.base_url,
                        adaptive_config.api_key,
                    ),
                )

            suite_values, test_language = decode_trial_request(run.suite_json)
            kinds = [TestKind(item) for item in suite_values]
            scenarios = tuple(
                scenario
                for kind in kinds
                for scenario in scenarios_for(kind, language=test_language)
            )
            pacing = WATCH_PACING if mode == "watch" else FAST_PACING
            result = await self.runner.run_suite(
                target,
                scenarios,
                observer=observe,
                pacing=pacing,
                adaptive_tester=adaptive,
            )
            latest = self.repository.get_run(run_id)
            if latest and latest.status != TrialStatus.CANCELLED.value:
                self.repository.save_result(run_id, result)
        except (ProviderError, ValueError, KeyError) as exc:
            await observe("session_failed", {"message": str(exc)})
            self.repository.set_run_status(run_id, TrialStatus.FAILED, error=str(exc))
        finally:
            self._clear_run_state(run_id)

    def _target(
        self,
        target_kind: str,
        target_name: str,
        config_json: str,
        credential: SecretStr | None,
    ) -> TargetAdapter:
        if target_kind == "stable":
            return stable_target()
        if target_kind == "fragile":
            return fragile_target()
        if target_kind == "http":
            return HttpTarget(
                name=target_name,
                config=HttpTargetConfig.model_validate_json(config_json),
            )
        if target_kind == "prompt_model":
            config = PromptModelConfig.model_validate_json(config_json)
            if credential is None:
                environment_key = os.getenv(config.api_key_env)
                if environment_key:
                    credential = SecretStr(environment_key)
            if credential is None:
                raise ValueError("The provider credential is no longer available.")
            return PromptModelTarget(
                config=config,
                provider=self.provider_factory(config.base_url, credential),
            )
        raise ValueError(f"Unsupported persisted target kind: {target_kind}")

    def cancel(self, run_id: str) -> bool:
        run = self.repository.get_run(run_id)
        if run is None:
            raise KeyError(run_id)
        if run.status in {TrialStatus.COMPLETED.value, TrialStatus.FAILED.value}:
            return False
        self._clear_run_state(run_id)
        self.repository.set_run_status(run_id, TrialStatus.CANCELLED)
        self.repository.append_trial_event(run_id, "session_cancelled", {})
        return True

    def _clear_run_state(self, run_id: str) -> None:
        self._modes.pop(run_id, None)
        self._tester_modes.pop(run_id, None)
        self._adaptive_configs.pop(run_id, None)
        self._run_credentials.pop(run_id, None)
