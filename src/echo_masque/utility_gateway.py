"""Free-first system AI routing for Character Relay Utility capabilities."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from time import perf_counter
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from sqlalchemy import func, select

from echo_masque.admin_runtime import UtilityCapability, UtilityProviderMember
from echo_masque.auth import SYSTEM_RUNTIME_USER_ID
from echo_masque.credentials import CredentialVault
from echo_masque.persistence.utility_gateway_models import (
    UtilityProviderStateRecord,
    UtilityUsageRecord,
)
from echo_masque.services.runtime import RuntimeService

_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)
UtilityHealth = Literal[
    "unknown", "healthy", "degraded", "unavailable", "cooling_down", "exhausted"
]
UtilityTier = Literal["free", "paid"]


class UtilityProviderSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    member_id: str
    provider: str
    model: str
    tier: UtilityTier = "free"
    configured: bool
    status: UtilityHealth = "unknown"
    remaining_value: float | None = None
    remaining_unit: str = ""
    reset_at: datetime | None = None
    observation_source: str = "none"
    latency_ms: float = 0.0
    error_rate: float = 0.0
    cooldown_until: datetime | None = None
    last_error: str = ""
    last_observed_at: datetime | None = None


class UtilityGatewaySnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    enabled: bool
    members: tuple[UtilityProviderSnapshot, ...]
    paid_fallback_enabled: bool
    daily_cost_usd: float = 0.0
    monthly_cost_usd: float = 0.0


@dataclass(frozen=True, slots=True)
class UtilityRoute:
    member_id: str
    provider: str
    model: str
    base_url: str
    tier: UtilityTier
    api_key: SecretStr
    reason: str


@dataclass(frozen=True, slots=True)
class UtilityInferenceResult:
    payload: dict[str, object]
    route: UtilityRoute
    latency_ms: int
    attempts: int
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


class UtilityGatewayUnavailable(RuntimeError):
    pass


class UtilityGatewayService:
    """Select configured free members first and keep paid fallback explicitly bounded."""

    def __init__(
        self,
        runtime: RuntimeService,
        *,
        http_transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.runtime = runtime
        self.database = runtime.repository.database
        self.http_transport = http_transport

    @staticmethod
    def _scope_id(member_id: str) -> str:
        return f"utility:{member_id}"

    def credential(self, member_id: str) -> SecretStr | None:
        vault = self.runtime.credential_vault
        if not vault.has_scope(
            owner_id=SYSTEM_RUNTIME_USER_ID,
            scope_kind=CredentialVault.runtime_scope_kind,
            scope_id=self._scope_id(member_id),
        ):
            return None
        return vault.get_scope(
            owner_id=SYSTEM_RUNTIME_USER_ID,
            scope_kind=CredentialVault.runtime_scope_kind,
            scope_id=self._scope_id(member_id),
        )

    def _state(self, member_id: str) -> UtilityProviderStateRecord | None:
        with self.database.session() as session:
            return session.get(UtilityProviderStateRecord, member_id)

    def _save_state(
        self,
        member: UtilityProviderMember,
        *,
        status: UtilityHealth,
        latency_ms: float = 0.0,
        last_error: str = "",
        remaining_value: float | None = None,
        remaining_unit: str = "",
        reset_at: datetime | None = None,
        observation_source: str = "local",
        cooldown_until: datetime | None = None,
    ) -> None:
        now = datetime.now(UTC)
        with self.database.session() as session:
            record = session.get(UtilityProviderStateRecord, member.id)
            previous_errors = record.consecutive_errors if record is not None else 0
            previous_rate = record.error_rate if record is not None else 0.0
            if record is None:
                record = UtilityProviderStateRecord(
                    member_id=member.id,
                    provider=member.provider,
                    model=member.model,
                    status=status,
                )
                session.add(record)
            failed = status in {"degraded", "unavailable", "cooling_down", "exhausted"}
            record.provider = member.provider
            record.model = member.model
            record.status = status
            record.remaining_value = remaining_value
            record.remaining_unit = remaining_unit[:40]
            record.reset_at = reset_at
            record.observation_source = observation_source[:40]
            record.latency_ms = max(0.0, latency_ms)
            record.consecutive_errors = previous_errors + 1 if failed else 0
            sample = 1.0 if failed else 0.0
            record.error_rate = round(previous_rate * 0.8 + sample * 0.2, 6)
            record.cooldown_until = cooldown_until
            record.last_error = last_error[:500]
            record.last_observed_at = now
            session.commit()

    def _record_usage(
        self,
        route: UtilityRoute,
        capability: UtilityCapability,
        *,
        status: str,
        latency_ms: int,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: float = 0.0,
    ) -> None:
        with self.database.session() as session:
            session.add(
                UtilityUsageRecord(
                    member_id=route.member_id,
                    capability=capability,
                    tier=route.tier,
                    status=status,
                    input_tokens=max(0, input_tokens),
                    output_tokens=max(0, output_tokens),
                    cost_usd=max(0.0, cost_usd),
                    latency_ms=max(0, latency_ms),
                )
            )
            session.commit()

    def _cost_since(self, since: datetime) -> float:
        with self.database.session() as session:
            value = session.scalar(
                select(func.coalesce(func.sum(UtilityUsageRecord.cost_usd), 0.0)).where(
                    UtilityUsageRecord.tier == "paid",
                    UtilityUsageRecord.created_at >= since,
                )
            )
            return float(value or 0.0)

    @staticmethod
    def _aware(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

    def snapshot(self) -> UtilityGatewaySnapshot:
        config = self.runtime.config().utility_gateway
        now = datetime.now(UTC)
        values: list[UtilityProviderSnapshot] = []
        for member in config.members:
            state = self._state(member.id)
            status: UtilityHealth = "unknown"
            if state is not None:
                status = state.status  # type: ignore[assignment]
                cooldown = self._aware(state.cooldown_until)
                if cooldown is not None and cooldown > now:
                    status = "cooling_down"
            values.append(
                UtilityProviderSnapshot(
                    member_id=member.id,
                    provider=member.provider,
                    model=member.model,
                    configured=self.credential(member.id) is not None,
                    status=status,
                    remaining_value=state.remaining_value if state is not None else None,
                    remaining_unit=state.remaining_unit if state is not None else "",
                    reset_at=self._aware(state.reset_at) if state is not None else None,
                    observation_source=state.observation_source if state is not None else "none",
                    latency_ms=state.latency_ms if state is not None else 0.0,
                    error_rate=state.error_rate if state is not None else 0.0,
                    cooldown_until=self._aware(state.cooldown_until) if state is not None else None,
                    last_error=state.last_error if state is not None else "",
                    last_observed_at=self._aware(state.last_observed_at) if state is not None else None,
                )
            )
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = day_start.replace(day=1)
        return UtilityGatewaySnapshot(
            enabled=config.enabled,
            members=tuple(values),
            paid_fallback_enabled=config.paid_fallback.enabled,
            daily_cost_usd=round(self._cost_since(day_start), 6),
            monthly_cost_usd=round(self._cost_since(month_start), 6),
        )

    def _member_candidates(self, capability: UtilityCapability) -> list[UtilityProviderMember]:
        config = self.runtime.config().utility_gateway
        now = datetime.now(UTC)
        candidates: list[tuple[tuple[float, ...], UtilityProviderMember]] = []
        health_rank = {"healthy": 0, "unknown": 1, "degraded": 2}
        for member in config.members:
            if not member.enabled or capability not in member.capabilities:
                continue
            if self.credential(member.id) is None:
                continue
            state = self._state(member.id)
            status = state.status if state is not None else "unknown"
            cooldown = self._aware(state.cooldown_until) if state is not None else None
            reset = self._aware(state.reset_at) if state is not None else None
            if status == "exhausted" and reset is not None and reset <= now:
                status = "unknown"
            if cooldown is not None and cooldown > now:
                continue
            if status in {"unavailable", "exhausted", "cooling_down"}:
                continue
            if config.routing_strategy == "fixed_priority":
                score = (float(member.priority),)
            else:
                score = (
                    float(health_rank.get(status, 3)),
                    state.error_rate if state is not None else 0.0,
                    state.latency_ms if state is not None and state.latency_ms > 0 else 999999.0,
                    float(member.priority),
                )
            candidates.append((score, member))
        candidates.sort(key=lambda item: item[0])
        return [item[1] for item in candidates]

    def _paid_route(
        self,
        capability: UtilityCapability,
        *,
        estimated_cost_usd: float,
    ) -> UtilityRoute | None:
        config = self.runtime.config().utility_gateway
        fallback = config.paid_fallback
        if not fallback.enabled or estimated_cost_usd <= 0:
            return None
        if estimated_cost_usd > fallback.max_call_usd:
            return None
        now = datetime.now(UTC)
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = day_start.replace(day=1)
        if self._cost_since(day_start) + estimated_cost_usd > fallback.daily_budget_usd:
            return None
        if self._cost_since(month_start) + estimated_cost_usd > fallback.monthly_budget_usd:
            return None
        for member in config.members:
            if member.provider != "openrouter":
                continue
            key = self.credential(member.id)
            if key is None:
                continue
            return UtilityRoute(
                member_id=member.id,
                provider="openrouter",
                model=fallback.model,
                base_url=fallback.base_url,
                tier="paid",
                api_key=key,
                reason=f"all_free_unavailable:{capability}",
            )
        return None

    @staticmethod
    def _chat_endpoint(base_url: str) -> str:
        root = base_url.rstrip("/")
        if root.endswith("/chat/completions"):
            return root
        if root.endswith("/v1"):
            return f"{root}/chat/completions"
        return f"{root}/v1/chat/completions"

    @staticmethod
    def _json_payload(text: str) -> dict[str, object] | None:
        value = text.strip()
        match = _JSON_OBJECT.search(value)
        if match is not None:
            value = match.group(0)
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return None
        return parsed if isinstance(parsed, dict) else None

    @staticmethod
    def _quota_headers(response: httpx.Response) -> tuple[float | None, str, datetime | None]:
        remaining: float | None = None
        unit = ""
        for name, candidate_unit in (
            ("x-ratelimit-remaining-requests", "requests"),
            ("ratelimit-remaining", "requests"),
            ("x-ratelimit-remaining-tokens", "tokens"),
        ):
            raw = response.headers.get(name)
            if raw is None:
                continue
            try:
                remaining = float(raw)
                unit = candidate_unit
                break
            except ValueError:
                continue
        reset_at: datetime | None = None
        raw_reset = response.headers.get("x-ratelimit-reset") or response.headers.get("ratelimit-reset")
        if raw_reset:
            try:
                seconds = float(raw_reset)
                if seconds > 10_000_000_000:
                    seconds /= 1000.0
                if seconds > 1_000_000_000:
                    reset_at = datetime.fromtimestamp(seconds, tz=UTC)
                elif seconds >= 0:
                    reset_at = datetime.now(UTC) + timedelta(seconds=seconds)
            except (ValueError, OSError, OverflowError):
                pass
        return remaining, unit, reset_at

    @staticmethod
    def _usage(body: object) -> tuple[int, int, float]:
        if not isinstance(body, dict):
            return 0, 0, 0.0
        usage = body.get("usage")
        if not isinstance(usage, dict):
            return 0, 0, 0.0
        input_tokens = usage.get("prompt_tokens") or usage.get("input_tokens") or 0
        output_tokens = usage.get("completion_tokens") or usage.get("output_tokens") or 0
        cost = usage.get("cost") or 0.0
        return (
            int(input_tokens) if isinstance(input_tokens, int) else 0,
            int(output_tokens) if isinstance(output_tokens, int) else 0,
            float(cost) if isinstance(cost, (int, float)) else 0.0,
        )

    def _call_openai_compatible(
        self,
        route: UtilityRoute,
        *,
        system_prompt: str,
        user_prompt: str,
        max_output_tokens: int,
        temperature: float,
        timeout_seconds: float,
    ) -> tuple[httpx.Response, object, str]:
        with httpx.Client(timeout=timeout_seconds, transport=self.http_transport) as client:
            response = client.post(
                self._chat_endpoint(route.base_url),
                headers={
                    "Authorization": f"Bearer {route.api_key.get_secret_value()}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": route.model,
                    "temperature": temperature,
                    "max_tokens": max_output_tokens,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                },
            )
        body = response.json() if response.content else {}
        content = ""
        if isinstance(body, dict):
            try:
                value = body["choices"][0]["message"]["content"]  # type: ignore[index]
                content = value if isinstance(value, str) else ""
            except (KeyError, IndexError, TypeError):
                content = ""
        return response, body, content

    def invoke_json(
        self,
        capability: UtilityCapability,
        *,
        system_prompt: str,
        user_prompt: str,
        estimated_cost_usd: float = 0.0,
        max_output_tokens: int = 192,
        temperature: float = 0.0,
    ) -> UtilityInferenceResult:
        config = self.runtime.config().utility_gateway
        if not config.enabled:
            raise UtilityGatewayUnavailable("utility_gateway_disabled")
        candidates = self._member_candidates(capability)
        attempts = 0
        last_reason = "no_eligible_free_member"
        for member in candidates:
            key = self.credential(member.id)
            if key is None:
                continue
            route = UtilityRoute(
                member_id=member.id,
                provider=member.provider,
                model=member.model,
                base_url=member.base_url,
                tier="free",
                api_key=key,
                reason="free_pool",
            )
            attempts += 1
            started = perf_counter()
            try:
                response, body, content = self._call_openai_compatible(
                    route,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_output_tokens=max_output_tokens,
                    temperature=temperature,
                    timeout_seconds=config.timeout_seconds,
                )
                latency = round((perf_counter() - started) * 1000)
                remaining, unit, reset_at = self._quota_headers(response)
                if response.status_code == 429:
                    cooldown = reset_at or (datetime.now(UTC) + timedelta(minutes=2))
                    self._save_state(
                        member,
                        status="exhausted" if remaining == 0 else "cooling_down",
                        latency_ms=latency,
                        last_error="http_429",
                        remaining_value=remaining,
                        remaining_unit=unit,
                        reset_at=reset_at,
                        observation_source="response_header",
                        cooldown_until=cooldown,
                    )
                    self._record_usage(route, capability, status="quota_error", latency_ms=latency)
                    last_reason = "http_429"
                    continue
                if response.status_code >= 500:
                    self._save_state(member, status="degraded", latency_ms=latency, last_error=f"http_{response.status_code}")
                    self._record_usage(route, capability, status="provider_error", latency_ms=latency)
                    last_reason = f"http_{response.status_code}"
                    continue
                if response.status_code >= 400:
                    self._save_state(member, status="unavailable", latency_ms=latency, last_error=f"http_{response.status_code}")
                    self._record_usage(route, capability, status="provider_error", latency_ms=latency)
                    last_reason = f"http_{response.status_code}"
                    continue
                parsed = self._json_payload(content)
                if parsed is None:
                    self._save_state(member, status="degraded", latency_ms=latency, last_error="invalid_json")
                    self._record_usage(route, capability, status="invalid_json", latency_ms=latency)
                    last_reason = "invalid_json"
                    continue
                input_tokens, output_tokens, cost = self._usage(body)
                self._save_state(
                    member,
                    status="healthy",
                    latency_ms=latency,
                    remaining_value=remaining,
                    remaining_unit=unit,
                    reset_at=reset_at,
                    observation_source="response_header" if remaining is not None or reset_at is not None else "response",
                )
                self._record_usage(
                    route,
                    capability,
                    status="completed",
                    latency_ms=latency,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=cost,
                )
                return UtilityInferenceResult(
                    payload=parsed,
                    route=route,
                    latency_ms=latency,
                    attempts=attempts,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=cost,
                )
            except (httpx.HTTPError, ValueError, TypeError, KeyError, IndexError, json.JSONDecodeError):
                latency = round((perf_counter() - started) * 1000)
                self._save_state(member, status="degraded", latency_ms=latency, last_error="provider_error")
                self._record_usage(route, capability, status="provider_error", latency_ms=latency)
                last_reason = "provider_error"

        paid = self._paid_route(capability, estimated_cost_usd=estimated_cost_usd)
        if paid is None:
            raise UtilityGatewayUnavailable(last_reason)
        attempts += 1
        started = perf_counter()
        try:
            response, body, content = self._call_openai_compatible(
                paid,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_output_tokens=max_output_tokens,
                temperature=temperature,
                timeout_seconds=config.timeout_seconds,
            )
            latency = round((perf_counter() - started) * 1000)
            if response.status_code >= 400:
                self._record_usage(paid, capability, status="provider_error", latency_ms=latency)
                raise UtilityGatewayUnavailable(f"paid_http_{response.status_code}")
            parsed = self._json_payload(content)
            if parsed is None:
                self._record_usage(paid, capability, status="invalid_json", latency_ms=latency)
                raise UtilityGatewayUnavailable("paid_invalid_json")
            input_tokens, output_tokens, observed_cost = self._usage(body)
            charged = observed_cost if observed_cost > 0 else estimated_cost_usd
            self._record_usage(
                paid,
                capability,
                status="completed",
                latency_ms=latency,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=charged,
            )
            return UtilityInferenceResult(
                payload=parsed,
                route=paid,
                latency_ms=latency,
                attempts=attempts,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=charged,
            )
        except httpx.HTTPError as exc:
            raise UtilityGatewayUnavailable("paid_provider_error") from exc


__all__ = [
    "UtilityGatewayService",
    "UtilityGatewaySnapshot",
    "UtilityGatewayUnavailable",
    "UtilityInferenceResult",
    "UtilityProviderSnapshot",
    "UtilityRoute",
]
