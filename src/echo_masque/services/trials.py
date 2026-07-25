"""Application service for persisted trial execution."""

import json
from typing import Literal

from echo_masque.domain import TestKind, TrialStatus
from echo_masque.persistence import Repository
from echo_masque.providers import ProviderError
from echo_masque.suites import scenarios_for
from echo_masque.targets import HttpTarget, HttpTargetConfig, fragile_target, stable_target
from echo_masque.trials import TrialRunner


class TrialService:
    def __init__(self, repository: Repository) -> None:
        self.repository = repository
        self.runner = TrialRunner()
        self._modes: dict[str, Literal["watch", "fast"]] = {}

    def start(
        self,
        *,
        suite: list[TestKind],
        target_id: str | None = None,
        character_card_id: str | None = None,
        mode: Literal["watch", "fast"] = "watch",
    ) -> str:
        if character_card_id is not None:
            card = self.repository.get_character_card(character_card_id)
            if card is None:
                raise KeyError(character_card_id)
            target_id = card.target_id
        if target_id is None or self.repository.get_target(target_id) is None:
            raise KeyError(target_id or "missing-target")
        run = self.repository.create_run(
            target_id=target_id,
            suite=[item.value for item in suite],
            character_card_id=character_card_id,
        )
        self._modes[run.id] = mode
        return run.id

    async def execute(self, run_id: str) -> None:
        run = self.repository.get_run(run_id)
        if run is None or run.status == TrialStatus.CANCELLED.value:
            return
        target_record = self.repository.get_target(run.target_id)
        if target_record is None:
            self.repository.set_run_status(
                run_id, TrialStatus.FAILED, error="Target no longer exists."
            )
            return

        async def observe(event_type: str, payload: dict[str, object]) -> None:
            scenario = payload.get("scenario_id")
            turn = payload.get("turn_index")
            self.repository.append_trial_event(
                run_id,
                event_type,
                payload,
                scenario_id=scenario if isinstance(scenario, str) else None,
                turn_index=turn if isinstance(turn, int) else None,
            )

        try:
            self.repository.clear_trial_events(run_id)
            self.repository.set_run_status(run_id, TrialStatus.RUNNING)
            if target_record.target_kind == "stable":
                target = stable_target()
            elif target_record.target_kind == "fragile":
                target = fragile_target()
            elif target_record.target_kind == "http":
                target = HttpTarget(
                    name=target_record.name,
                    config=HttpTargetConfig.model_validate(json.loads(target_record.config_json)),
                )
            else:
                raise ValueError(f"Unsupported persisted target kind: {target_record.target_kind}")
            kinds = [TestKind(item) for item in json.loads(run.suite_json)]
            scenarios = tuple(scenario for kind in kinds for scenario in scenarios_for(kind))
            delay = 0.28 if self._modes.pop(run_id, "fast") == "watch" else 0
            result = await self.runner.run_suite(
                target,
                scenarios,
                observer=observe,
                delay_seconds=delay,
            )
            latest = self.repository.get_run(run_id)
            if latest and latest.status != TrialStatus.CANCELLED.value:
                self.repository.save_result(run_id, result)
        except (ProviderError, ValueError, KeyError) as exc:
            await observe("session_failed", {"message": str(exc)})
            self.repository.set_run_status(run_id, TrialStatus.FAILED, error=str(exc))

    def cancel(self, run_id: str) -> bool:
        run = self.repository.get_run(run_id)
        if run is None:
            raise KeyError(run_id)
        if run.status in {TrialStatus.COMPLETED.value, TrialStatus.FAILED.value}:
            return False
        self.repository.set_run_status(run_id, TrialStatus.CANCELLED)
        self.repository.append_trial_event(run_id, "session_cancelled", {})
        return True
