"""Persistence, prompt versioning, task expansion, and analytics for Phase 14."""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from collections import Counter, defaultdict
from datetime import UTC, datetime
from itertools import product
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import delete, func, select, update

from echo_masque.domain import TrialSuiteResult
from echo_masque.matrix import (
    MAX_MATRIX_TASKS,
    DistributionItem,
    MatrixAnalytics,
    MatrixComparison,
    MatrixCreate,
    MatrixDefinition,
    MatrixListPage,
    MatrixStatus,
    MatrixTaskCombination,
    MatrixTaskStatus,
    MatrixTaskView,
    MatrixUpdate,
    MatrixVariantAnalytics,
    MatrixView,
    PromptVersionDiff,
    PromptVersionView,
    preview_for,
)
from echo_masque.persistence.database import Database
from echo_masque.persistence.models import (
    CharacterCardRecord,
    ExperimentMatrixRecord,
    ExperimentMatrixTaskRecord,
    PromptVersionRecord,
    TargetRecord,
    TestPackRecord,
    TrialRunRecord,
)
from echo_masque.targets import PromptModelConfig


class MatrixRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    # Prompt versions
    def capture_prompt_version(
        self,
        owner_id: str,
        character_card_id: str,
        *,
        label: str = "",
    ) -> PromptVersionView | None:
        with self.database.session() as session:
            card = session.get(CharacterCardRecord, character_card_id)
            if card is None or card.owner_id != owner_id:
                return None
            target = session.get(TargetRecord, card.target_id)
            if target is None or target.target_kind != "prompt_model":
                return None
            config = PromptModelConfig.model_validate_json(target.config_json)
            digest = _config_hash(config)
            existing = session.scalar(
                select(PromptVersionRecord).where(
                    PromptVersionRecord.owner_id == owner_id,
                    PromptVersionRecord.character_card_id == character_card_id,
                    PromptVersionRecord.config_hash == digest,
                )
            )
            versions = list(
                session.scalars(
                    select(PromptVersionRecord).where(
                        PromptVersionRecord.owner_id == owner_id,
                        PromptVersionRecord.character_card_id == character_card_id,
                    )
                )
            )
            for item in versions:
                item.is_active = False
            if existing is not None:
                existing.is_active = True
                if label.strip():
                    existing.label = label.strip()
                session.commit()
                session.refresh(existing)
                return self._prompt_view(existing)
            latest = session.scalar(
                select(func.max(PromptVersionRecord.version)).where(
                    PromptVersionRecord.owner_id == owner_id,
                    PromptVersionRecord.character_card_id == character_card_id,
                )
            )
            version = PromptVersionRecord(
                id=str(uuid4()),
                owner_id=owner_id,
                character_card_id=character_card_id,
                version=int(latest or 0) + 1,
                label=label.strip() or f"Version {int(latest or 0) + 1}",
                provider=config.provider,
                base_url=config.base_url,
                model=config.model,
                system_prompt=config.system_prompt,
                temperature=config.temperature,
                config_hash=digest,
                is_active=True,
                is_production=False,
            )
            session.add(version)
            session.commit()
            session.refresh(version)
            return self._prompt_view(version)

    def list_prompt_versions(
        self, owner_id: str, character_card_id: str
    ) -> list[PromptVersionView] | None:
        current = self.capture_prompt_version(owner_id, character_card_id)
        with self.database.session() as session:
            card = session.get(CharacterCardRecord, character_card_id)
            if card is None or card.owner_id != owner_id:
                return None
            target = session.get(TargetRecord, card.target_id)
            if target is None or target.target_kind != "prompt_model":
                return []
            records = session.scalars(
                select(PromptVersionRecord)
                .where(
                    PromptVersionRecord.owner_id == owner_id,
                    PromptVersionRecord.character_card_id == character_card_id,
                )
                .order_by(PromptVersionRecord.version.desc())
            )
            views = [self._prompt_view(item) for item in records]
            if current is not None and not views:
                return [current]
            return views

    def get_prompt_version(
        self, version_id: str, owner_id: str | None = None
    ) -> PromptVersionView | None:
        with self.database.session() as session:
            record = session.get(PromptVersionRecord, version_id)
            if record is None or (owner_id is not None and record.owner_id != owner_id):
                return None
            return self._prompt_view(record)

    def restore_prompt_version(
        self, owner_id: str, character_card_id: str, version_id: str
    ) -> PromptVersionView | None:
        with self.database.session() as session:
            card = session.get(CharacterCardRecord, character_card_id)
            version = session.get(PromptVersionRecord, version_id)
            if (
                card is None
                or card.owner_id != owner_id
                or version is None
                or version.owner_id != owner_id
                or version.character_card_id != character_card_id
            ):
                return None
            target = session.get(TargetRecord, card.target_id)
            if target is None or target.target_kind != "prompt_model":
                return None
            current = PromptModelConfig.model_validate_json(target.config_json)
            restored = PromptModelConfig(
                name=card.display_name,
                provider=version.provider,
                base_url=version.base_url,
                model=version.model,
                system_prompt=version.system_prompt,
                temperature=version.temperature,
                api_key_env=current.api_key_env,
            )
            target.name = card.display_name
            target.config_json = restored.model_dump_json()
            versions = list(
                session.scalars(
                    select(PromptVersionRecord).where(
                        PromptVersionRecord.owner_id == owner_id,
                        PromptVersionRecord.character_card_id == character_card_id,
                    )
                )
            )
            for item in versions:
                item.is_active = item.id == version_id
            session.commit()
            session.refresh(version)
            return self._prompt_view(version)

    def set_production_version(
        self,
        owner_id: str,
        character_card_id: str,
        version_id: str,
        value: bool,
    ) -> PromptVersionView | None:
        with self.database.session() as session:
            version = session.get(PromptVersionRecord, version_id)
            if (
                version is None
                or version.owner_id != owner_id
                or version.character_card_id != character_card_id
            ):
                return None
            if value:
                session.execute(
                    update(PromptVersionRecord)
                    .where(
                        PromptVersionRecord.owner_id == owner_id,
                        PromptVersionRecord.character_card_id == character_card_id,
                    )
                    .values(is_production=False)
                )
            version.is_production = value
            session.commit()
            session.refresh(version)
            return self._prompt_view(version)

    def prompt_version_diff(
        self, owner_id: str, left_id: str, right_id: str
    ) -> PromptVersionDiff | None:
        left = self.get_prompt_version(left_id, owner_id)
        right = self.get_prompt_version(right_id, owner_id)
        if left is None or right is None or left.character_card_id != right.character_card_id:
            return None
        fields = ("provider", "base_url", "model", "system_prompt", "temperature")
        changed = [name for name in fields if getattr(left, name) != getattr(right, name)]
        return PromptVersionDiff(
            left=left,
            right=right,
            changed_fields=changed,
            system_prompt_before=left.system_prompt,
            system_prompt_after=right.system_prompt,
        )

    # Matrix CRUD and expansion
    def create_matrix(self, owner_id: str, payload: MatrixCreate) -> MatrixView:
        self.validate_definition(owner_id, payload.definition)
        record = ExperimentMatrixRecord(
            id=str(uuid4()),
            owner_id=owner_id,
            name=payload.name,
            description=payload.description,
            status=MatrixStatus.DRAFT.value,
            definition_json=_definition_json(payload.definition),
        )
        with self.database.session() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
            return self._matrix_view(record)

    def update_matrix(
        self, matrix_id: str, owner_id: str, payload: MatrixUpdate
    ) -> MatrixView | None:
        self.validate_definition(owner_id, payload.definition)
        with self.database.session() as session:
            record = session.get(ExperimentMatrixRecord, matrix_id)
            if record is None or record.owner_id != owner_id:
                return None
            if record.status != MatrixStatus.DRAFT.value:
                raise ValueError("Only draft Matrices can be edited.")
            record.name = payload.name
            record.description = payload.description
            record.definition_json = _definition_json(payload.definition)
            record.updated_at = datetime.now(UTC)
            session.commit()
            session.refresh(record)
            return self._matrix_view(record)

    def get_matrix(self, matrix_id: str, owner_id: str | None = None) -> MatrixView | None:
        with self.database.session() as session:
            record = session.get(ExperimentMatrixRecord, matrix_id)
            if record is None or (owner_id is not None and record.owner_id != owner_id):
                return None
            return self._matrix_view(record)

    def list_matrices(
        self, owner_id: str, *, page: int = 1, page_size: int = 20
    ) -> MatrixListPage:
        with self.database.session() as session:
            total = int(
                session.scalar(
                    select(func.count())
                    .select_from(ExperimentMatrixRecord)
                    .where(ExperimentMatrixRecord.owner_id == owner_id)
                )
                or 0
            )
            pages = max(1, math.ceil(total / page_size))
            safe_page = min(max(1, page), pages)
            records = session.scalars(
                select(ExperimentMatrixRecord)
                .where(ExperimentMatrixRecord.owner_id == owner_id)
                .order_by(ExperimentMatrixRecord.updated_at.desc())
                .offset((safe_page - 1) * page_size)
                .limit(page_size)
            )
            return MatrixListPage(
                items=[self._matrix_view(item) for item in records],
                page=safe_page,
                page_size=page_size,
                total=total,
                pages=pages,
            )

    def delete_matrix(self, matrix_id: str, owner_id: str) -> bool:
        with self.database.session() as session:
            record = session.get(ExperimentMatrixRecord, matrix_id)
            if record is None or record.owner_id != owner_id:
                return False
            if record.status in {MatrixStatus.RUNNING.value, MatrixStatus.QUEUED.value}:
                raise ValueError("A running Matrix must be cancelled before deletion.")
            session.execute(
                delete(ExperimentMatrixTaskRecord).where(
                    ExperimentMatrixTaskRecord.matrix_id == matrix_id
                )
            )
            session.delete(record)
            session.commit()
            return True

    def validate_definition(self, owner_id: str, definition: MatrixDefinition) -> None:
        preview = preview_for(definition)
        if not preview.within_limit:
            raise ValueError(
                f"Matrix expands to {preview.task_count} tasks; the limit is {MAX_MATRIX_TASKS}."
            )
        with self.database.session() as session:
            for subject in definition.subjects:
                card = session.get(CharacterCardRecord, subject.character_card_id)
                if card is None or card.owner_id != owner_id:
                    raise ValueError(f"Character Card not found: {subject.character_card_id}")
                target = session.get(TargetRecord, card.target_id)
                if target is None:
                    raise ValueError(f"Target binding not found for {card.display_name}.")
                if subject.prompt_version_ids and target.target_kind != "prompt_model":
                    raise ValueError(
                        "Prompt versions can only be selected for Prompt + Model cards."
                    )
                for version_id in subject.prompt_version_ids:
                    version = session.get(PromptVersionRecord, version_id)
                    if (
                        version is None
                        or version.owner_id != owner_id
                        or version.character_card_id != card.id
                    ):
                        raise ValueError(f"Prompt version not found: {version_id}")
            for pack_id in definition.test_pack_ids:
                pack = session.get(TestPackRecord, pack_id)
                if pack is None or pack.owner_id != owner_id:
                    raise ValueError(f"Test Pack not found: {pack_id}")

    def create_tasks(self, matrix_id: str, owner_id: str) -> MatrixView:
        matrix = self.get_matrix(matrix_id, owner_id)
        if matrix is None:
            raise KeyError(matrix_id)
        if matrix.status != MatrixStatus.DRAFT:
            raise ValueError("Only a draft Matrix can be launched.")
        combinations = self.expand(matrix.definition, owner_id)
        now = datetime.now(UTC)
        with self.database.session() as session:
            record = session.get(ExperimentMatrixRecord, matrix_id)
            if record is None:
                raise KeyError(matrix_id)
            session.execute(
                delete(ExperimentMatrixTaskRecord).where(
                    ExperimentMatrixTaskRecord.matrix_id == matrix_id
                )
            )
            for index, combination in enumerate(combinations, start=1):
                session.add(
                    ExperimentMatrixTaskRecord(
                        id=str(uuid4()),
                        matrix_id=matrix_id,
                        ordinal=index,
                        status=MatrixTaskStatus.PENDING.value,
                        combination_json=combination.model_dump_json(),
                        max_attempts=matrix.definition.max_attempts,
                    )
                )
            record.status = MatrixStatus.QUEUED.value
            record.total_tasks = len(combinations)
            record.pending_tasks = len(combinations)
            record.running_tasks = 0
            record.completed_tasks = 0
            record.failed_tasks = 0
            record.cancelled_tasks = 0
            record.started_at = now
            record.completed_at = None
            record.updated_at = now
            session.commit()
            session.refresh(record)
            return self._matrix_view(record)

    def expand(
        self, definition: MatrixDefinition, owner_id: str
    ) -> list[MatrixTaskCombination]:
        subject_variants: list[tuple[str, str | None]] = []
        for subject in definition.subjects:
            versions = subject.prompt_version_ids
            if not versions:
                captured = self.capture_prompt_version(owner_id, subject.character_card_id)
                versions = [captured.id] if captured is not None else []
            if versions:
                subject_variants.extend(
                    (subject.character_card_id, version_id) for version_id in versions
                )
            else:
                subject_variants.append((subject.character_card_id, None))
        models: list[str | None] = (
            [*definition.model_overrides]
            if definition.model_overrides
            else [None]
        )
        temperatures: list[float | None] = (
            [*definition.temperatures]
            if definition.temperatures
            else [None]
        )
        combinations: list[MatrixTaskCombination] = []
        for (
            subject_variant,
            model,
            temperature,
            pack_id,
            language,
            tester_mode,
            judge_mode,
            repeat_index,
        ) in product(
            subject_variants,
            models,
            temperatures,
            definition.test_pack_ids,
            definition.test_languages,
            definition.tester_modes,
            definition.judge_modes,
            range(1, definition.repeat_count + 1),
        ):
            combinations.append(
                MatrixTaskCombination(
                    character_card_id=subject_variant[0],
                    prompt_version_id=subject_variant[1],
                    model_override=model,
                    temperature=temperature,
                    test_pack_id=pack_id,
                    test_language=language,
                    tester_mode=tester_mode,
                    judge_mode=judge_mode,
                    repeat_index=repeat_index,
                )
            )
        if len(combinations) > MAX_MATRIX_TASKS:
            raise ValueError("Expanded Matrix exceeds the server task limit.")
        return combinations

    # Task state
    def list_tasks(self, matrix_id: str, owner_id: str) -> list[MatrixTaskView] | None:
        if self.get_matrix(matrix_id, owner_id) is None:
            return None
        with self.database.session() as session:
            records = session.scalars(
                select(ExperimentMatrixTaskRecord)
                .where(ExperimentMatrixTaskRecord.matrix_id == matrix_id)
                .order_by(ExperimentMatrixTaskRecord.ordinal)
            )
            return [self._task_view(item) for item in records]

    def pending_tasks(self, matrix_id: str, limit: int) -> list[MatrixTaskView]:
        with self.database.session() as session:
            records = session.scalars(
                select(ExperimentMatrixTaskRecord)
                .where(
                    ExperimentMatrixTaskRecord.matrix_id == matrix_id,
                    ExperimentMatrixTaskRecord.status == MatrixTaskStatus.PENDING.value,
                )
                .order_by(ExperimentMatrixTaskRecord.ordinal)
                .limit(limit)
            )
            return [self._task_view(item) for item in records]

    def mark_task_running(self, task_id: str) -> MatrixTaskView:
        with self.database.session() as session:
            record = session.get(ExperimentMatrixTaskRecord, task_id)
            if record is None:
                raise KeyError(task_id)
            record.status = MatrixTaskStatus.RUNNING.value
            record.attempt_count += 1
            record.started_at = datetime.now(UTC)
            record.error = None
            session.commit()
            self._refresh_counts(session, record.matrix_id)
            session.commit()
            session.refresh(record)
            return self._task_view(record)

    def bind_task_run(self, task_id: str, run_id: str) -> None:
        with self.database.session() as session:
            record = session.get(ExperimentMatrixTaskRecord, task_id)
            if record is None:
                raise KeyError(task_id)
            record.run_id = run_id
            session.commit()

    def complete_task(self, task_id: str) -> None:
        self._finish_task(task_id, MatrixTaskStatus.COMPLETED, None)

    def fail_or_retry_task(self, task_id: str, error: str) -> bool:
        with self.database.session() as session:
            record = session.get(ExperimentMatrixTaskRecord, task_id)
            if record is None:
                raise KeyError(task_id)
            retry = record.attempt_count < record.max_attempts
            record.status = (
                MatrixTaskStatus.PENDING.value if retry else MatrixTaskStatus.FAILED.value
            )
            record.retry_count += 1 if retry else 0
            record.backoff_seconds = min(30, 2 ** max(0, record.attempt_count - 1)) if retry else 0
            record.error = error
            record.completed_at = None if retry else datetime.now(UTC)
            session.commit()
            self._refresh_counts(session, record.matrix_id)
            session.commit()
            return retry

    def pause_matrix(self, matrix_id: str, owner_id: str) -> MatrixView | None:
        return self._set_matrix_state(
            matrix_id,
            owner_id,
            allowed={MatrixStatus.QUEUED, MatrixStatus.RUNNING},
            status=MatrixStatus.PAUSED,
        )

    def resume_matrix(self, matrix_id: str, owner_id: str) -> MatrixView | None:
        return self._set_matrix_state(
            matrix_id,
            owner_id,
            allowed={MatrixStatus.PAUSED, MatrixStatus.FAILED},
            status=MatrixStatus.QUEUED,
        )

    def cancel_matrix(self, matrix_id: str, owner_id: str) -> MatrixView | None:
        with self.database.session() as session:
            record = session.get(ExperimentMatrixRecord, matrix_id)
            if record is None or record.owner_id != owner_id:
                return None
            session.execute(
                update(ExperimentMatrixTaskRecord)
                .where(
                    ExperimentMatrixTaskRecord.matrix_id == matrix_id,
                    ExperimentMatrixTaskRecord.status.in_(
                        [MatrixTaskStatus.PENDING.value, MatrixTaskStatus.RUNNING.value]
                    ),
                )
                .values(
                    status=MatrixTaskStatus.CANCELLED.value,
                    completed_at=datetime.now(UTC),
                )
            )
            record.status = MatrixStatus.CANCELLED.value
            record.completed_at = datetime.now(UTC)
            session.commit()
            self._refresh_counts(session, matrix_id)
            session.commit()
            session.refresh(record)
            return self._matrix_view(record)

    def retry_failed(self, matrix_id: str, owner_id: str) -> MatrixView | None:
        with self.database.session() as session:
            record = session.get(ExperimentMatrixRecord, matrix_id)
            if record is None or record.owner_id != owner_id:
                return None
            session.execute(
                update(ExperimentMatrixTaskRecord)
                .where(
                    ExperimentMatrixTaskRecord.matrix_id == matrix_id,
                    ExperimentMatrixTaskRecord.status == MatrixTaskStatus.FAILED.value,
                )
                .values(
                    status=MatrixTaskStatus.PENDING.value,
                    attempt_count=0,
                    error=None,
                    completed_at=None,
                )
            )
            record.status = MatrixStatus.QUEUED.value
            record.completed_at = None
            session.commit()
            self._refresh_counts(session, matrix_id)
            session.commit()
            session.refresh(record)
            return self._matrix_view(record)

    def matrix_should_run(self, matrix_id: str) -> bool:
        with self.database.session() as session:
            status = session.scalar(
                select(ExperimentMatrixRecord.status).where(
                    ExperimentMatrixRecord.id == matrix_id
                )
            )
            return status in {MatrixStatus.QUEUED.value, MatrixStatus.RUNNING.value}

    def mark_matrix_running(self, matrix_id: str) -> None:
        with self.database.session() as session:
            record = session.get(ExperimentMatrixRecord, matrix_id)
            if record is None:
                raise KeyError(matrix_id)
            record.status = MatrixStatus.RUNNING.value
            record.started_at = record.started_at or datetime.now(UTC)
            session.commit()

    def finalize_matrix(self, matrix_id: str) -> MatrixView:
        with self.database.session() as session:
            self._refresh_counts(session, matrix_id)
            record = session.get(ExperimentMatrixRecord, matrix_id)
            if record is None:
                raise KeyError(matrix_id)
            if record.pending_tasks or record.running_tasks:
                if record.status not in {
                    MatrixStatus.PAUSED.value,
                    MatrixStatus.CANCELLED.value,
                }:
                    record.status = MatrixStatus.RUNNING.value
            elif record.status != MatrixStatus.CANCELLED.value:
                record.status = (
                    MatrixStatus.FAILED.value
                    if record.failed_tasks and not record.completed_tasks
                    else MatrixStatus.COMPLETED.value
                )
                record.completed_at = datetime.now(UTC)
            session.commit()
            session.refresh(record)
            return self._matrix_view(record)

    def recover_interrupted(self) -> int:
        with self.database.session() as session:
            running_tasks = list(
                session.scalars(
                    select(ExperimentMatrixTaskRecord).where(
                        ExperimentMatrixTaskRecord.status == MatrixTaskStatus.RUNNING.value
                    )
                )
            )
            matrix_ids = {item.matrix_id for item in running_tasks}
            for task in running_tasks:
                task.status = MatrixTaskStatus.PENDING.value
                task.error = "Recovered after application restart."
                task.run_id = None
                task.started_at = None
            running_matrices = list(
                session.scalars(
                    select(ExperimentMatrixRecord).where(
                        ExperimentMatrixRecord.status.in_(
                            [MatrixStatus.RUNNING.value, MatrixStatus.QUEUED.value]
                        )
                    )
                )
            )
            for matrix in running_matrices:
                matrix.status = MatrixStatus.PAUSED.value
                matrix_ids.add(matrix.id)
            session.commit()
            for matrix_id in matrix_ids:
                self._refresh_counts(session, matrix_id)
            session.commit()
            return len(matrix_ids)

    def set_matrix_baseline(
        self, matrix_id: str, owner_id: str, value: bool
    ) -> MatrixView | None:
        with self.database.session() as session:
            record = session.get(ExperimentMatrixRecord, matrix_id)
            if record is None or record.owner_id != owner_id:
                return None
            if value:
                session.execute(
                    update(ExperimentMatrixRecord)
                    .where(ExperimentMatrixRecord.owner_id == owner_id)
                    .values(is_baseline=False)
                )
            record.is_baseline = value
            session.commit()
            session.refresh(record)
            return self._matrix_view(record)

    # Analytics
    def analytics(self, matrix_id: str, owner_id: str) -> MatrixAnalytics | None:
        matrix = self.get_matrix(matrix_id, owner_id)
        tasks = self.list_tasks(matrix_id, owner_id)
        if matrix is None or tasks is None:
            return None
        samples: list[dict[str, Any]] = []
        failure_types: Counter[str] = Counter()
        breakpoints: Counter[str] = Counter()
        provider_errors = 0
        with self.database.session() as session:
            for task in tasks:
                if task.status == MatrixTaskStatus.FAILED:
                    provider_errors += 1
                if task.run_id is None:
                    continue
                run = session.get(TrialRunRecord, task.run_id)
                if run is None or run.result_json is None:
                    continue
                result = TrialSuiteResult.model_validate_json(run.result_json)
                usage = _result_usage(result)
                sample = {
                    "combination": task.combination,
                    "result": result,
                    "score": float(result.average_score),
                    "passed": result.passed,
                    "review": result.review_required,
                    **usage,
                }
                samples.append(sample)
                for item in result.results:
                    if item.verdict.failure_type:
                        for failure in item.verdict.failure_type.split(","):
                            if failure.strip():
                                failure_types[failure.strip()] += 1
                    if item.breakpoint is not None:
                        breakpoints[f"{item.scenario.name} / turn {item.breakpoint}"] += 1
        scores = [float(item["score"]) for item in samples]
        return MatrixAnalytics(
            matrix_id=matrix.id,
            matrix_name=matrix.name,
            status=matrix.status,
            total_tasks=matrix.total_tasks,
            completed_runs=len(samples),
            failed_tasks=matrix.failed_tasks,
            cancelled_tasks=matrix.cancelled_tasks,
            mean_score=_mean(scores),
            minimum_score=min(scores) if scores else None,
            maximum_score=max(scores) if scores else None,
            variance=statistics.pvariance(scores) if len(scores) > 1 else (0.0 if scores else None),
            standard_deviation=(
                statistics.pstdev(scores) if len(scores) > 1 else (0.0 if scores else None)
            ),
            pass_rate=_rate(samples, "passed"),
            review_rate=_rate(samples, "review"),
            failure_rate=_failure_rate(samples),
            input_tokens=sum(int(item["input_tokens"]) for item in samples),
            output_tokens=sum(int(item["output_tokens"]) for item in samples),
            latency_ms=sum(int(item["latency_ms"]) for item in samples),
            provider_errors=provider_errors,
            retry_count=sum(item.retry_count for item in tasks),
            failure_types=_distribution(failure_types),
            breakpoints=_distribution(breakpoints),
            scenarios=_group_scenarios(samples),
            by_character=_group(samples, "character", lambda item: item.character_card_id),
            by_prompt_version=_group(
                samples, "prompt", lambda item: item.prompt_version_id or "current"
            ),
            by_model=_group(samples, "model", lambda item: item.model_override or "current"),
            by_temperature=_group(
                samples,
                "temperature",
                lambda item: str(item.temperature) if item.temperature is not None else "current",
            ),
            by_language=_group(samples, "language", lambda item: item.test_language.value),
            by_tester=_group(samples, "tester", lambda item: item.tester_mode),
            by_judge=_group(samples, "judge", lambda item: item.judge_mode.value),
        )

    def compare(
        self, baseline_id: str, candidate_id: str, owner_id: str
    ) -> MatrixComparison | None:
        baseline_matrix = self.get_matrix(baseline_id, owner_id)
        candidate_matrix = self.get_matrix(candidate_id, owner_id)
        baseline = self.analytics(baseline_id, owner_id)
        candidate = self.analytics(candidate_id, owner_id)
        if (
            baseline_matrix is None
            or candidate_matrix is None
            or baseline is None
            or candidate is None
        ):
            return None
        incompatibilities: list[str] = []
        pairs = (
            (
                "Test Packs",
                baseline_matrix.definition.test_pack_ids,
                candidate_matrix.definition.test_pack_ids,
            ),
            (
                "Languages",
                baseline_matrix.definition.test_languages,
                candidate_matrix.definition.test_languages,
            ),
            (
                "Tester Modes",
                baseline_matrix.definition.tester_modes,
                candidate_matrix.definition.tester_modes,
            ),
            (
                "Judge Modes",
                baseline_matrix.definition.judge_modes,
                candidate_matrix.definition.judge_modes,
            ),
        )
        for label, left, right in pairs:
            if set(left) != set(right):
                incompatibilities.append(label)
        compatible = not incompatibilities
        score_delta = (
            candidate.mean_score - baseline.mean_score
            if candidate.mean_score is not None and baseline.mean_score is not None
            else None
        )
        classification: Literal[
            "improved",
            "no_meaningful_change",
            "regression",
            "incompatible",
        ] = "incompatible"
        if compatible:
            if (
                score_delta is not None
                and score_delta >= 3
                and candidate.pass_rate >= baseline.pass_rate
            ):
                classification = "improved"
            elif score_delta is not None and (
                score_delta <= -3
                or candidate.pass_rate < baseline.pass_rate - 0.05
            ):
                classification = "regression"
            else:
                classification = "no_meaningful_change"
        return MatrixComparison(
            baseline=baseline,
            candidate=candidate,
            compatible=compatible,
            incompatibilities=incompatibilities,
            score_delta=score_delta,
            pass_rate_delta=candidate.pass_rate - baseline.pass_rate,
            review_rate_delta=candidate.review_rate - baseline.review_rate,
            failure_rate_delta=candidate.failure_rate - baseline.failure_rate,
            latency_delta_ms=candidate.latency_ms - baseline.latency_ms,
            input_token_delta=candidate.input_tokens - baseline.input_tokens,
            output_token_delta=candidate.output_tokens - baseline.output_tokens,
            classification=classification,
        )

    # Views and internal state helpers
    @staticmethod
    def _prompt_view(record: PromptVersionRecord) -> PromptVersionView:
        return PromptVersionView(
            id=record.id,
            owner_id=record.owner_id,
            character_card_id=record.character_card_id,
            version=record.version,
            label=record.label,
            provider=record.provider,
            base_url=record.base_url,
            model=record.model,
            system_prompt=record.system_prompt,
            temperature=record.temperature,
            config_hash=record.config_hash,
            is_active=record.is_active,
            is_production=record.is_production,
            created_at=record.created_at,
        )

    @staticmethod
    def _matrix_view(record: ExperimentMatrixRecord) -> MatrixView:
        return MatrixView(
            id=record.id,
            owner_id=record.owner_id,
            name=record.name,
            description=record.description,
            status=MatrixStatus(record.status),
            definition=MatrixDefinition.model_validate_json(record.definition_json),
            total_tasks=record.total_tasks,
            pending_tasks=record.pending_tasks,
            running_tasks=record.running_tasks,
            completed_tasks=record.completed_tasks,
            failed_tasks=record.failed_tasks,
            cancelled_tasks=record.cancelled_tasks,
            is_baseline=record.is_baseline,
            created_at=record.created_at,
            updated_at=record.updated_at,
            started_at=record.started_at,
            completed_at=record.completed_at,
        )

    @staticmethod
    def _task_view(record: ExperimentMatrixTaskRecord) -> MatrixTaskView:
        return MatrixTaskView(
            id=record.id,
            matrix_id=record.matrix_id,
            ordinal=record.ordinal,
            status=MatrixTaskStatus(record.status),
            combination=MatrixTaskCombination.model_validate_json(record.combination_json),
            run_id=record.run_id,
            attempt_count=record.attempt_count,
            max_attempts=record.max_attempts,
            retry_count=record.retry_count,
            backoff_seconds=record.backoff_seconds,
            error=record.error,
            created_at=record.created_at,
            updated_at=record.updated_at,
            started_at=record.started_at,
            completed_at=record.completed_at,
        )

    def _finish_task(
        self, task_id: str, status: MatrixTaskStatus, error: str | None
    ) -> None:
        with self.database.session() as session:
            record = session.get(ExperimentMatrixTaskRecord, task_id)
            if record is None:
                raise KeyError(task_id)
            record.status = status.value
            record.error = error
            record.backoff_seconds = 0
            record.completed_at = datetime.now(UTC)
            session.commit()
            self._refresh_counts(session, record.matrix_id)
            session.commit()

    def _set_matrix_state(
        self,
        matrix_id: str,
        owner_id: str,
        *,
        allowed: set[MatrixStatus],
        status: MatrixStatus,
    ) -> MatrixView | None:
        with self.database.session() as session:
            record = session.get(ExperimentMatrixRecord, matrix_id)
            if record is None or record.owner_id != owner_id:
                return None
            if MatrixStatus(record.status) not in allowed:
                raise ValueError(
                    f"Matrix cannot transition from {record.status} "
                    f"to {status.value}."
                )
            record.status = status.value
            record.completed_at = None
            session.commit()
            session.refresh(record)
            return self._matrix_view(record)

    @staticmethod
    def _refresh_counts(session: Any, matrix_id: str) -> None:
        record = session.get(ExperimentMatrixRecord, matrix_id)
        if record is None:
            return
        counts = dict(
            session.execute(
                select(
                    ExperimentMatrixTaskRecord.status,
                    func.count(ExperimentMatrixTaskRecord.id),
                )
                .where(ExperimentMatrixTaskRecord.matrix_id == matrix_id)
                .group_by(ExperimentMatrixTaskRecord.status)
            ).all()
        )
        record.pending_tasks = int(counts.get(MatrixTaskStatus.PENDING.value, 0))
        record.running_tasks = int(counts.get(MatrixTaskStatus.RUNNING.value, 0))
        record.completed_tasks = int(counts.get(MatrixTaskStatus.COMPLETED.value, 0))
        record.failed_tasks = int(counts.get(MatrixTaskStatus.FAILED.value, 0))
        record.cancelled_tasks = int(counts.get(MatrixTaskStatus.CANCELLED.value, 0))
        record.updated_at = datetime.now(UTC)


