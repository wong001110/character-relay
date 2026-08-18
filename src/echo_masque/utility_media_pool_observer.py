"""Persist Media Free Pool outcomes into the shared Utility routing telemetry."""

from __future__ import annotations

from datetime import UTC, datetime
from time import perf_counter

from echo_masque.admin_runtime import UtilityProviderMember
from echo_masque.persistence.utility_gateway_models import (
    UtilityProviderQuotaRecord,
    UtilityProviderStateRecord,
    UtilityUsageRecord,
)
from echo_masque.providers.errors import (
    ProviderAuthenticationError,
    ProviderBillingRequiredError,
    ProviderCapabilityUnsupportedError,
    ProviderError,
    ProviderInsufficientBalanceError,
    ProviderModelNotFoundError,
    ProviderProtocolError,
    ProviderQuotaExhaustedError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)


class UtilityMediaPoolObserver:
    """Share Media provider access/health evidence with the normal Utility router."""

    def __init__(self, database: object) -> None:
        self.database = database

    @staticmethod
    def started() -> float:
        return perf_counter()

    @staticmethod
    def _latency(started: float) -> int:
        return max(0, round((perf_counter() - started) * 1000))

    def _usage(self, member_id: str, *, status: str, latency_ms: int) -> None:
        with self.database.session() as session:  # type: ignore[attr-defined]
            session.add(
                UtilityUsageRecord(
                    member_id=member_id,
                    capability="media_understanding",
                    tier="free",
                    status=status[:24],
                    latency_ms=latency_ms,
                )
            )
            session.commit()

    def success(self, member: UtilityProviderMember, *, started: float) -> None:
        now = datetime.now(UTC)
        latency_ms = self._latency(started)
        with self.database.session() as session:  # type: ignore[attr-defined]
            record = session.get(UtilityProviderStateRecord, member.id)
            if record is None:
                record = UtilityProviderStateRecord(
                    member_id=member.id,
                    provider=member.provider,
                    model=member.model,
                )
                session.add(record)
            record.provider = member.provider
            record.model = member.model
            record.status = "healthy"
            record.latency_ms = latency_ms
            record.error_rate = round(record.error_rate * 0.8, 6)
            record.consecutive_errors = 0
            record.last_error = ""
            record.cooldown_until = None
            record.observation_source = "media_runtime"
            record.last_observed_at = now
            session.commit()
        self._usage(member.id, status="completed", latency_ms=latency_ms)

    def failure(
        self,
        member: UtilityProviderMember,
        exc: ProviderError,
        *,
        started: float,
    ) -> None:
        latency_ms = self._latency(started)
        # Capability mismatch is scoped to the model capability registry and must not poison
        # healthy text Utility routes for the same member.
        if isinstance(exc, ProviderCapabilityUnsupportedError):
            self._usage(member.id, status="capability", latency_ms=latency_ms)
            return

        now = datetime.now(UTC)
        status = "degraded"
        cooldown_until = None
        remaining_value = None
        remaining_unit = ""
        reset_at = None
        error_code = exc.reason_code
        quota_observations = ()

        if isinstance(exc, (ProviderBillingRequiredError, ProviderInsufficientBalanceError)):
            status = "unavailable"
        elif isinstance(exc, (ProviderAuthenticationError, ProviderModelNotFoundError)):
            status = "unavailable"
        elif isinstance(exc, ProviderQuotaExhaustedError):
            status = "exhausted"
            quota_observations = exc.quota_observations
            remaining_value = 0
            zero = next((item for item in quota_observations if item.remaining == 0), None)
            remaining_unit = zero.unit if zero is not None else "requests"
            resets = [item.reset_at for item in quota_observations if item.reset_at is not None]
            reset_at = min(resets) if resets else None
            cooldown_until = reset_at
        elif isinstance(exc, ProviderRateLimitError):
            status = "cooling_down"
            quota_observations = exc.quota_observations
            resets = [item.reset_at for item in quota_observations if item.reset_at is not None]
            reset_at = min(resets) if resets else None
            cooldown_until = reset_at
        elif isinstance(exc, (ProviderTimeoutError, ProviderUnavailableError, ProviderProtocolError)):
            status = "degraded"

        with self.database.session() as session:  # type: ignore[attr-defined]
            record = session.get(UtilityProviderStateRecord, member.id)
            if record is None:
                record = UtilityProviderStateRecord(
                    member_id=member.id,
                    provider=member.provider,
                    model=member.model,
                )
                session.add(record)
            previous_rate = record.error_rate
            previous_errors = record.consecutive_errors
            record.provider = member.provider
            record.model = member.model
            record.status = status
            record.latency_ms = latency_ms
            record.error_rate = round(previous_rate * 0.8 + 0.2, 6)
            record.consecutive_errors = previous_errors + 1
            record.last_error = f"{error_code}:{exc}"[:500]
            record.remaining_value = remaining_value
            record.remaining_unit = remaining_unit
            record.reset_at = reset_at
            record.cooldown_until = cooldown_until
            record.observation_source = "media_runtime"
            record.last_observed_at = now
            for observation in quota_observations:
                quota = session.get(
                    UtilityProviderQuotaRecord,
                    (member.id, observation.kind),
                )
                if quota is None:
                    quota = UtilityProviderQuotaRecord(
                        member_id=member.id,
                        kind=observation.kind,
                    )
                    session.add(quota)
                quota.remaining = observation.remaining
                quota.limit_value = observation.limit
                quota.unit = observation.unit[:40]
                quota.reset_at = observation.reset_at
                quota.window_seconds = observation.window_seconds
                quota.source = observation.source[:48]
                quota.observed_at = now
            session.commit()
        self._usage(member.id, status=status, latency_ms=latency_ms)


__all__ = ["UtilityMediaPoolObserver"]
