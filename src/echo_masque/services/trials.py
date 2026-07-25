"""Application service for persisted trial execution."""

import asyncio
import json
import os
from typing import Literal

from pydantic import SecretStr

from echo_masque.credentials import CredentialStore
from echo_masque.domain import TestKind, TrialStatus
from echo_masque.persistence import Repository
from echo_masque.providers import (
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
from echo_masque.trials import FAST_PACING, WATCH_PACING, TrialRunner


class TrialService:
    def __init__(
        self,
        repository: Repository,
        credential_store: CredentialStore | None = None,
    ) -> None:
        self.repository = repository
        self.credential_store = credential_store or CredentialStore()
        self.runner = TrialRunner()
        self._modes: dict[str, Literal["watch", "fast"]] = {}
        self._run_credentials: dict[str, SecretStr] = {}

    def start(
        self,
        *,
        suite: list[TestKind],
        target_id: str | None = None,
        character_card_id: str | None = None,
        owner_id: str = "local-user",
        mode: Literal["watch", "fast"] = "fast",
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

        run = self.repository.create_run(
            target_id=target_id,
            suite=[item.value for item in suite],
            character_card_id=card_id,
        )
        self._modes[run.id] = mode
        if credential is not None:
            self._run_credentials[run.id] = credential
        return run.id

    async def execute(self, run_id: str) -> None:
        mode = self._modes.pop(run_id, "fast")
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
            target: TargetAdapter
            if target_record.target_kind == "stable":
                target = stable_target()
            elif target_record.target_kind == "fragile":
                target = fragile_target()
            elif target_record.target_kind == "http":
                target = HttpTarget(
                    name=target_record.name,
                    config=HttpTargetConfig.model_validate_json(target_record.config_json),
                )
            elif target_record.target_kind == "prompt_model":
                config = PromptModelConfig.model_validate_json(target_record.config_json)
                if credential is None:
                    environment_key = os.getenv(config.api_key_env)
                    if environment_key:
                        credential = SecretStr(environment_key)
                if credential is None:
                    raise ValueError("The provider credential is no longer available.")
                provider = OpenAICompatibleProvider(
                    base_url=config.base_url,
                    api_key=credential,
                )
                target = PromptModelTarget(config=config, provider=provider)
            else:
                raise ValueError(
                    f"Unsupported persisted target kind: {target_record.target_kind}"
                )

            kinds = [TestKind(item) for item in json.loads(run.suite_json)]
            scenarios = tuple(
                scenario
                for kind in kinds
                for scenario in scenarios_for(kind)
            )
            pacing = WATCH_PACING if mode == "watch" else FAST_PACING
            result = await self.runner.run_suite(
                target,
                scenarios,
                observer=observe,
                pacing=pacing,
            )
            latest = self.repository.get_run(run_id)
            if latest and latest.status != TrialStatus.CANCELLED.value:
                self.repository.save_result(run_id, result)
        except (ProviderError, ValueError, KeyError) as exc:
            await observe("session_failed", {"message": str(exc)})
            self.repository.set_run_status(run_id, TrialStatus.FAILED, error=str(exc))
        finally:
            self._modes.pop(run_id, None)
            self._run_credentials.pop(run_id, None)

    def cancel(self, run_id: str) -> bool:
        run = self.repository.get_run(run_id)
        if run is None:
            raise KeyError(run_id)
        if run.status in {TrialStatus.COMPLETED.value, TrialStatus.FAILED.value}:
            return False
        self._modes.pop(run_id, None)
        self._run_credentials.pop(run_id, None)
        self.repository.set_run_status(run_id, TrialStatus.CANCELLED)
        self.repository.append_trial_event(run_id, "session_cancelled", {})
        return True
