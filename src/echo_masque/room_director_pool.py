"""Async bounded Room Director transport over the existing FREE ONLY Utility pool.

No utility JSON salvage, additional model judge, hidden retries, paid fallback,
private cards or tools. The shared provider adapter owns endpoint/credential safety.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from time import perf_counter
from typing import Literal

from echo_masque.providers.attempts import ModelAttemptBudgetExceeded
from echo_masque.providers.base import ChatMessage, ProviderCompletion
from echo_masque.providers.errors import ProviderError, ProviderTimeoutError
from echo_masque.providers.openai_compatible import OpenAICompatibleProvider
from echo_masque.room_director import (
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    AttemptReceipt,
    DirectorInput,
    DirectorReply,
    DirectorResult,
    call_director,
)
from echo_masque.utility_gateway_contracts import UtilityRoute
from echo_masque.utility_gateway_live import ExistingProviderUtilityCaller
from echo_masque.utility_gateway_router import UtilityGatewayRouter

logger = logging.getLogger(__name__)


class RoomDirectorPool:
    def __init__(
        self,
        gateway: UtilityGatewayRouter,
        *,
        provider_factory: Callable[[UtilityRoute], OpenAICompatibleProvider] | None = None,
    ) -> None:
        self.gateway = gateway
        self.provider_factory = provider_factory or ExistingProviderUtilityCaller._provider

    async def decide(self, view: DirectorInput) -> DirectorResult:
        policy = self.gateway.runtime.config().room_director
        now = datetime.now(UTC)
        accepted = {
            report.member_id: report
            for report in policy.qualifications
            if report.meets_gate()
            and report.approved_at <= now < report.expires_at
            and report.prompt_version == PROMPT_VERSION
        }
        if not policy.enabled or not accepted:
            return DirectorResult(outcome="unavailable", input_fingerprint=view.fingerprint)
        routes = [
            route
            for route in self.gateway.free_routes("room_director")
            if (report := accepted.get(route.member_id)) is not None
            and (report.provider, report.base_url.rstrip("/"), report.model)
            == (route.provider, route.base_url.rstrip("/"), route.model)
        ]
        attempts: list[AttemptReceipt] = []
        deadline = perf_counter() + policy.deadline_seconds
        for route in routes[: policy.max_attempts]:
            remaining = deadline - perf_counter()
            if remaining <= 0:
                break
            started = perf_counter()
            completion: ProviderCompletion | None = None
            failure: ProviderError | None = None
            outcome: Literal["success", "timeout", "unavailable", "invalid", "error"]
            try:
                async with asyncio.timeout(remaining):
                    completion = await self.provider_factory(route).complete(
                        messages=(
                            ChatMessage(role="system", content=SYSTEM_PROMPT),
                            ChatMessage(role="user", content=view.user_prompt),
                        ),
                        model=route.model,
                        temperature=0.0,
                        max_output_tokens=256,
                        # Strict validation follows one call. No response-format probe/repair calls.
                        response_format=None,
                    )
                valid_envelope = (
                    completion.model == accepted[route.member_id].observed_model
                    and not completion.tool_calls
                    and completion.finish_reason != "length"
                )
                outcome = "success" if valid_envelope else "invalid"
            except ModelAttemptBudgetExceeded:
                # Admission was denied before HTTP, so do not fabricate a provider attempt.
                return DirectorResult(
                    outcome="unavailable",
                    attempts=tuple(attempts),
                    input_fingerprint=view.fingerprint,
                    failure_code="budget_exhausted",
                )
            except (TimeoutError, ProviderTimeoutError):
                outcome = "timeout"
            except ProviderError as exc:
                failure = exc
                outcome = "unavailable"
            elapsed = (perf_counter() - started) * 1000
            attempts.append(
                AttemptReceipt(
                    provider=route.provider,
                    model=completion.model if completion else route.model,
                    outcome=outcome,
                    latency_ms=elapsed,
                    input_tokens=completion.input_tokens if completion else None,
                    output_tokens=completion.output_tokens if completion else None,
                    # A FREE ONLY routing setting is not a monetary usage receipt.
                    cost_usd=None,
                )
            )
            try:
                self.gateway.observe_director_transport(
                    route,
                    completion=completion,
                    failure=failure,
                    timed_out=outcome == "timeout",
                    invalid=outcome == "invalid",
                )
            except Exception:
                # Diagnostic health loss must not reinterpret a known decision or repeat a call.
                logger.warning("room_director_pool_observation_failed member=%s", route.member_id)
            if completion is not None:
                reply = DirectorReply(text=completion.text[:16384], attempts=tuple(attempts))
                return call_director(view, lambda *_, reply=reply: reply)
        return DirectorResult(
            outcome="unavailable", attempts=tuple(attempts), input_fingerprint=view.fingerprint
        )
