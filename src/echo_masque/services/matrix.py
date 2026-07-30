"""SQLite-backed Phase 14 Matrix execution, controls, and export."""

from __future__ import annotations

import asyncio
import contextlib
import csv
import io
import json
from copy import deepcopy
from dataclasses import dataclass

from echo_masque.domain import TrialStatus
from echo_masque.matrix import (
    ExportFormat,
    MatrixAnalytics,
    MatrixComparison,
    MatrixCreate,
    MatrixDefinition,
    MatrixLaunch,
    MatrixPreview,
    MatrixStatus,
    MatrixTaskStatus,
    MatrixTaskView,
    MatrixUpdate,
    MatrixView,
    preview_for,
)
from echo_masque.persistence import Repository, WorkspaceRepository
from echo_masque.persistence.matrix_repository import MatrixRepository
from echo_masque.services.trials import TrialService


@dataclass(frozen=True, slots=True)
class MatrixExport:
    content: str
    media_type: str
    filename: str


class MatrixService:
    def __init__(
        self,
        repository: Repository,
        workspace_repository: WorkspaceRepository,
        matrix_repository: MatrixRepository,
        trial_service: TrialService,
    ) -> None:
        self.repository = repository
        self.workspace_repository = workspace_repository
        self.matrix_repository = matrix_repository
        self.trial_service = trial_service
        self._active: set[str] = set()

    def preview(self, owner_id: str, definition: MatrixDefinition) -> MatrixPreview:
        self.matrix_repository.validate_definition(owner_id, definition)
        return preview_for(definition)

    def create(self, owner_id: str, payload: MatrixCreate) -> MatrixView:
        return self.matrix_repository.create_matrix(owner_id, payload)

    def update(
        self, matrix_id: str, owner_id: str, payload: MatrixUpdate
    ) -> MatrixView | None:
        return self.matrix_repository.update_matrix(matrix_id, owner_id, payload)

    def launch(
        self, matrix_id: str, owner_id: str, payload: MatrixLaunch
    ) -> MatrixView:
        matrix = self.matrix_repository.get_matrix(matrix_id, owner_id)
        if matrix is None:
            raise KeyError(matrix_id)
        preview = self.preview(owner_id, matrix.definition)
        if payload.confirmed_task_count != preview.task_count:
            raise ValueError(
                "Matrix confirmation is stale. Preview the combinations again before launch."
            )
        runtime = self.trial_service.runtime_service.status()
        if preview.requires_adaptive and not runtime.adaptive.configured:
            raise ValueError("Adaptive Tester is not ready in Admin Runtime.")
        if preview.requires_semantic and not runtime.judge.configured:
            raise ValueError("Semantic Judge is not ready in Admin Runtime.")
        return self.matrix_repository.create_tasks(matrix_id, owner_id)

    async def run_matrix(self, matrix_id: str) -> None:
        if matrix_id in self._active:
            return
        self._active.add(matrix_id)
        try:
            matrix = self.matrix_repository.get_matrix(matrix_id)
            if matrix is None:
                return
            while self.matrix_repository.matrix_should_run(matrix_id):
                self.matrix_repository.mark_matrix_running(matrix_id)
                pending = self.matrix_repository.pending_tasks(
                    matrix_id,
                    matrix.definition.concurrency,
                )
                if not pending:
                    break
                await asyncio.gather(*(self._run_task(task) for task in pending))
                matrix = self.matrix_repository.get_matrix(matrix_id)
                if matrix is None or matrix.status in {
                    MatrixStatus.PAUSED,
                    MatrixStatus.CANCELLED,
                }:
                    break
            self.matrix_repository.finalize_matrix(matrix_id)
        finally:
            self._active.discard(matrix_id)

    async def _run_task(self, task: MatrixTaskView) -> None:
        if not self.matrix_repository.matrix_should_run(task.matrix_id):
            return
        running = self.matrix_repository.mark_task_running(task.id)
        combination = running.combination
        try:
            run_id = self.trial_service.start(
                suite=[],
                character_card_id=combination.character_card_id,
                test_pack_id=combination.test_pack_id,
                owner_id=self._owner_for_matrix(task.matrix_id),
                mode="fast",
                tester_mode=combination.tester_mode,
                judge_mode=combination.judge_mode,
                test_language=combination.test_language,
            )
            self.matrix_repository.bind_task_run(task.id, run_id)
            self._apply_task_snapshot(run_id, combination)
            await self.trial_service.execute(run_id)
            latest_tasks = self.matrix_repository.list_tasks(
                task.matrix_id,
                self._owner_for_matrix(task.matrix_id),
            )
            latest_task = next(
                (item for item in latest_tasks or [] if item.id == task.id),
                None,
            )
            if latest_task is not None and latest_task.status == MatrixTaskStatus.CANCELLED:
                return
            run = self.repository.get_run(run_id)
            if run is None:
                raise ValueError("Matrix Trial disappeared before completion.")
            if run.status == TrialStatus.COMPLETED.value:
                self.matrix_repository.complete_task(task.id)
                return
            error = run.error or f"Trial ended as {run.status}."
            retry = self.matrix_repository.fail_or_retry_task(task.id, error)
            if retry:
                refreshed = self.matrix_repository.list_tasks(
                    task.matrix_id,
                    self._owner_for_matrix(task.matrix_id),
                )
                waiting = next(
                    (item for item in refreshed or [] if item.id == task.id),
                    None,
                )
                if waiting is not None and waiting.backoff_seconds:
                    await asyncio.sleep(waiting.backoff_seconds)
        except (KeyError, ValueError) as exc:
            retry = self.matrix_repository.fail_or_retry_task(task.id, str(exc))
            if retry:
                await asyncio.sleep(min(30, 2 ** max(0, running.attempt_count - 1)))

    def _apply_task_snapshot(self, run_id: str, combination: object) -> None:
        from echo_masque.matrix import MatrixTaskCombination

        resolved = MatrixTaskCombination.model_validate(combination)
        owner_id = self._owner_for_matrix_task(resolved, run_id)
        snapshot = self.workspace_repository.get_run_snapshot(run_id, owner_id)
        if snapshot is None:
            raise ValueError("Matrix Run snapshot was not created.")
        target = deepcopy(snapshot.target)
        character = deepcopy(snapshot.character)
        config_value = target.get("config")
        config = dict(config_value) if isinstance(config_value, dict) else {}
        version = None
        if resolved.prompt_version_id is not None:
            version = self.matrix_repository.get_prompt_version(
                resolved.prompt_version_id,
                owner_id,
            )
            if version is None:
                raise ValueError("Selected Prompt version is no longer available.")
            config.update(
                {
                    "provider": version.provider,
                    "base_url": version.base_url,
                    "model": version.model,
                    "system_prompt": version.system_prompt,
                    "temperature": version.temperature,
                }
            )
            character["prompt_version_id"] = version.id
            character["prompt_version"] = version.version
            character["prompt_version_label"] = version.label
        if resolved.model_override is not None:
            config["model"] = resolved.model_override
        if resolved.temperature is not None:
            config["temperature"] = resolved.temperature
        target["config"] = config
        character["matrix_override"] = {
            "model": resolved.model_override,
            "temperature": resolved.temperature,
            "repeat_index": resolved.repeat_index,
        }
        self.workspace_repository.save_run_snapshot(
            run_id=run_id,
            owner_id=owner_id,
            character_card_id=snapshot.character_card_id,
            test_pack_id=snapshot.test_pack_id,
            character=character,
            target=target,
            test_pack=snapshot.test_pack,
            scenarios=snapshot.scenarios,
            rerun_of=snapshot.rerun_of,
        )

    def _owner_for_matrix(self, matrix_id: str) -> str:
        matrix = self.matrix_repository.get_matrix(matrix_id)
        if matrix is None:
            raise KeyError(matrix_id)
        return matrix.owner_id

    def _owner_for_matrix_task(self, combination: object, run_id: str) -> str:
        from echo_masque.matrix import MatrixTaskCombination

        resolved = MatrixTaskCombination.model_validate(combination)
        snapshot = self.workspace_repository.get_run_snapshot(run_id)
        if snapshot is not None:
            return snapshot.owner_id
        card = self.repository.get_character_card(resolved.character_card_id)
        if card is None:
            raise KeyError(resolved.character_card_id)
        return card.owner_id

    def pause(self, matrix_id: str, owner_id: str) -> MatrixView | None:
        return self.matrix_repository.pause_matrix(matrix_id, owner_id)

    def resume(self, matrix_id: str, owner_id: str) -> MatrixView | None:
        return self.matrix_repository.resume_matrix(matrix_id, owner_id)

    def cancel(self, matrix_id: str, owner_id: str) -> MatrixView | None:
        tasks = self.matrix_repository.list_tasks(matrix_id, owner_id)
        if tasks is None:
            return None
        for task in tasks:
            if task.status == MatrixTaskStatus.RUNNING and task.run_id is not None:
                with contextlib.suppress(KeyError):
                    self.trial_service.cancel(task.run_id)
        return self.matrix_repository.cancel_matrix(matrix_id, owner_id)

    def retry_failed(self, matrix_id: str, owner_id: str) -> MatrixView | None:
        return self.matrix_repository.retry_failed(matrix_id, owner_id)

    def analytics(self, matrix_id: str, owner_id: str) -> MatrixAnalytics | None:
        return self.matrix_repository.analytics(matrix_id, owner_id)

    def compare(
        self, baseline_id: str, candidate_id: str, owner_id: str
    ) -> MatrixComparison | None:
        return self.matrix_repository.compare(baseline_id, candidate_id, owner_id)

    def export(
        self, matrix_id: str, owner_id: str, export_format: ExportFormat
    ) -> MatrixExport | None:
        matrix = self.matrix_repository.get_matrix(matrix_id, owner_id)
        tasks = self.matrix_repository.list_tasks(matrix_id, owner_id)
        analytics = self.matrix_repository.analytics(matrix_id, owner_id)
        if matrix is None or tasks is None or analytics is None:
            return None
        safe_name = "".join(
            character if character.isalnum() or character in {"-", "_"} else "-"
            for character in matrix.name
        ).strip("-") or "echo-masque-matrix"
        if export_format == "json":
            content = json.dumps(
                {
                    "matrix": matrix.model_dump(mode="json"),
                    "analytics": analytics.model_dump(mode="json"),
                    "tasks": [item.model_dump(mode="json") for item in tasks],
                },
                ensure_ascii=False,
                indent=2,
            )
            return MatrixExport(content, "application/json", f"{safe_name}.json")
        if export_format == "csv":
            stream = io.StringIO()
            writer = csv.writer(stream)
            writer.writerow(
                [
                    "ordinal",
                    "status",
                    "character_card_id",
                    "prompt_version_id",
                    "model",
                    "temperature",
                    "test_pack_id",
                    "language",
                    "tester_mode",
                    "judge_mode",
                    "repeat",
                    "run_id",
                    "attempts",
                    "retries",
                    "error",
                ]
            )
            for task in tasks:
                item = task.combination
                writer.writerow(
                    [
                        task.ordinal,
                        task.status.value,
                        item.character_card_id,
                        item.prompt_version_id or "",
                        item.model_override or "current",
                        item.temperature if item.temperature is not None else "current",
                        item.test_pack_id,
                        item.test_language.value,
                        item.tester_mode,
                        item.judge_mode.value,
                        item.repeat_index,
                        task.run_id or "",
                        task.attempt_count,
                        task.retry_count,
                        task.error or "",
                    ]
                )
            return MatrixExport(stream.getvalue(), "text/csv", f"{safe_name}.csv")
        lines = [
            f"# {matrix.name}",
            "",
            matrix.description,
            "",
            f"- Status: **{matrix.status.value}**",
            f"- Tasks: **{matrix.total_tasks}**",
            f"- Completed runs: **{analytics.completed_runs}**",
            f"- Mean score: **{_display(analytics.mean_score)}**",
            f"- Pass rate: **{analytics.pass_rate:.1%}**",
            f"- Review rate: **{analytics.review_rate:.1%}**",
            f"- Failure rate: **{analytics.failure_rate:.1%}**",
            f"- Input tokens: **{analytics.input_tokens}**",
            f"- Output tokens: **{analytics.output_tokens}**",
            f"- Total latency: **{analytics.latency_ms} ms**",
            "",
            "## Variants",
            "",
            "| Variant | Runs | Mean | Pass | Review | Failure |",
            "|---|---:|---:|---:|---:|---:|",
        ]
        variants = (
            analytics.by_temperature
            + analytics.by_model
            + analytics.by_language
        )
        for variant in variants:
            lines.append(
                f"| {variant.label} | {variant.run_count} | "
                f"{_display(variant.mean_score)} | {variant.pass_rate:.1%} | "
                f"{variant.review_rate:.1%} | {variant.failure_rate:.1%} |"
            )
        return MatrixExport("\n".join(lines), "text/markdown", f"{safe_name}.md")


def _display(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}"