def _config_hash(config: PromptModelConfig) -> str:
    payload = {
        "provider": config.provider,
        "base_url": config.base_url,
        "model": config.model,
        "system_prompt": config.system_prompt,
        "temperature": config.temperature,
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _definition_json(definition: MatrixDefinition) -> str:
    return json.dumps(
        definition.model_dump(mode="json", exclude_computed_fields=True),
        ensure_ascii=False,
    )


def _mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def _rate(samples: list[dict[str, Any]], key: str) -> float:
    return sum(bool(item[key]) for item in samples) / len(samples) if samples else 0.0


def _failure_rate(samples: list[dict[str, Any]]) -> float:
    return (
        sum(not bool(item["passed"]) and not bool(item["review"]) for item in samples)
        / len(samples)
        if samples
        else 0.0
    )


def _distribution(counter: Counter[str]) -> list[DistributionItem]:
    return [
        DistributionItem(key=key, count=count)
        for key, count in counter.most_common()
    ]


def _result_usage(result: TrialSuiteResult) -> dict[str, int]:
    input_tokens = 0
    output_tokens = 0
    latency_ms = 0
    for item in result.results:
        for turn in item.turns:
            latency_ms += turn.latency_ms or 0
            input_tokens += _int_value(turn.trace.get("input_tokens"))
            output_tokens += _int_value(turn.trace.get("output_tokens"))
        metadata = item.semantic_metadata
        if metadata is not None:
            latency_ms += metadata.latency_ms or 0
            input_tokens += metadata.input_tokens or 0
            output_tokens += metadata.output_tokens or 0
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "latency_ms": latency_ms,
    }


