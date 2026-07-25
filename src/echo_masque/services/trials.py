"""Application service for persisted trial execution."""

import json

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

    def start(self, *, target_id: str, suite: list[TestKind]) -> str:
        target = self.repository.get_target(target_id)
        if target is None:
            raise KeyError(target_id)
        run = self.repository.create_run(
            target_id=target_id,
            suite=[item.value for item in suite],
        )
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
        try:
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
            result = await self.runner.run_suite(target, scenarios)
            latest = self.repository.get_run(run_id)
            if latest and latest.status != TrialStatus.CANCELLED.value:
                self.repository.save_result(run_id, result)
        except (ProviderError, ValueError, KeyError) as exc:
            self.repository.set_run_status(run_id, TrialStatus.FAILED, error=str(exc))

    def cancel(self, run_id: str) -> bool:
        run = self.repository.get_run(run_id)
        if run is None:
            raise KeyError(run_id)
        if run.status in {TrialStatus.COMPLETED.value, TrialStatus.FAILED.value}:
            return False
        self.repository.set_run_status(run_id, TrialStatus.CANCELLED)
        return True
