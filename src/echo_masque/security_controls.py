"""Persistent rate limiting, quotas, and per-user concurrency controls."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import delete, func, select

from echo_masque.config import Settings
from echo_masque.persistence import Database
from echo_masque.persistence.models import (
    CharacterCardRecord,
    CustomScenarioRecord,
    ExperimentMatrixRecord,
    RunSnapshotRecord,
    TestPackRecord,
    TrialRunRecord,
)
from echo_masque.persistence.security_models import RateLimitBucketRecord

ResourceKind = Literal["character", "scenario", "pack", "run", "matrix"]


class QuotaExceeded(RuntimeError):
    def __init__(self, message: str, *, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class QuotaService:
    """Apply server-side security controls using the shared persistent database."""

    def __init__(self, database: Database, settings: Settings) -> None:
        self.database = database
        self.settings = settings

    def consume_request(self, user_id: str) -> None:
        self._consume(
            key=f"request:{user_id}",
            limit=self.settings.request_limit_per_minute,
            window_seconds=60,
            message="Request rate limit exceeded.",
        )

    def check_login(self, identity_hash: str) -> None:
        key = f"login:{identity_hash}"
        now = datetime.now(UTC)
        with self.database.session() as session:
            record = session.get(RateLimitBucketRecord, key)
            if record is None or record.blocked_until is None:
                return
            blocked_until = self._utc(record.blocked_until)
            if blocked_until <= now:
                record.blocked_until = None
                record.count = 0
                record.window_started_at = now
                session.commit()
                return
            retry_after = max(1, int((blocked_until - now).total_seconds()))
            raise QuotaExceeded(
                "Too many failed login attempts. Try again later.",
                retry_after=retry_after,
            )

    def record_login_failure(self, identity_hash: str) -> None:
        key = f"login:{identity_hash}"
        now = datetime.now(UTC)
        window = timedelta(seconds=self.settings.login_failure_window_seconds)
        with self.database.session() as session:
            record = session.get(RateLimitBucketRecord, key)
            if record is None:
                record = RateLimitBucketRecord(
                    key=key,
                    window_started_at=now,
                    count=1,
                )
                session.add(record)
            else:
                if now - self._utc(record.window_started_at) >= window:
                    record.window_started_at = now
                    record.count = 0
                    record.blocked_until = None
                record.count += 1
            if record.count >= self.settings.login_failure_limit:
                record.blocked_until = now + timedelta(
                    seconds=self.settings.login_block_seconds
                )
            session.commit()

    def record_login_success(self, identity_hash: str) -> None:
        with self.database.session() as session:
            session.execute(
                delete(RateLimitBucketRecord).where(
                    RateLimitBucketRecord.key == f"login:{identity_hash}"
                )
            )
            session.commit()

    def enforce_create(
        self,
        owner_id: str,
        kind: ResourceKind,
        *,
        incoming: int = 1,
    ) -> None:
        counts = self.counts(owner_id)
        limits = {
            "character": self.settings.max_characters_per_user,
            "scenario": self.settings.max_scenarios_per_user,
            "pack": self.settings.max_test_packs_per_user,
            "run": self.settings.max_runs_per_user,
            "matrix": self.settings.max_matrices_per_user,
        }
        if counts[kind] + incoming > limits[kind]:
            raise QuotaExceeded(f"{kind.title()} quota exceeded for this account.")
        if counts["workspace"] + incoming > self.settings.max_workspace_records_per_user:
            raise QuotaExceeded("Workspace storage quota exceeded for this account.")

    def enforce_run_start(self, owner_id: str) -> None:
        self.enforce_create(owner_id, "run")
        with self.database.session() as session:
            active = session.scalar(
                select(func.count())
                .select_from(RunSnapshotRecord)
                .join(TrialRunRecord, TrialRunRecord.id == RunSnapshotRecord.run_id)
                .where(
                    RunSnapshotRecord.owner_id == owner_id,
                    TrialRunRecord.status.in_(("pending", "running")),
                )
            )
        if int(active or 0) >= self.settings.max_concurrent_runs_per_user:
            raise QuotaExceeded(
                "Concurrent Run limit reached for this account.",
                retry_after=5,
            )

    def enforce_matrix_launch(self, owner_id: str, task_count: int) -> None:
        if task_count <= 0:
            return
        start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        with self.database.session() as session:
            used = session.scalar(
                select(func.coalesce(func.sum(ExperimentMatrixRecord.total_tasks), 0)).where(
                    ExperimentMatrixRecord.owner_id == owner_id,
                    ExperimentMatrixRecord.started_at.is_not(None),
                    ExperimentMatrixRecord.started_at >= start,
                )
            )
        if int(used or 0) + task_count > self.settings.max_matrix_tasks_per_day:
            raise QuotaExceeded("Daily Matrix task quota exceeded for this account.")

    def enforce_import(
        self,
        owner_id: str,
        *,
        characters: int,
        scenarios: int,
        packs: int,
        runs: int,
        matrices: int = 0,
    ) -> None:
        incoming = {
            "character": characters,
            "scenario": scenarios,
            "pack": packs,
            "run": runs,
            "matrix": matrices,
        }
        for kind, count in incoming.items():
            if count:
                self.enforce_create(owner_id, kind, incoming=count)  # type: ignore[arg-type]
        if sum(incoming.values()) + self.counts(owner_id)["workspace"] > (
            self.settings.max_workspace_records_per_user
        ):
            raise QuotaExceeded("Workspace import exceeds the account storage quota.")

    def counts(self, owner_id: str) -> dict[str, int]:
        with self.database.session() as session:
            characters = self._count(session, CharacterCardRecord, owner_id)
            scenarios = self._count(session, CustomScenarioRecord, owner_id)
            packs = self._count(session, TestPackRecord, owner_id)
            runs = self._count(session, RunSnapshotRecord, owner_id)
            matrices = self._count(session, ExperimentMatrixRecord, owner_id)
        return {
            "character": characters,
            "scenario": scenarios,
            "pack": packs,
            "run": runs,
            "matrix": matrices,
            "workspace": characters + scenarios + packs + runs + matrices,
        }

    def _consume(
        self,
        *,
        key: str,
        limit: int,
        window_seconds: int,
        message: str,
    ) -> None:
        if limit <= 0:
            return
        now = datetime.now(UTC)
        window = timedelta(seconds=window_seconds)
        with self.database.session() as session:
            record = session.get(RateLimitBucketRecord, key)
            if record is None:
                record = RateLimitBucketRecord(
                    key=key,
                    window_started_at=now,
                    count=1,
                )
                session.add(record)
                session.commit()
                return
            if now - self._utc(record.window_started_at) >= window:
                record.window_started_at = now
                record.count = 1
                record.blocked_until = None
                session.commit()
                return
            record.count += 1
            if record.count > limit:
                session.commit()
                retry_after = max(
                    1,
                    int((self._utc(record.window_started_at) + window - now).total_seconds()),
                )
                raise QuotaExceeded(message, retry_after=retry_after)
            session.commit()

    @staticmethod
    def _count(session: object, model: object, owner_id: str) -> int:
        value = session.scalar(  # type: ignore[attr-defined]
            select(func.count()).select_from(model).where(model.owner_id == owner_id)  # type: ignore[attr-defined]
        )
        return int(value or 0)

    @staticmethod
    def _utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