def _int_value(value: object) -> int:
    return value if isinstance(value, int) else 0


def _group(
    samples: list[dict[str, Any]],
    prefix: str,
    key_fn: Any,
) -> list[MatrixVariantAnalytics]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for sample in samples:
        combination = sample["combination"]
        groups[str(key_fn(combination))].append(sample)
    return [
        _variant(f"{prefix}:{key}", key, items)
        for key, items in sorted(groups.items())
    ]


def _group_scenarios(samples: list[dict[str, Any]]) -> list[MatrixVariantAnalytics]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for sample in samples:
        result = sample["result"]
        combination = sample["combination"]
        for item in result.results:
            usage = _result_usage(TrialSuiteResult(target=result.target, results=(item,)))
            groups[item.scenario.name].append(
                {
                    "combination": combination,
                    "score": float(item.verdict.score),
                    "passed": item.verdict.passed and not item.review_required,
                    "review": item.review_required,
                    **usage,
                }
            )
    return [_variant(f"scenario:{key}", key, items) for key, items in sorted(groups.items())]


def _variant(key: str, label: str, samples: list[dict[str, Any]]) -> MatrixVariantAnalytics:
    scores = [float(item["score"]) for item in samples]
    return MatrixVariantAnalytics(
        key=key,
        label=label,
        run_count=len(samples),
        mean_score=_mean(scores),
        minimum_score=min(scores) if scores else None,
        maximum_score=max(scores) if scores else None,
        standard_deviation=(statistics.pstdev(scores) if len(scores) > 1 else 0.0),
        pass_rate=_rate(samples, "passed"),
        review_rate=_rate(samples, "review"),
        failure_rate=_failure_rate(samples),
        input_tokens=sum(int(item["input_tokens"]) for item in samples),
        output_tokens=sum(int(item["output_tokens"]) for item in samples),
        latency_ms=sum(int(item["latency_ms"]) for item in samples),
    )
